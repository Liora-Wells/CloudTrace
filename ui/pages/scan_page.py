#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QComboBox, QPlainTextEdit, QPushButton, QFileDialog, QScrollArea,
    QGridLayout, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from core.constants import FONT_FAMILY, PORT_OPTIONS
from core.importer import parse_ip_list, load_entries_from_file
from core.factory import parse_cidr_lines
from settings import load_custom_cidrs, save_settings
from ui.widgets import Card, Segmented, FunnelBar, LogTerminal
from ui.styles import FONT_SMALL, FIELD_STYLE, C_BLUE, C_MUTED, btn_stylesheet
from ui.dialogs import CustomMessageBox


class ScanPage(QWidget):
    """扫描页：参数 + IP 来源 + 漏斗 + 日志终端。"""

    start_requested = Signal()

    def __init__(self, app_settings: dict, parent=None):
        super().__init__(parent)
        self.app_settings = app_settings
        self._build()

    # ---------------- UI ----------------
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(12)

        # ---- 上排：扫描参数 + IP 来源 ----
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        param_card = Card("扫描参数")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        def field(label_text, widget):
            wrap = QVBoxLayout()
            wrap.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setProperty("class", "fieldLabel")
            lbl.setFont(FONT_SMALL)
            wrap.addWidget(lbl)
            wrap.addWidget(widget)
            return wrap

        self.seg_version = Segmented(["IPv4", "IPv6"], 0)
        grid.addLayout(field("IP 版本", self.seg_version), 0, 0)

        self.combo_port = QComboBox()
        for port in PORT_OPTIONS:
            self.combo_port.addItem(port)
        self.combo_port.setCurrentText("443")
        self.combo_port.setFixedHeight(30)
        grid.addLayout(field("端口", self.combo_port), 0, 1)

        self.spin_workers = QSpinBox()
        self.spin_workers.setRange(10, 500)
        self.spin_workers.setValue(int(self.app_settings.get("workers", 200)))
        self.spin_workers.setSingleStep(50)
        self.spin_workers.setFixedHeight(30)
        grid.addLayout(field("并发数", self.spin_workers), 0, 2)

        self.spin_threshold = QSpinBox()
        self.spin_threshold.setRange(50, 999)
        self.spin_threshold.setValue(int(self.app_settings.get("latency_threshold", 230)))
        self.spin_threshold.setSingleStep(10)
        self.spin_threshold.setSuffix(" ms")
        self.spin_threshold.setFixedHeight(30)
        grid.addLayout(field("延迟阈值", self.spin_threshold), 1, 0)

        self.spin_sample = QSpinBox()
        self.spin_sample.setRange(100, 50000)
        self.spin_sample.setSingleStep(500)
        self.spin_sample.setValue(int(self.app_settings.get("sample_max", 5000)))
        self.spin_sample.setFixedHeight(30)
        grid.addLayout(field("采样上限", self.spin_sample), 1, 1)

        self.spin_ping = QSpinBox()
        self.spin_ping.setRange(0, 10)
        self.spin_ping.setValue(int(self.app_settings.get("ping_times", 0)))
        self.spin_ping.setSpecialValueText("自动")
        self.spin_ping.setFixedHeight(30)
        grid.addLayout(field("探测次数(0=自动)", self.spin_ping), 1, 2)

        self.seg_mode = Segmented(["TCPing", "HTTPing"],
                                  0 if self.app_settings.get("scan_mode", "tcping") == "tcping" else 1)
        grid.addLayout(field("扫描方式", self.seg_mode), 2, 0)

        mode_hint = QLabel("TCPing 测握手延迟；HTTPing 测 TTFB（阈值自动 ×1.3/×4.0 换算），两者数据不可比")
        mode_hint.setProperty("class", "fieldLabel")
        mode_hint.setFont(QFont(FONT_FAMILY, 8))
        mode_hint.setStyleSheet(f"color: {C_MUTED}; border: none; background: transparent;")
        mode_hint.setWordWrap(True)
        grid.addWidget(mode_hint, 3, 0, 1, 3)

        param_card.body().addLayout(grid)
        top_row.addWidget(param_card, 1)

        # ---- IP 来源 ----
        source_card = Card("IP 来源")
        source_top = QHBoxLayout()
        source_top.setSpacing(10)
        lbl = QLabel("来源模式")
        lbl.setProperty("class", "fieldLabel")
        lbl.setFont(FONT_SMALL)
        self.combo_source = QComboBox()
        self.combo_source.addItems(["仅官方", "仅自定义", "官方+自定义", "非标列表"])
        self.combo_source.setCurrentText(self.app_settings.get("cidr_mode", "仅官方"))
        self.combo_source.setFixedHeight(30)
        self.combo_source.setMinimumWidth(140)
        source_top.addWidget(lbl)
        source_top.addWidget(self.combo_source)
        source_top.addStretch()
        source_card.body().addLayout(source_top)

        self.text_cidrs = QPlainTextEdit()
        self.text_cidrs.setFont(FONT_SMALL)
        self.text_cidrs.setPlaceholderText("每行一个 CIDR，如:\n1.2.3.0/24\n2606:4700::/32")
        self.text_cidrs.setMinimumHeight(70)

        self.text_import = QPlainTextEdit()
        self.text_import.setFont(FONT_SMALL)
        self.text_import.setPlaceholderText("每行一个 IP 或 IP 端口，如:\n1.2.3.4\n5.6.7.8 8443\n2606:4700::1111")
        self.text_import.setMinimumHeight(70)

        import_btn_row = QHBoxLayout()
        self.btn_import_file = QPushButton("导入文件 (txt/csv)")
        self.btn_import_file.setCursor(Qt.PointingHandCursor)
        self.btn_import_file.setFont(FONT_SMALL)
        self.btn_import_file.setStyleSheet(btn_stylesheet(C_BLUE))
        self.btn_import_file.clicked.connect(self._import_file)
        import_hint = QLabel("未填端口时使用上方「端口」参数")
        import_hint.setStyleSheet(f"color: {C_MUTED}; font-size: 11px; border: none; background: transparent;")
        self.import_hint = import_hint
        import_btn_row.addWidget(self.btn_import_file)
        import_btn_row.addWidget(import_hint)
        import_btn_row.addStretch()

        source_card.body().addWidget(self.text_cidrs)
        source_card.body().addWidget(self.text_import)
        source_card.body().addLayout(import_btn_row)

        top_row.addWidget(source_card, 1)
        lay.addLayout(top_row)

        # ---- 漏斗 ----
        funnel_card = Card("本次扫描")
        self.funnel_bar = FunnelBar()
        funnel_card.body().addWidget(self.funnel_bar)
        lay.addWidget(funnel_card)

        # ---- 日志 ----
        self.terminal = LogTerminal("运行日志")
        lay.addWidget(self.terminal)

        # ---- 主按钮 ----
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("▶ 开始扫描")
        self.btn_start.setFixedSize(150, 38)
        self.btn_start.setFont(QFont(FONT_FAMILY, 11))
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setStyleSheet(btn_stylesheet(C_BLUE))
        self.btn_start.clicked.connect(self.start_requested.emit)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_start)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        lay.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        self.setStyleSheet(FIELD_STYLE)
        self.combo_source.currentTextChanged.connect(self._on_source_changed)
        self._on_source_changed(self.combo_source.currentText())

        saved_cidrs = load_custom_cidrs()
        if saved_cidrs:
            self.text_cidrs.setPlainText(saved_cidrs)

    def _on_source_changed(self, mode: str):
        is_import = (mode == "非标列表")
        is_custom = mode in ("仅自定义", "官方+自定义")
        self.text_cidrs.setVisible(is_custom and not is_import)
        self.text_import.setVisible(is_import)
        self.btn_import_file.setVisible(is_import)
        self.import_hint.setVisible(is_import)
        # 来源模式需要持久化，否则重启后总是回到「仅官方」（旧版行为回归）
        if self.app_settings.get("cidr_mode") != mode:
            self.app_settings["cidr_mode"] = mode
            save_settings(self.app_settings)

    def persist_scan_params(self):
        """把扫描页参数写回设置，保证下次启动沿用（不覆盖设置页拥有的 sample_max/scan_mode）。"""
        changed = False
        for key, value in (("workers", self.spin_workers.value()),
                           ("latency_threshold", self.spin_threshold.value()),
                           ("ping_times", self.spin_ping.value())):
            if self.app_settings.get(key) != value:
                self.app_settings[key] = value
                changed = True
        if changed:
            save_settings(self.app_settings)

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 IP 列表", "", "文本文件 (*.txt *.csv);;所有文件 (*)"
        )
        if not path:
            return
        entries, errors = load_entries_from_file(path, default_port=int(self.combo_port.currentText()))
        if errors:
            CustomMessageBox.warning(self, "导入部分失败", "\n".join(errors[:10]))
        if entries:
            lines = [f"{e['ip']} {e['port']}" for e in entries]
            self.text_import.setPlainText("\n".join(lines))

    # ---------------- 数据收集 ----------------
    def collect(self) -> Optional[dict]:
        """校验并返回扫描参数；失败时弹窗并返回 None。"""
        source_mode = self.combo_source.currentText()
        ip_version = 4 if self.seg_version.index() == 0 else 6

        cidrs: List[str] = []
        entries: Optional[List[dict]] = None

        if source_mode == "非标列表":
            text = self.text_import.toPlainText().strip()
            if not text:
                CustomMessageBox.warning(self, "提示", "非标列表不能为空（每行一个 IP [端口]）")
                return None
            entries, errors = parse_ip_list(text, default_port=int(self.combo_port.currentText()))
            if errors:
                CustomMessageBox.warning(self, "IP 列表格式错误", "\n".join(errors[:10]))
                return None
            if not entries:
                CustomMessageBox.warning(self, "提示", "未解析到有效的 IP")
                return None
        elif source_mode != "仅官方":
            text = self.text_cidrs.toPlainText().strip()
            if not text:
                CustomMessageBox.warning(self, "提示", "自定义 CIDR 不能为空")
                return None
            cidrs, invalid = parse_cidr_lines(text.splitlines(), ip_version)
            if invalid:
                msg = [f'第{no}行 "{val}" 不是有效的 CIDR' for no, val in invalid[:10]]
                if len(invalid) > 10:
                    msg.append(f"... 共 {len(invalid)} 行无效")
                CustomMessageBox.warning(self, "CIDR 格式错误", "\n".join(msg))
                return None
            if not cidrs:
                CustomMessageBox.warning(self, "提示", f"未找到有效的 IPv{ip_version} CIDR")
                return None

        return {
            "ip_version": ip_version,
            "source_mode": source_mode,
            "cidrs": cidrs,
            "entries": entries,
            "port": int(self.combo_port.currentText()),
            "workers": self.spin_workers.value(),
            "threshold": self.spin_threshold.value(),
            "sample_max": self.spin_sample.value(),
            "ping_times": self.spin_ping.value(),
            "scan_mode": "tcping" if self.seg_mode.index() == 0 else "httping",
            "cidr_text": self.text_cidrs.toPlainText(),
        }

    def health_snapshot(self) -> dict:
        """给配置体检用的当前扫描参数。"""
        return {
            "latency_threshold": self.spin_threshold.value(),
            "workers": self.spin_workers.value(),
            "sample_max": self.spin_sample.value(),
            "scan_mode": "tcping" if self.seg_mode.index() == 0 else "httping",
        }

    # ---------------- 状态 ----------------
    def set_funnel(self, steps: list):
        self.funnel_bar.set_steps(steps)

    def set_busy(self, busy: bool):
        self.btn_start.setEnabled(not busy)

    def log(self, msg: str):
        self.terminal.append_line(msg)
