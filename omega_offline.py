import argparse
import json
from pathlib import Path

from omega_protocol.models import OperationMode
from omega_protocol.orchestrator import OmegaOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OMEGA Protocol offline runner for WinPE and maintenance sessions.",
    )
    parser.add_argument("--disk", type=int, required=True, help="Physical disk number.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute instead of returning only the preflight plan.",
    )
    parser.add_argument(
        "--report-dir",
        default=str(Path.cwd() / "reports"),
        help="Directory for generated reports.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    orchestrator = OmegaOrchestrator(report_root=Path(args.report_dir))
    payload: list[dict[str, object]] | dict[str, object]
    if not args.execute:
        payload = [
            plan.to_dict()
            for plan in orchestrator.build_plans(
                mode=OperationMode.DRIVE_SANITIZE,
                targets=[str(args.disk)],
                dry_run=True,
            )
        ]
    else:
        payload = orchestrator.execute(
            mode=OperationMode.DRIVE_SANITIZE,
            targets=[str(args.disk)],
            dry_run=False,
        ).to_dict()

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
