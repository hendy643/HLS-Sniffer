#!/usr/bin/env python3
"""PyQt6 GUI for hls-sniffer."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import core


def find_mpv() -> str:
    """Prefer the copy the Windows installer downloads into
    <install dir>/mpv/mpv.exe (see packaging/windows/installer.iss) over
    whatever's on PATH, since most users won't have mpv installed separately."""
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).parent / "mpv" / "mpv.exe"
        if bundled.exists():
            return str(bundled)
    return shutil.which("mpv") or "mpv"


class RipWorker(QThread):
    log = pyqtSignal(str)
    finished_ok = pyqtSignal(list)
    finished_err = pyqtSignal(str)

    def __init__(self, url: str, wait: float, headed: bool, click: bool, ua: str):
        super().__init__()
        self.url = url
        self.wait = wait
        self.headed = headed
        self.click = click
        self.ua = ua

    def run(self) -> None:
        try:
            candidates = core.rip(
                self.url,
                wait=self.wait,
                headless=not self.headed,
                ua=self.ua,
                click=self.click,
                on_hit=lambda h: self.log.emit(f"[{h.ts:6.2f}s] m3u8 request: {h.url}"),
                on_status=lambda msg: self.log.emit(f"... {msg}"),
            )
        except Exception as e:
            self.finished_err.emit(str(e))
            return
        self.finished_ok.emit(candidates)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("hls-sniffer")
        self.resize(1000, 700)

        self.candidates: list[core.Candidate] = []
        self.worker: "RipWorker | None" = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # --- input row ---
        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Page URL:"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/some-page-with-a-video-embed")
        input_row.addWidget(self.url_edit, stretch=1)
        self.rip_button = QPushButton("Sniff")
        self.rip_button.clicked.connect(self.start_rip)
        input_row.addWidget(self.rip_button)
        root.addLayout(input_row)

        # --- options row ---
        opts_row = QHBoxLayout()
        opts_row.addWidget(QLabel("Wait (s):"))
        self.wait_spin = QDoubleSpinBox()
        self.wait_spin.setRange(1, 300)
        self.wait_spin.setValue(20)
        opts_row.addWidget(self.wait_spin)

        self.headed_check = QCheckBox("Show browser window")
        opts_row.addWidget(self.headed_check)

        self.click_check = QCheckBox("Try clicking play")
        self.click_check.setChecked(True)
        opts_row.addWidget(self.click_check)

        opts_row.addWidget(QLabel("User-Agent:"))
        self.ua_edit = QLineEdit(core.DEFAULT_UA)
        opts_row.addWidget(self.ua_edit, stretch=1)
        root.addLayout(opts_row)

        # --- main splitter: log | results | detail ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(splitter, stretch=1)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        splitter.addWidget(self.log_view)

        lower_split = QSplitter(Qt.Orientation.Horizontal)
        self.results_list = QListWidget()
        self.results_list.currentRowChanged.connect(self.show_detail)
        lower_split.addWidget(self.results_list)

        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        detail_layout.addWidget(self.detail_view, stretch=1)

        button_row = QHBoxLayout()
        self.copy_ffmpeg_btn = QPushButton("Copy ffmpeg command")
        self.copy_ffmpeg_btn.clicked.connect(self.copy_ffmpeg)
        self.copy_mpv_btn = QPushButton("Copy mpv command")
        self.copy_mpv_btn.clicked.connect(self.copy_mpv)
        self.play_mpv_btn = QPushButton("Play with mpv")
        self.play_mpv_btn.clicked.connect(self.play_mpv)
        button_row.addWidget(self.copy_ffmpeg_btn)
        button_row.addWidget(self.copy_mpv_btn)
        button_row.addWidget(self.play_mpv_btn)
        detail_layout.addLayout(button_row)

        lower_split.addWidget(detail_widget)
        lower_split.setSizes([350, 650])
        splitter.addWidget(lower_split)
        splitter.setSizes([200, 500])

        self.status_label = QLabel("Ready.")
        root.addWidget(self.status_label)

    def start_rip(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "hls-sniffer", "Enter a page URL first.")
            return

        self.log_view.clear()
        self.results_list.clear()
        self.detail_view.clear()
        self.candidates = []
        self.rip_button.setEnabled(False)
        self.status_label.setText("Working…")

        self.worker = RipWorker(
            url=url,
            wait=self.wait_spin.value(),
            headed=self.headed_check.isChecked(),
            click=self.click_check.isChecked(),
            ua=self.ua_edit.text().strip() or core.DEFAULT_UA,
        )
        self.worker.log.connect(self.append_log)
        self.worker.finished_ok.connect(self.on_finished)
        self.worker.finished_err.connect(self.on_error)
        self.worker.start()

    def append_log(self, msg: str) -> None:
        self.log_view.appendPlainText(msg)

    def on_error(self, msg: str) -> None:
        self.rip_button.setEnabled(True)
        self.status_label.setText("Error.")
        QMessageBox.critical(self, "hls-sniffer", msg)

    def on_finished(self, candidates: list) -> None:
        self.rip_button.setEnabled(True)
        self.candidates = candidates

        if not candidates:
            self.status_label.setText("No .m3u8 requests observed. Try 'Show browser window' or a longer wait.")
            return

        best = core.best_guess(candidates)
        for i, c in enumerate(candidates):
            flag = "  <-- best guess" if c is best else ""
            item = QListWidgetItem(f"[{c.playlist_kind or '?'}] {c.base}{flag}")
            self.results_list.addItem(item)

        self.status_label.setText(f"Found {len(candidates)} distinct playlist(s).")
        if candidates:
            self.results_list.setCurrentRow(0)

    def show_detail(self, row: int) -> None:
        if row < 0 or row >= len(self.candidates):
            self.detail_view.clear()
            return
        c = self.candidates[row]
        ua = self.ua_edit.text().strip() or core.DEFAULT_UA
        lines = [
            f"URL: {c.url}",
            "",
            f"first seen: {c.first_ts:.2f}s   last seen: {c.last_ts:.2f}s   requests seen: {c.count}",
            f"kind: {c.playlist_kind}{'  (AES-encrypted)' if c.encrypted else ''}",
            "",
            f"status in-browser:      {c.browser_status}",
            f"status bare (no headers): {c.bare_status}",
            f"status with headers:    {c.headered_status}",
        ]
        if c.segment_check:
            lines.append(f"first segment check: {c.segment_check}")
        lines += [
            "",
            f"diagnosis: {c.diagnosis()}",
            "",
            "ffmpeg command:",
            core.ffmpeg_cmd(c, ua),
            "",
            "mpv command:",
            core.mpv_cmd(c, ua),
        ]
        self.detail_view.setPlainText("\n".join(lines))

    def _current_candidate(self) -> "core.Candidate | None":
        row = self.results_list.currentRow()
        if row < 0 or row >= len(self.candidates):
            return None
        return self.candidates[row]

    def copy_ffmpeg(self) -> None:
        c = self._current_candidate()
        if c:
            QApplication.clipboard().setText(core.ffmpeg_cmd(c, self.ua_edit.text().strip() or core.DEFAULT_UA))

    def copy_mpv(self) -> None:
        c = self._current_candidate()
        if c:
            QApplication.clipboard().setText(core.mpv_cmd(c, self.ua_edit.text().strip() or core.DEFAULT_UA))

    def play_mpv(self) -> None:
        c = self._current_candidate()
        if not c:
            return
        ua = self.ua_edit.text().strip() or core.DEFAULT_UA
        fields = ",".join(core.header_lines(c, ua))
        try:
            subprocess.Popen([find_mpv(), f"--http-header-fields={fields}", c.url])
        except FileNotFoundError:
            QMessageBox.warning(self, "hls-sniffer", "mpv wasn't found. Install it, or use the copied command with a player of your choice.")


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
