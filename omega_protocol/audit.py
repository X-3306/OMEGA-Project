"""Report generation utilities."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from omega_protocol.models import ExecutionPlan, ExecutionResult, SessionBundle, to_serializable
from omega_protocol.runtime import packaged_resource


class ReportWriter:
    """Writes JSONL, CSV, HTML and PDF session reports."""

    def __init__(self, report_root: Path) -> None:
        self.report_root = Path(report_root)
        self.report_root.mkdir(parents=True, exist_ok=True)
        template_dir = packaged_resource("omega_protocol", "report_templates")
        self.environment = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(),
        )
        self.pdf_font_name = _register_report_font()

    def write_session(
        self,
        mode,
        dry_run: bool,
        plans: list[ExecutionPlan],
        results: list[ExecutionResult],
        native_bridge_state: str,
    ) -> SessionBundle:
        """Write all session artifacts and return a bundle."""

        session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        session_dir = self.report_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        jsonl_path = session_dir / "session.jsonl"
        csv_path = session_dir / "summary.csv"
        html_path = session_dir / "session.html"
        pdf_path = session_dir / "session.pdf"

        with jsonl_path.open("w", encoding="utf-8") as handle:
            for result in results:
                handle.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")

        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["plan_id", "target", "success", "assurance", "method", "summary"])
            for result in results:
                writer.writerow(
                    [
                        result.plan_id,
                        result.target,
                        result.success,
                        result.assurance_achieved.value,
                        result.method_name,
                        result.summary,
                    ],
                )

        template = self.environment.get_template("session_report.html.j2")
        html = template.render(
            session_id=session_id,
            mode=mode.value,
            dry_run=dry_run,
            plans=[plan.to_dict() for plan in plans],
            results=[result.to_dict() for result in results],
            generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            native_bridge_state=native_bridge_state,
        )
        html_path.write_text(html, encoding="utf-8")

        self._write_pdf(pdf_path, session_id, mode.value, dry_run, native_bridge_state, results)

        bundle = SessionBundle(
            session_id=session_id,
            generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            mode=mode,
            dry_run=dry_run,
            plans=plans,
            results=results,
            report_paths={
                "jsonl": str(jsonl_path),
                "csv": str(csv_path),
                "html": str(html_path),
                "pdf": str(pdf_path),
            },
            native_bridge_state=native_bridge_state,
        )
        (session_dir / "bundle.json").write_text(
            json.dumps(to_serializable(bundle), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return bundle

    def _write_pdf(
        self,
        path: Path,
        session_id: str,
        mode: str,
        dry_run: bool,
        native_bridge_state: str,
        results: list[ExecutionResult],
    ) -> None:
        """Write a Unicode-safe PDF report using reportlab."""

        doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=40, rightMargin=40, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                name="OmegaBody",
                parent=styles["BodyText"],
                fontName=self.pdf_font_name,
                fontSize=10,
                leading=13,
            ),
        )
        styles.add(
            ParagraphStyle(
                name="OmegaTitle",
                parent=styles["Heading1"],
                fontName=self.pdf_font_name,
                fontSize=18,
                leading=22,
            ),
        )
        styles.add(
            ParagraphStyle(
                name="OmegaSub",
                parent=styles["Heading2"],
                fontName=self.pdf_font_name,
                fontSize=12,
                leading=16,
            ),
        )

        story = [
            Paragraph("OMEGA Protocol Session Report", styles["OmegaTitle"]),
            Spacer(1, 8),
            Paragraph(f"Session: {session_id}", styles["OmegaBody"]),
            Paragraph(f"Mode: {mode}", styles["OmegaBody"]),
            Paragraph(f"Dry run: {dry_run}", styles["OmegaBody"]),
            Paragraph(f"Native backend: {native_bridge_state}", styles["OmegaBody"]),
            Spacer(1, 16),
        ]

        for result in results:
            story.extend(
                [
                    Paragraph(result.display_name, styles["OmegaSub"]),
                    Paragraph(f"Target: {result.target}", styles["OmegaBody"]),
                    Paragraph(f"Success: {result.success}", styles["OmegaBody"]),
                    Paragraph(f"Assurance: {result.assurance_achieved.value}", styles["OmegaBody"]),
                    Paragraph(f"Method: {result.method_name}", styles["OmegaBody"]),
                    Paragraph(f"Summary: {result.summary}", styles["OmegaBody"]),
                    Paragraph(f"Detail: {result.detail}", styles["OmegaBody"]),
                ],
            )
            for warning in result.warnings:
                story.append(Paragraph(f"Warning: {warning}", styles["OmegaBody"]))
            story.append(Spacer(1, 12))

        doc.build(story)


def _register_report_font() -> str:
    """Register a Unicode-safe font for PDF reports."""

    candidates = [
        packaged_resource("reportlab", "fonts", "Vera.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            font_name = f"OmegaFont-{candidate.stem}"
            if font_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(font_name, str(candidate)))
            return font_name
    return "Helvetica"
