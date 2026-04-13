"""PySide6 desktop application for OMEGA Protocol."""

from __future__ import annotations

import ctypes
from PySide6.QtGui import QPixmap
import sys
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from omega_protocol.events import (
    PreflightReady,
    SessionCompleted,
    SessionFailed,
    SessionLogEvent,
    SessionProgressEvent,
)
from omega_protocol.models import AppPhase, AppState, OperationMode, PreflightResult, SessionBundle
from omega_protocol.orchestrator import OmegaOrchestrator
from omega_protocol.runtime import application_root, packaged_resource
from omega_protocol.settings import PREFLIGHT_DEBOUNCE_MS
from omega_protocol.system import is_windows_admin
from omega_protocol.ui.list_models import DriveListModel, FileListModel
from omega_protocol.ui.workers import PreflightWorker, SessionWorker

APP_STYLE = "\n".join(
    [
        "QMainWindow, QWidget { background: #07101c; color: #edf4ff; }",
        "QToolBar { spacing: 8px; background: #0a1524; border: 1px solid #20344a; padding: 8px; }",
        "QFrame#panel { background: #0d1726; border: 1px solid #20344a; border-radius: 18px; }",
        "QLabel[role='eyebrow'] { color: #56d4ff; font-size: 11px; font-weight: 700; }",
        "QLabel[role='title'] { font-size: 24px; font-weight: 700; }",
        "QLabel[role='section'] { font-size: 15px; font-weight: 700; }",
        "QLabel[role='body'] { color: #9db0c8; }",
        "QLabel[role='headline'] { font-size: 36px; font-weight: 700; }",
        "QPushButton { background: #182a3d; border: 1px solid #28415b; "
        "border-radius: 12px; min-height: 38px; padding: 4px 12px; }",
        "QPushButton:hover { background: #21405a; }",
        "QPushButton:checked { background: #56d4ff; color: #09131f; border-color: #56d4ff; }",
        "QPushButton:disabled { color: #70839a; background: #122031; }",
        "QListView, QPlainTextEdit, QTabWidget::pane { background: #09111d; "
        "border: 1px solid #20344a; border-radius: 14px; }",
        "QTabBar::tab { background: #152234; border: 1px solid #20344a; padding: 8px 14px; "
        "margin-right: 6px; border-top-left-radius: 10px; border-top-right-radius: 10px; }",
        "QTabBar::tab:selected { background: #56d4ff; color: #08131f; }",
        "#riskCard { background: #31131a; color: #ffb6bf; border: 1px solid #5a2630; "
        "border-radius: 14px; padding: 10px 12px; }",
        "#stateBadge { background: #10273a; color: #56d4ff; border-radius: 999px; "
        "padding: 8px 14px; font-weight: 700; }",
        "QProgressBar { border: 1px solid #20344a; border-radius: 10px; background: #09111d; "
        "text-align: center; min-height: 16px; }",
        "QProgressBar::chunk { background: #56d4ff; border-radius: 9px; }",
    ],
)

SAFE_RISK_STYLE = (
    "background:#0e2d22;color:#9ef3c7;border:1px solid #214b3a;"
    "border-radius:14px;padding:10px 12px;"
)
CRITICAL_RISK_STYLE = (
    "background:#31131a;color:#ffb6bf;border:1px solid #5a2630;"
    "border-radius:14px;padding:10px 12px;"
)


class OmegaMainWindow(QMainWindow):
    """Main production UI backed by PySide6."""

    def __init__(self, orchestrator: OmegaOrchestrator | None = None) -> None:
        super().__init__()
        self.orchestrator = orchestrator or OmegaOrchestrator(report_root=Path.cwd() / "reports")
        self.thread_pool = QThreadPool.globalInstance()
        self.state = AppState()
        self.file_model = FileListModel()
        self.drive_model = DriveListModel()
        self._request_token = 0
        self._pending_force_refresh = False
        self._log_buffer: list[str] = []
        self._session_running = False

        self._build_window()
        self._build_toolbar()
        self._build_layout()
        self._apply_styles()
        self._connect_signals()

        self.preflight_timer = QTimer(self)
        self.preflight_timer.setSingleShot(True)
        self.preflight_timer.setInterval(PREFLIGHT_DEBOUNCE_MS)
        self.preflight_timer.timeout.connect(self._dispatch_preflight)

        self.log_flush_timer = QTimer(self)
        self.log_flush_timer.setInterval(75)
        self.log_flush_timer.timeout.connect(self._flush_logs)
        self.log_flush_timer.start()

        self.schedule_preflight(force_inventory_refresh=True, immediate=True)

    def _build_window(self) -> None:
        self.setWindowTitle(f"OMEGA Protocol {self.orchestrator.version}")
        self.resize(1520, 940)
        self.setMinimumSize(1180, 760)
        
        # Set application icon
        icon_path = packaged_resource("omega_protocol.ui", "Ω.png")
        if icon_path and icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Actions", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        add_files_action = QAction("Add Files", self)
        add_files_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Open))
        add_files_action.triggered.connect(self.add_files)
        toolbar.addAction(add_files_action)

        refresh_action = QAction("Refresh Drives", self)
        refresh_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Refresh))
        refresh_action.triggered.connect(
            lambda: self.schedule_preflight(force_inventory_refresh=True, immediate=True),
        )
        toolbar.addAction(refresh_action)

        admin_action = QAction("Restart as Administrator", self)
        admin_action.triggered.connect(self.restart_as_administrator)
        toolbar.addAction(admin_action)

        help_action = QAction("Help", self)
        help_action.setShortcut(QKeySequence(QKeySequence.StandardKey.HelpContents))
        help_action.triggered.connect(self.open_user_guide)
        toolbar.addAction(help_action)

        clear_action = QAction("Clear Selection", self)
        clear_action.setShortcut(QKeySequence("Ctrl+L"))
        clear_action.triggered.connect(self.clear_selection)
        toolbar.addAction(clear_action)

    def _build_layout(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root.addWidget(splitter)

        splitter.addWidget(self._build_left_column())
        splitter.addWidget(self._build_center_column())
        splitter.addWidget(self._build_right_column())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 3)

    def _build_left_column(self) -> QWidget:
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        hero = self._panel()
        hero_layout = QVBoxLayout(hero)
        
        # Add logo/icon to hero panel
        icon_path = packaged_resource("omega_protocol.ui", "Ω.png")
        if icon_path and icon_path.exists():
            icon_label = QLabel()
            pixmap = QPixmap(str(icon_path))
            scaled_pixmap = pixmap.scaledToHeight(80, Qt.TransformationMode.SmoothTransformation)
            icon_label.setPixmap(scaled_pixmap)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hero_layout.addWidget(icon_label)
        
        hero_layout.addWidget(self._label("OMEGA", "eyebrow"))
        hero_layout.addWidget(self._label("Secure Sanitization", "title"))
        hero_layout.addWidget(
            self._label(
                "Build file and drive sanitization sessions, review a preflight "
                "summary and generate an audit trail",
                "body",
            ),
        )
        left_layout.addWidget(hero)

        controls = self._panel()
        controls_layout = QVBoxLayout(controls)
        controls_layout.addWidget(self._label("Mode", "section"))

        mode_row = QHBoxLayout()
        self.files_mode_button = QPushButton("Files")
        self.files_mode_button.setCheckable(True)
        self.files_mode_button.setChecked(True)
        self.drives_mode_button = QPushButton("Drives")
        self.drives_mode_button.setCheckable(True)
        mode_row.addWidget(self.files_mode_button)
        mode_row.addWidget(self.drives_mode_button)
        controls_layout.addLayout(mode_row)

        self.dry_run_checkbox = QCheckBox("Dry run only")
        self.dry_run_checkbox.setChecked(False)
        controls_layout.addWidget(self.dry_run_checkbox)

        self.add_files_button = QPushButton("Add Files")
        self.remove_files_button = QPushButton("Remove Selected Files")
        self.refresh_inventory_button = QPushButton("Refresh Drives")
        self.clear_button = QPushButton("Clear Selection")
        self.help_button = QPushButton("Open User Guide")
        self.execute_button = QPushButton("Run Session")
        for button in (
            self.add_files_button,
            self.remove_files_button,
            self.refresh_inventory_button,
            self.clear_button,
            self.help_button,
            self.execute_button,
        ):
            controls_layout.addWidget(button)
        left_layout.addWidget(controls)

        self.state_panel = self._panel()
        state_layout = QVBoxLayout(self.state_panel)
        state_layout.addWidget(self._label("Status: ", "section"))
        self.state_badge = QLabel("READY")
        self.state_badge.setObjectName("stateBadge")
        self.state_copy = self._label(
            "Choose a mode, review the preflight and then confirm execution.",
            "body",
        )
        state_layout.addWidget(self.state_badge)
        state_layout.addWidget(self.state_copy)
        state_layout.addStretch(1)
        left_layout.addWidget(self.state_panel)
        left_layout.addStretch(1)
        return left

    def _build_center_column(self) -> QWidget:
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(12)

        header = self._panel()
        header_layout = QVBoxLayout(header)
        header_layout.addWidget(self._label("CONTROL SURFACE", "eyebrow"))
        header_layout.addWidget(self._label("OMEGA Protocol", "title"))
        header_layout.addWidget(
            self._label(
                "Use the tabs below to manage files, inspect drive inventory, "
                "review the preflight summary and open the final report.",
                "body",
            ),
        )
        center_layout.addWidget(header)

        self.tabs = QTabWidget()
        self.file_view = QListView()
        self.file_view.setModel(self.file_model)
        self.drive_view = QListView()
        self.drive_view.setModel(self.drive_model)
        self.preflight_text = QPlainTextEdit()
        self.preflight_text.setReadOnly(True)
        self.report_text = QPlainTextEdit()
        self.report_text.setReadOnly(True)
        self.help_tab = self._build_help_tab()
        self.tabs.addTab(self.file_view, "Files")
        self.tabs.addTab(self.drive_view, "Drives")
        self.tabs.addTab(self.preflight_text, "Preflight")
        self.tabs.addTab(self.report_text, "Report")
        self.tabs.addTab(self.help_tab, "Help")
        center_layout.addWidget(self.tabs, 1)
        return center

    def _build_help_tab(self) -> QWidget:
        help_tab = QWidget()
        layout = QVBoxLayout(help_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        intro = self._panel()
        intro_layout = QVBoxLayout(intro)
        intro_layout.addWidget(self._label("USER GUIDE", "eyebrow"))
        intro_layout.addWidget(self._label("Practical Help", "title"))
        intro_layout.addWidget(
            self._label(
                "Open the user guide for a simple explanation of what each "
                "button does, what Dry Run means and what the tool includes.",
                "body",
            ),
        )
        open_help_button = QPushButton("Open User Guide in Browser")
        open_help_button.clicked.connect(self.open_user_guide)
        intro_layout.addWidget(open_help_button)
        layout.addWidget(intro)

        quick_help = self._panel()
        quick_layout = QVBoxLayout(quick_help)
        quick_layout.addWidget(self._label("QUICK START", "eyebrow"))
        quick_layout.addWidget(
            self._label(
                "1. Add files or inspect drives.\n"
                "2. Review the preflight summary.\n"
                "3. Use Dry Run when you want a preview only.\n"
                "4. Run the session when you are ready.\n"
                "5. Open the report tab to review artifacts.",
                "body",
            ),
        )
        layout.addWidget(quick_help)
        
        # Add About section with links and author info
        about_panel = self._panel()
        about_layout = QVBoxLayout(about_panel)
        about_layout.addWidget(self._label("ABOUT", "eyebrow"))
        about_layout.addWidget(self._label("Project Information", "title"))
        
        # Author and links text
        about_text = QLabel()
        about_text.setProperty("role", "body")
        about_text.setWordWrap(True)
        about_text.setOpenExternalLinks(True)
        about_text.setText(
            "Author: <b>X-3306</b><br><br>"
            "For articles and documentation, visit:<br>"
            "<a href='https://medium.com/@X-3306' style='color: #56d4ff;'>Medium Articles</a><br><br>"
            "For source code and contributions, visit:<br>"
            "<a href='https://github.com/X-3306/OMEGA-Project' style='color: #56d4ff;'>"
            "OMEGA Project on GitHub</a>"
        )
        about_layout.addWidget(about_text)
        about_layout.addStretch(1)
        layout.addWidget(about_panel)
        
        layout.addStretch(1)
        return help_tab

    def _build_right_column(self) -> QWidget:
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        overview = self._panel()
        overview_layout = QVBoxLayout(overview)
        overview_layout.addWidget(self._label("Overview", "section"))
        self.risk_card = QLabel(
            "Execution mode is enabled.\n"
            "Use Dry Run when you want to preview the workflow without changing data.",
        )
        self.risk_card.setObjectName("riskCard")
        overview_layout.addWidget(self.risk_card)

        self.progress_label = self._label("0%", "headline")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        overview_layout.addWidget(self.progress_label)
        overview_layout.addWidget(self.progress_bar)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        overview_layout.addWidget(self.log_view, 1)

        right_layout.addWidget(overview, 1)
        return right

    def _connect_signals(self) -> None:
        self.files_mode_button.clicked.connect(lambda: self._set_mode(OperationMode.FILE_SANITIZE))
        self.drives_mode_button.clicked.connect(lambda: self._set_mode(OperationMode.DRIVE_SANITIZE))
        self.dry_run_checkbox.toggled.connect(lambda _checked: self.schedule_preflight())
        self.add_files_button.clicked.connect(self.add_files)
        self.remove_files_button.clicked.connect(self.remove_selected_files)
        self.refresh_inventory_button.clicked.connect(
            lambda: self.schedule_preflight(force_inventory_refresh=True, immediate=True),
        )
        self.clear_button.clicked.connect(self.clear_selection)
        self.help_button.clicked.connect(self.open_user_guide)
        self.execute_button.clicked.connect(self.start_execution)
        self.file_view.doubleClicked.connect(lambda _index: self.remove_selected_files())
        self.drive_view.clicked.connect(self._toggle_clicked_drive)

    def _apply_styles(self) -> None:
        self.setFont(QFont("Segoe UI", 10))
        self.setStyleSheet(APP_STYLE)

    def _panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        return panel

    def _label(self, text: str, role: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", role)
        label.setWordWrap(True)
        return label

    def _set_mode(self, mode: OperationMode) -> None:
        self.state.mode = mode
        self.files_mode_button.setChecked(mode is OperationMode.FILE_SANITIZE)
        self.drives_mode_button.setChecked(mode is OperationMode.DRIVE_SANITIZE)
        self.tabs.setCurrentIndex(0 if mode is OperationMode.FILE_SANITIZE else 1)
        self.schedule_preflight()

    def add_files(self) -> None:
        if self._session_running:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Select files for sanitization")
        if self.file_model.add_paths(paths):
            self.schedule_preflight()

    def remove_selected_files(self) -> None:
        if self._session_running:
            return
        indexes = self.file_view.selectionModel().selectedIndexes()
        if self.file_model.remove_rows([index.row() for index in indexes]):
            self.schedule_preflight()

    def clear_selection(self) -> None:
        if self._session_running:
            return
        self.file_model.clear()
        self.drive_model.clear_selection()
        self.state.selected_files = ()
        self.state.selected_disks = ()
        self.schedule_preflight()
        self._buffer_log("[OK] SYSTEM\nThe current selection was cleared.\n")

    def schedule_preflight(self, force_inventory_refresh: bool = False, immediate: bool = False) -> None:
        self.state.dry_run = self.dry_run_checkbox.isChecked()
        self.state.selected_files = tuple(self.file_model.paths())
        self.state.selected_disks = tuple(self.drive_model.selected_disks())
        self._request_token += 1
        self._pending_force_refresh = force_inventory_refresh or self._pending_force_refresh
        self._set_phase(AppPhase.PREFLIGHT, "Refreshing the preflight summary in the background.")
        if immediate:
            self.preflight_timer.stop()
            self._dispatch_preflight()
            return
        self.preflight_timer.start()

    def _dispatch_preflight(self) -> None:
        worker = PreflightWorker(
            orchestrator=self.orchestrator,
            request_token=self._request_token,
            mode=self.state.mode,
            targets=self.current_targets(),
            dry_run=self.dry_run_checkbox.isChecked(),
            force_inventory_refresh=self._pending_force_refresh,
        )
        worker.signals.event_emitted.connect(self._handle_preflight_event)
        self.thread_pool.start(worker)
        self._pending_force_refresh = False

    def start_execution(self) -> None:
        if self._session_running:
            return
        targets = self.current_targets()
        if not targets:
            QMessageBox.warning(self, "OMEGA Protocol", "Select at least one target before starting a session.")
            return
        if not self.dry_run_checkbox.isChecked():
            answer = QMessageBox.question(
                self,
                "OMEGA Protocol",
                "Execution mode is irreversible.\n\nDo you want to continue with the selected targets?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._session_running = True
        self.state.dry_run = self.dry_run_checkbox.isChecked()
        self._set_phase(
            AppPhase.RUNNING,
            "The session is running. I/O work is happening outside the UI thread.",
        )
        self.progress_bar.setValue(0)
        self.progress_label.setText("0%")
        self._set_controls_enabled(False)

        worker = SessionWorker(
            orchestrator=self.orchestrator,
            mode=self.state.mode,
            targets=targets,
            dry_run=self.dry_run_checkbox.isChecked(),
        )
        worker.signals.event_emitted.connect(self._handle_session_event)
        self.thread_pool.start(worker)

    def current_targets(self) -> list[str]:
        if self.state.mode is OperationMode.FILE_SANITIZE:
            return self.file_model.paths()
        return [str(disk_number) for disk_number in self.drive_model.selected_disks()]

    def _toggle_clicked_drive(self, index) -> None:
        current = self.drive_model.data(index, int(Qt.ItemDataRole.CheckStateRole))
        new_value = Qt.CheckState.Unchecked if current == Qt.CheckState.Checked else Qt.CheckState.Checked
        if self.drive_model.setData(index, new_value, int(Qt.ItemDataRole.CheckStateRole)):
            self.schedule_preflight()

    def _handle_preflight_event(self, event: object) -> None:
        if not isinstance(event, PreflightReady):
            return
        if event.request_token != self._request_token or event.result is None:
            return

        result = event.result
        if result.inventory is not None:
            self.drive_model.set_drives(result.inventory.disks)
        self._render_preflight(result)
        if result.errors:
            self._set_phase(AppPhase.ERROR, result.errors[0])
        elif self._session_running:
            self._set_phase(AppPhase.RUNNING, "The session is still running.")
        else:
            self._set_phase(AppPhase.IDLE, "Preflight is ready.")

    def _handle_session_event(self, event: object) -> None:
        if isinstance(event, SessionLogEvent):
            self._buffer_log(f"[{event.status.upper()}] {event.title}\n{event.detail}\n")
            return

        if isinstance(event, SessionProgressEvent):
            ratio = 0 if event.total == 0 else int(max(0.0, min(1.0, event.current / event.total)) * 100)
            self.progress_bar.setValue(ratio)
            self.progress_label.setText(f"{ratio}%")
            self.state.progress = ratio / 100
            return

        if isinstance(event, SessionCompleted):
            self._session_running = False
            if event.bundle is not None:
                self.state.latest_report_paths = dict(event.bundle.report_paths)
                self.report_text.setPlainText(self._session_summary(event.bundle))
                self.tabs.setCurrentWidget(self.report_text)
            self._set_phase(AppPhase.COMPLETE, "The session completed. Final reports are ready.")
            self._set_controls_enabled(True)
            self.schedule_preflight(force_inventory_refresh=True, immediate=False)
            return

        if isinstance(event, SessionFailed):
            self._session_running = False
            self._set_phase(AppPhase.ERROR, event.message)
            self._buffer_log(f"[ERROR] SYSTEM\n{event.message}\n")
            self._set_controls_enabled(True)
            QMessageBox.critical(self, "OMEGA Protocol", event.message)

    def _render_preflight(self, result: PreflightResult) -> None:
        lines = [
            f"Mode: {result.mode.value}",
            f"Dry run: {result.dry_run}",
            f"Planned targets: {len(result.plans)}",
        ]
        if result.inventory is not None:
            source = "cached" if result.inventory.from_cache else "fresh"
            lines.append(f"Drive inventory entries: {len(result.inventory.disks)} ({source})")
            if result.inventory.warning:
                lines.append(f"Inventory status: {result.inventory.warning}")
        if result.warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(f"  - {warning}" for warning in result.warnings)
        if result.errors:
            lines.extend(["", "Errors:"])
            lines.extend(f"  - {error}" for error in result.errors)

        for plan in result.plans:
            lines.extend(
                [
                    "",
                    f"[{plan.display_name}]",
                    f"Target: {plan.target}",
                    f"Assurance target: {plan.assurance_target.value}",
                    f"Method: {plan.method_name}",
                    f"Executable: {plan.executable}",
                    f"Requires admin: {plan.requires_admin}",
                    f"Requires offline: {plan.requires_offline}",
                    f"Rationale: {plan.rationale}",
                ],
            )
            if plan.restrictions:
                lines.append("Restrictions:")
                lines.extend(f"  - {item}" for item in plan.restrictions)
            if plan.warnings:
                lines.append("Warnings:")
                lines.extend(f"  - {item}" for item in plan.warnings)

        if not result.plans and self.state.mode is OperationMode.DRIVE_SANITIZE and result.inventory is not None:
            lines.extend(
                [
                    "",
                    "Drive inventory is visible. Select a checkable physical disk entry when it becomes available.",
                ],
            )

        self.preflight_text.setPlainText("\n".join(lines))
        self._update_risk_card()

    def _session_summary(self, bundle: SessionBundle) -> str:
        lines = [
            f"Session ID: {bundle.session_id}",
            f"Generated: {bundle.generated_at}",
            f"Mode: {bundle.mode.value}",
            f"Dry run: {bundle.dry_run}",
            f"Native backend: {bundle.native_bridge_state}",
            "",
            "Artifacts:",
        ]
        
        for key, value in bundle.report_paths.items():
            lines.append(f"  - {key}: {value}")
        lines.extend(["", "Results:"])
        for result in bundle.results:
            lines.extend(
                [
                    f"  - {result.display_name}",
                    f"    success={result.success}",
                    f"    assurance={result.assurance_achieved.value}",
                    f"    method={result.method_name}",
                    f"    summary={result.summary}",
                ],
            )
        return "\n".join(lines)

    def _update_risk_card(self) -> None:
        if self.dry_run_checkbox.isChecked():
            self.risk_card.setText(
                "Dry run is enabled.\nYou can review the workflow without changing data.",
            )
            self.risk_card.setStyleSheet(SAFE_RISK_STYLE)
            return
        self.risk_card.setText(
            "Execution mode is enabled.\nUse Dry Run when you want to preview the workflow without changing data.",
        )
        self.risk_card.setStyleSheet(CRITICAL_RISK_STYLE)

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.files_mode_button,
            self.drives_mode_button,
            self.dry_run_checkbox,
            self.add_files_button,
            self.remove_files_button,
            self.refresh_inventory_button,
            self.clear_button,
            self.help_button,
            self.execute_button,
        ):
            widget.setEnabled(enabled)

    def _set_phase(self, phase: AppPhase, copy: str) -> None:
        self.state.phase = phase
        self.state.status_text = copy
        if phase is AppPhase.IDLE:
            badge_text, color, background = "READY", "#56d4ff", "#10273a"
        elif phase is AppPhase.PREFLIGHT:
            badge_text, color, background = "PREFLIGHT", "#f4c86b", "#33270d"
        elif phase is AppPhase.RUNNING:
            badge_text, color, background = "RUNNING", "#f4c86b", "#33270d"
        elif phase is AppPhase.COMPLETE:
            badge_text, color, background = "COMPLETE", "#69f0ad", "#0e2d22"
        else:
            badge_text, color, background = "ERROR", "#ff828e", "#31131a"

        self.state_badge.setText(badge_text)
        self.state_badge.setStyleSheet(
            f"background:{background};color:{color};border-radius:999px;"
            "padding:8px 14px;font-weight:700;",
        )
        self.state_copy.setText(copy)
        self.state.progress = self.progress_bar.value() / 100 if self.progress_bar.maximum() else 0.0

    def _buffer_log(self, message: str) -> None:
        self._log_buffer.append(message.rstrip() + "\n")

    def _flush_logs(self) -> None:
        if not self._log_buffer:
            return
        self.log_view.appendPlainText("\n".join(self._log_buffer))
        self._log_buffer.clear()

    def open_user_guide(self) -> None:
        """Open the bundled end-user guide."""

        guide_path = packaged_resource("omega_protocol", "help", "user_guide.html")
        if not guide_path.exists():
            QMessageBox.warning(self, "OMEGA Protocol", "The user guide could not be found in this build.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(guide_path)))

    def restart_as_administrator(self) -> None:
        """Relaunch the application with elevation."""

        if is_windows_admin():
            QMessageBox.information(self, "OMEGA Protocol", "The application is already running as administrator.")
            return

        executable = sys.executable
        arguments = ""
        if not getattr(sys, "frozen", False):
            script_path = application_root() / "OMEGA_BETA.py"
            arguments = f'"{script_path}"'

        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            arguments or None,
            str(application_root()),
            1,
        )
        if int(result) <= 32:
            QMessageBox.warning(
                self,
                "OMEGA Protocol",
                "Elevation was not granted. Drive inventory may remain limited until the app is restarted as administrator.",
            )
            return
        self.close()


def create_application() -> QApplication:
    """Create or reuse the QApplication instance."""

    app = QApplication.instance()
    existing = app if isinstance(app, QApplication) else QApplication(sys.argv)
    existing.setStyle("Fusion")
    existing.setApplicationName("OMEGA Protocol")
    existing.setOrganizationName("OMEGA")
    return existing


def run() -> int:
    """Run the Qt desktop application."""

    app = create_application()
    window = OmegaMainWindow()
    window.show()
    return app.exec()


def main() -> int:
    """Console-friendly wrapper used by entrypoints."""

    return run()
