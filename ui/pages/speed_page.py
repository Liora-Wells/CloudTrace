#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit,
    QPushButton, QApplication, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from core.constants import FONT_FAMILY, AIRPORT_CODES
from ui.widgets import Card, LogTerminal
from ui.styles import (
    FONT_SMALL, TABLE_LIGHT_STYLE, C_BLUE, C_ORANGE, C_GREEN,
    btn_stylesheet, ghost_btn_stylesheet,
)
from ui.dialogs import CustomMessageBox


class SpeedPage(QWidget):
    """测速页：控制工具栏 + 排名表格 + 日志。"""

    start_region_requested = Signal()
    start_full_requested = Signal()
    export_requested = Signal()

    def __init__(self, app_settings: dict, parent=None):
        super().__init__(parent)
        self.app_settings = app_settings
        self.all_results: List[Dict] = []
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        # ---- 工具栏 ----
        card = Card("测速控制")
        bar = QHBoxLayout()
        bar.setSpacing(10)

        def labeled(text, widget):
            box = QHBoxLayout()
            box.setSpacing(5)
            lbl = QLabel(text)
            lbl.setProperty("class", "fieldLabel")
            lbl.setFont(FONT_SMALL)
            box.addWidget(lbl)
            box.addWidget(widget)
            return box

        self.input_region = QLineEdit()
        self.input_region.setFixedWidth(70)
        self.input_region.setFixedHeight(28)
        self.input_region.setAlignment(Qt.AlignCenter)
        self.input_region.setPlaceholderText("HKG")
        self.input_region.textChanged.connect(self._auto_uppercase)
        bar.addLayout(labeled("地区码", self.input_region))

        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, 50)
        self.spin_count.setValue(10)
        self.spin_count.setFixedHeight(28)
        self.spin_count.setFixedWidth(64)
        bar.addLayout(labeled("数量", self.spin_count))

        self.combo_speed_url = QComboBox()
        self.combo_speed_url.addItems(["自动测速地址", "手动输入"])
        self.combo_speed_url.setFixedHeight(28)
        self.combo_speed_url.setMinimumWidth(130)
        saved_url = self.app_settings.get("speed_url", "auto")
        self.combo_speed_url.setCurrentText("手动输入" if saved_url not in ("auto", "") else "自动测速地址")
        bar.addLayout(labeled("测速地址", self.combo_speed_url))

        self.input_speed_url = QLineEdit()
        self.input_speed_url.setFixedHeight(28)
        self.input_speed_url.setMinimumWidth(230)
        self.input_speed_url.setPlaceholderText("speed.cloudflare.com/__down?bytes=99999999")
        self.input_speed_url.setText("" if saved_url in ("auto", "") else saved_url)
        bar.addWidget(self.input_speed_url)
        self.combo_speed_url.currentTextChanged.connect(
            lambda t: self.input_speed_url.setVisible(t == "手动输入"))
        self.input_speed_url.setVisible(self.combo_speed_url.currentText() == "手动输入")

        self.chk_min_speed = QCheckBox("隐藏低于")
        self.spin_min_speed = QDoubleSpinBox()
        self.spin_min_speed.setRange(0, 200)
        self.spin_min_speed.setDecimals(1)
        self.spin_min_speed.setSuffix(" MB/s")
        self.spin_min_speed.setFixedHeight(28)
        self.spin_min_speed.setFixedWidth(110)
        bar.addWidget(self.chk_min_speed)
        bar.addWidget(self.spin_min_speed)

        bar.addStretch()

        self.btn_region = QPushButton("🌸 地区测速")
        self.btn_full = QPushButton("⬆ 完全测速")
        self.btn_export = QPushButton("⬇ 导出结果")
        self.btn_region.setFixedHeight(30)
        self.btn_full.setFixedHeight(30)
        self.btn_export.setFixedHeight(30)
        for b in (self.btn_region, self.btn_full, self.btn_export):
            b.setFont(FONT_SMALL)
            b.setCursor(Qt.PointingHandCursor)
        self.btn_region.setStyleSheet(btn_stylesheet(C_ORANGE))
        self.btn_full.setStyleSheet(btn_stylesheet(C_BLUE))
        self.btn_export.setStyleSheet(btn_stylesheet(C_GREEN))
        self.btn_region.clicked.connect(self._on_region)
        self.btn_full.clicked.connect(self.start_full_requested.emit)
        self.btn_export.clicked.connect(self.export_requested.emit)
        bar.addWidget(self.btn_region)
        bar.addWidget(self.btn_full)
        bar.addWidget(self.btn_export)

        card.body().addLayout(bar)
        outer.addWidget(card)

        self.chk_min_speed.stateChanged.connect(self._refresh_table)
        self.spin_min_speed.valueChanged.connect(self._refresh_table)

        # ---- 表格 ----
        table_card = Card("测速结果")
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["排名", "IP 地址", "地区", "延迟", "下载速度", "综合评分", "端口", "测速类型"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setStyleSheet(TABLE_LIGHT_STYLE)
        for i in range(7):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.doubleClicked.connect(self._copy_cell)
        table_card.body().addWidget(self.table, 1)
        outer.addWidget(table_card, 1)

        # ---- 日志 ----
        self.terminal = LogTerminal("测速日志")
        outer.addWidget(self.terminal)

        self.setStyleSheet(
            "QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: white;"
            " color: #111827; border: 1px solid #D1D5DB; border-radius: 6px;"
            f" padding: 4px 7px; font-family: '{FONT_FAMILY}'; }}"
            "QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus"
            " { border: 1px solid #2563EB; }"
            "QComboBox::drop-down { border: none; width: 20px; }"
            "QLabel { color: #374151; font-size: 12px; }"
            "QCheckBox { color: #374151; font-size: 12px; spacing: 5px; }"
            "QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px;"
            " border: 1px solid #D1D5DB; background: white; }"
            "QCheckBox::indicator:checked { background: #2563EB; border: 1px solid #2563EB; }"
        )

    # ---------------- 交互 ----------------
    def _auto_uppercase(self, text):
        if text != text.upper():
            self.input_region.blockSignals(True)
            pos = self.input_region.cursorPosition()
            self.input_region.setText(text.upper())
            self.input_region.setCursorPosition(pos)
            self.input_region.blockSignals(False)

    def _on_region(self):
        region = self.input_region.text().strip().upper()
        if not region:
            CustomMessageBox.warning(self, "提示", "请输入地区码（如 HKG, NRT, SIN）")
            return
        self.start_region_requested.emit()

    # ---------------- 参数 ----------------
    def collect(self) -> dict:
        if self.combo_speed_url.currentText() == "手动输入":
            url = self.input_speed_url.text().strip() or "auto"
        else:
            url = "auto"
        return {
            "region": self.input_region.text().strip().upper(),
            "count": self.spin_count.value(),
            "speed_url": url,
            "min_speed": self.spin_min_speed.value() if self.chk_min_speed.isChecked() else 0,
        }

    def health_snapshot(self) -> dict:
        return {"min_speed": self.collect()["min_speed"], "speed_url": self.collect()["speed_url"]}

    # ---------------- 数据 ----------------
    def set_results(self, results: List[Dict]):
        self.all_results = list(results or [])
        self._refresh_table()

    def _visible_results(self) -> List[Dict]:
        data = self.all_results
        if self.chk_min_speed.isChecked():
            limit = self.spin_min_speed.value()
            data = [r for r in data if (r.get("download_speed") or 0) >= limit]
        return data

    def _refresh_table(self):
        data = self._visible_results()
        self.table.setRowCount(len(data))
        rank_colors = {0: QColor("#D4A017"), 1: QColor("#9AA0A6"), 2: QColor("#B87333")}

        for i, r in enumerate(data):
            rank_item = QTableWidgetItem(str(i + 1))
            rank_item.setTextAlignment(Qt.AlignCenter)
            if i in rank_colors:
                rank_item.setForeground(rank_colors[i])
                font = rank_item.font()
                font.setBold(True)
                rank_item.setFont(font)
            self.table.setItem(i, 0, rank_item)

            self.table.setItem(i, 1, QTableWidgetItem(r.get("ip", "")))

            code = r.get("iata_code", "") or ""
            name = r.get("chinese_name", AIRPORT_CODES.get(code, "未知"))
            verify_mark = ""
            if r.get("verified") is True:
                verify_mark = "✓ "
            elif r.get("verified") is False:
                verify_mark = "✗ "
            region_item = QTableWidgetItem(f"{verify_mark}{name}({code})")
            region_item.setTextAlignment(Qt.AlignCenter)
            if r.get("verified") is False:
                region_item.setForeground(QColor("#EF4444"))
            self.table.setItem(i, 2, region_item)

            latency = r.get("latency", 0)
            lat_item = QTableWidgetItem(f"{latency:.1f} ms")
            lat_item.setTextAlignment(Qt.AlignCenter)
            if latency < 100:
                lat_item.setForeground(QColor("#22C55E"))
            elif latency < 200:
                lat_item.setForeground(QColor("#F97316"))
            else:
                lat_item.setForeground(QColor("#EF4444"))
            self.table.setItem(i, 3, lat_item)

            speed = r.get("download_speed", 0)
            speed_item = QTableWidgetItem(f"{speed:.2f} MB/s")
            speed_item.setTextAlignment(Qt.AlignCenter)
            if speed >= 10:
                speed_item.setForeground(QColor("#22C55E"))
            elif speed >= 5:
                speed_item.setForeground(QColor("#F97316"))
            else:
                speed_item.setForeground(QColor("#EF4444"))
            self.table.setItem(i, 4, speed_item)

            score = r.get("score", 0)
            score_item = QTableWidgetItem(f"{score:.1f}")
            score_item.setTextAlignment(Qt.AlignCenter)
            if i in rank_colors:
                font = score_item.font()
                font.setBold(True)
                score_item.setFont(font)
            self.table.setItem(i, 5, score_item)

            port_item = QTableWidgetItem(str(r.get("port", "")))
            port_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 6, port_item)

            self.table.setItem(i, 7, QTableWidgetItem(r.get("test_type", "")))

    def _copy_cell(self, index):
        item = self.table.item(index.row(), index.column())
        if item and item.text():
            QApplication.clipboard().setText(item.text())

    def set_busy(self, busy: bool):
        for b in (self.btn_region, self.btn_full, self.btn_export):
            b.setEnabled(not busy)

    def log(self, msg: str):
        self.terminal.append_line(msg)
