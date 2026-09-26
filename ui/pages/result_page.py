#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QSpinBox, QComboBox, QPushButton, QApplication,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from core.constants import FONT_FAMILY
from core.analytics import region_stats, filter_by_region, filter_by_latency
from core.scanner import effective_latency_threshold
from ui.widgets import Card, RegionChips, FunnelBar
from ui.styles import (
    FONT_SMALL, TABLE_LIGHT_STYLE, C_BLUE, C_ORANGE, C_MUTED,
    btn_stylesheet, ghost_btn_stylesheet,
)


class ResultPage(QWidget):
    """结果页：漏斗 + 地区芯片 + 扫描结果表格 + 测速入口。"""

    single_speed_requested = Signal(object)  # ip_info dict
    region_speed_requested = Signal(list)    # 选中的地区码
    full_speed_requested = Signal()
    export_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_results: List[Dict] = []
        self.scan_mode = "tcping"
        self._checked_ips: set = set()
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        # ---- 漏斗 ----
        funnel_card = Card()
        row = QHBoxLayout()
        row.setSpacing(10)
        self.funnel_bar = FunnelBar()
        row.addWidget(self.funnel_bar)
        row.addStretch()
        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet(f"color: {C_MUTED}; font-size: 12px; border: none; background: transparent;")
        row.addWidget(self.lbl_summary)
        funnel_card.body().addLayout(row)
        outer.addWidget(funnel_card)

        # ---- 地区芯片 ----
        chips_card = Card("地区分布（点击过滤）")
        self.chips = RegionChips()
        chips_card.body().addWidget(self.chips)
        outer.addWidget(chips_card)

        # ---- 表格 ----
        table_card = Card("扫描结果")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.chk_latency = QCheckBox("仅显示延迟 <")
        self.chk_latency.setChecked(True)
        self.spin_latency = QSpinBox()
        self.spin_latency.setRange(50, 9999)
        self.spin_latency.setValue(200)
        self.spin_latency.setFixedHeight(28)
        self.spin_latency.setSuffix(" ms")

        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["按延迟升序", "按地区排序"])
        self.combo_sort.setFixedHeight(28)

        toolbar.addWidget(self.chk_latency)
        toolbar.addWidget(self.spin_latency)
        toolbar.addWidget(self.combo_sort)
        toolbar.addStretch()

        self.btn_single = QPushButton("🎯 单点测速")
        self.btn_region = QPushButton("🚀 测速所选地区")
        self.btn_full = QPushButton("⬆ 完全测速")
        self.btn_export = QPushButton("⬇ 导出")
        for b, color in ((self.btn_single, None), (self.btn_region, C_ORANGE),
                         (self.btn_full, C_BLUE), (self.btn_export, None)):
            b.setFixedHeight(30)
            b.setFont(FONT_SMALL)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(ghost_btn_stylesheet() if color is None else btn_stylesheet(color))
        self.btn_single.clicked.connect(self._on_single)
        self.btn_region.clicked.connect(self._on_region)
        self.btn_full.clicked.connect(self.full_speed_requested.emit)
        self.btn_export.clicked.connect(self.export_requested.emit)

        toolbar.addWidget(self.btn_single)
        toolbar.addWidget(self.btn_region)
        toolbar.addWidget(self.btn_full)
        toolbar.addWidget(self.btn_export)
        table_card.body().addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["", "IP 地址", "地区", "延迟", "端口", "扫描时间"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setStyleSheet(TABLE_LIGHT_STYLE)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.doubleClicked.connect(self._copy_cell)
        self.table.itemChanged.connect(self._on_item_changed)
        table_card.body().addWidget(self.table, 1)
        outer.addWidget(table_card, 1)

        self.chk_latency.stateChanged.connect(self._refresh_table)
        self.spin_latency.valueChanged.connect(self._refresh_table)
        self.combo_sort.currentTextChanged.connect(self._refresh_table)
        self.chips.selection_changed.connect(lambda _c: self._refresh_table())

    # ---------------- 数据 ----------------
    def set_results(self, results: List[Dict], funnel: dict = None, scan_mode: str = "tcping"):
        self.all_results = list(results or [])
        self.scan_mode = scan_mode or "tcping"
        # 换了一批数据：清空旧的勾选，避免把勾选状态带到不相关的 IP 上
        valid_ips = {r.get("ip") for r in self.all_results}
        self._checked_ips &= valid_ips

        # 过滤阈值同步到当前最大延迟，避免刚扫完就被默认值藏掉全部结果
        if self.all_results:
            max_lat = max((r.get("latency") or 0) for r in self.all_results)
            value = min(9999, max(50, int(max_lat) + 1))
            self.spin_latency.blockSignals(True)
            self.spin_latency.setValue(value)
            self.spin_latency.blockSignals(False)

        stats = region_stats(self.all_results)
        self.chips.set_stats(stats)

        # 漏斗
        funnel = funnel or {}
        steps = []
        if funnel.get("generated"):
            steps.append(("生成", funnel["generated"]))
            steps.append(("延迟达标", funnel.get("latency_ok", 0)))
            steps.append(("地区解析", funnel.get("with_iata", 0)))
        steps.append(("可用", len(self.all_results)))
        self.funnel_bar.set_steps(steps)

        mode_txt = "HTTPing" if self.scan_mode == "httping" else "TCPing"
        self.lbl_summary.setText(f"共 {len(self.all_results)} 个 IP · 模式 {mode_txt}")
        self._refresh_table()

    def _latency_factor(self) -> float:
        """延迟换算系数：以当前结果的扫描方式与端口为准（结果页内部口径统一）。"""
        if not self.all_results:
            return 1.0
        port = self.all_results[0].get("port", 443)
        return effective_latency_threshold(100, self.scan_mode, port) / 100.0

    def _visible_results(self) -> List[Dict]:
        data = self.all_results
        codes = self.chips.selected_codes()
        if codes:
            data = [r for r in data if (r.get("iata_code") or "").upper() in codes]
        if self.chk_latency.isChecked():
            limit = effective_latency_threshold(self.spin_latency.value(),
                                                self.scan_mode, self.current_port())
            data = filter_by_latency(data, limit)
        if self.combo_sort.currentText() == "按地区排序":
            data = sorted(data, key=lambda r: (r.get("iata_code") or "zzz", r.get("latency", 0)))
        else:
            data = sorted(data, key=lambda r: r.get("latency", 0))
        return data

    def current_port(self) -> int:
        return self.all_results[0].get("port", 443) if self.all_results else 443

    def _refresh_table(self):
        data = self._visible_results()
        factor = self._latency_factor()

        self._loading_table = True
        try:
            self.table.setRowCount(len(data))
            for i, r in enumerate(data):
                chk = QTableWidgetItem()
                chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                chk.setCheckState(Qt.Checked if r.get("ip") in self._checked_ips else Qt.Unchecked)
                chk.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, 0, chk)

                self.table.setItem(i, 1, QTableWidgetItem(r.get("ip", "")))

                code = r.get("iata_code") or ""
                name = r.get("chinese_name", code) if code else "未知"
                region_item = QTableWidgetItem(f"{name} ({code})" if code else name)
                region_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, 2, region_item)

                latency = r.get("latency", 0)
                lat_item = QTableWidgetItem(f"{latency:.1f} ms")
                lat_item.setTextAlignment(Qt.AlignCenter)
                if latency < 100 * factor:
                    lat_item.setForeground(QColor("#22C55E"))
                elif latency < 200 * factor:
                    lat_item.setForeground(QColor("#F97316"))
                else:
                    lat_item.setForeground(QColor("#EF4444"))
                self.table.setItem(i, 3, lat_item)

                port_item = QTableWidgetItem(str(r.get("port", "")))
                port_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, 4, port_item)

                time_item = QTableWidgetItem(r.get("scan_time", ""))
                time_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, 5, time_item)
        finally:
            self._loading_table = False

        self.lbl_summary.setText(
            f"显示 {len(data)} / {len(self.all_results)} 个 IP"
            + (f" · 模式 {'HTTPing' if self.scan_mode == 'httping' else 'TCPing'}")
        )

    def _on_item_changed(self, item):
        """记录勾选状态：刷新表格/切换排序后勾选不丢失。"""
        if getattr(self, "_loading_table", False) or item.column() != 0:
            return
        ip_item = self.table.item(item.row(), 1)
        if not ip_item:
            return
        ip = ip_item.text()
        if item.checkState() == Qt.Checked:
            self._checked_ips.add(ip)
        else:
            self._checked_ips.discard(ip)

    # ---------------- 交互 ----------------
    def _row_info(self) -> Optional[dict]:
        row = self.table.currentRow()
        if row < 0:
            return None
        ip = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
        for r in self._visible_results():
            if r.get("ip") == ip:
                return r
        return None

    def checked_ip_infos(self) -> List[dict]:
        visible = self._visible_results()
        out = []
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item and item.checkState() == Qt.Checked:
                ip = self.table.item(i, 1).text() if self.table.item(i, 1) else ""
                for r in visible:
                    if r.get("ip") == ip:
                        out.append(r)
                        break
        return out

    def _on_single(self):
        infos = self.checked_ip_infos()
        if not infos:
            cur = self._row_info()
            infos = [cur] if cur else []
        if not infos:
            from ui.dialogs import CustomMessageBox
            CustomMessageBox.warning(self, "提示", "请先勾选或选中一行 IP")
            return
        if len(infos) == 1:
            self.single_speed_requested.emit(infos[0])
        else:
            self.single_speed_requested.emit({"_multiple": infos})

    def _on_region(self):
        codes = self.chips.selected_codes()
        if not codes:
            from ui.dialogs import CustomMessageBox
            CustomMessageBox.warning(self, "提示", "请先点选上方地区芯片（可多选）")
            return
        self.region_speed_requested.emit(codes)

    def _copy_cell(self, index):
        item = self.table.item(index.row(), index.column())
        if item and item.text():
            QApplication.clipboard().setText(item.text())

    def set_busy(self, busy: bool):
        for b in (self.btn_single, self.btn_region, self.btn_full, self.btn_export):
            b.setEnabled(not busy)

    def set_empty(self):
        self.all_results = []
        self._checked_ips = set()
        self.chips.set_stats([])
        self.funnel_bar.clear()
        self.lbl_summary.setText("")
        self.table.setRowCount(0)
