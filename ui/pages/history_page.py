#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from core.constants import FONT_FAMILY
from settings import get_history_list
from ui.widgets import Card, Segmented
from ui.styles import (
    FONT_SMALL, C_BLUE, C_RED, C_MUTED, btn_stylesheet, ghost_btn_stylesheet,
)
from ui.dialogs import CustomMessageBox


class HistoryPage(QWidget):
    """历史页：扫描/测速记录的加载、导出、删除。"""

    load_requested = Signal(str, str)     # filepath, type('scan'|'speed')
    export_requested = Signal(str, str)   # filepath, type
    delete_requested = Signal(str)        # filepath

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ip_version = 4
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        head = QHBoxLayout()
        lbl = QLabel("IP 版本")
        lbl.setProperty("class", "fieldLabel")
        lbl.setFont(FONT_SMALL)
        self.seg_version = Segmented(["IPv4", "IPv6"], 0)
        self.seg_version.indexChanged.connect(self._on_version_changed)
        head.addWidget(lbl)
        head.addWidget(self.seg_version)
        head.addStretch()
        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.setFixedHeight(28)
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setStyleSheet(ghost_btn_stylesheet())
        self.btn_refresh.clicked.connect(self.refresh)
        head.addWidget(self.btn_refresh)
        outer.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self.inner_lay = QVBoxLayout(inner)
        self.inner_lay.setContentsMargins(0, 0, 6, 0)
        self.inner_lay.setSpacing(12)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    def _on_version_changed(self, idx: int):
        self.ip_version = 4 if idx == 0 else 6
        self.refresh()

    def refresh(self):
        while self.inner_lay.count():
            item = self.inner_lay.takeAt(0)
            w = item.widget()
            if w:
                # 先脱离父级再延迟销毁，否则旧卡片在事件循环处理 deleteLater
                # 之前仍会留在界面上，出现重影/叠加。
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                sub = item.layout()
                while sub.count():
                    s = sub.takeAt(0)
                    if s.widget():
                        s.widget().setParent(None)
                        s.widget().deleteLater()

        for type_label, type_key, icon in (("扫描记录", "scan", "📡"), ("测速记录", "speed", "🚀")):
            card = Card(f"IPv{self.ip_version} {type_label}")
            history = get_history_list(self.ip_version, type_key)
            if not history:
                empty = QLabel(f"暂无{type_label}（执行一次{'扫描' if type_key == 'scan' else '测速'}后自动生成）")
                empty.setStyleSheet(f"color: {C_MUTED}; font-size: 12px; border: none; background: transparent;")
                card.body().addWidget(empty)
            else:
                for h in history:
                    card.body().addWidget(self._make_row(h, type_key, icon))
            self.inner_lay.addWidget(card)
        self.inner_lay.addStretch()

    def _make_row(self, h: dict, type_key: str, icon: str) -> QFrame:
        row = QFrame()
        row.setObjectName("card")
        row.setStyleSheet(
            "QFrame#card { background: white; border: 1px solid #E5E7EB; border-radius: 10px; }"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(12)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont(FONT_FAMILY, 14))
        lay.addWidget(icon_lbl)

        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        title = QLabel(h.get("save_time", "未知时间"))
        title.setFont(QFont(FONT_FAMILY, 10))
        title.setStyleSheet("color: #111827; border: none; background: transparent;")
        meta = QLabel(f"{h.get('count', 0)} 个 IP · {h.get('filename', '')}")
        meta.setFont(QFont(FONT_FAMILY, 8))
        meta.setStyleSheet(f"color: {C_MUTED}; border: none; background: transparent;")
        text_box.addWidget(title)
        text_box.addWidget(meta)
        lay.addLayout(text_box, 1)

        def op(text, color, primary=False):
            b = QPushButton(text)
            b.setFixedSize(60, 26)
            b.setFont(QFont(FONT_FAMILY, 9))
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(btn_stylesheet(color) if primary else ghost_btn_stylesheet())
            return b

        btn_load = op("加载", C_BLUE, primary=True)
        btn_export = op("导出", "#8B5CF6", primary=True)
        btn_del = op("删除", C_RED, primary=True)
        filepath = h["filepath"]
        # 首参必须带默认值：PySide6 的 clicked 只有 0/1 参重载，
        # 2 个参数的 lambda 会匹配失败并静默不执行（详见 ui/widgets.py 注释）。
        btn_load.clicked.connect(lambda _c=False, fp=filepath: self.load_requested.emit(fp, type_key))
        btn_export.clicked.connect(lambda _c=False, fp=filepath: self.export_requested.emit(fp, type_key))
        btn_del.clicked.connect(lambda _c=False, fp=filepath: self._confirm_delete(fp))
        lay.addWidget(btn_load)
        lay.addWidget(btn_export)
        lay.addWidget(btn_del)
        return row

    def _confirm_delete(self, filepath: str):
        ans = CustomMessageBox.question(self, "确认删除", "确定要删除这条历史记录吗？\n该操作不可恢复。",
                                        ["删除", "取消"], "取消")
        if ans == "删除":
            self.delete_requested.emit(filepath)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
