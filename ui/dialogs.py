#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QDialog, QLabel, QPushButton, QFrame,
    QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from config import FONT_FAMILY
from ui.styles import FONT_BTN, FONT_SMALL
from storage import get_history_list


class CustomMessageBox(QDialog):
    TYPE_INFO = "info"
    TYPE_WARNING = "warning"
    TYPE_ERROR = "error"
    TYPE_QUESTION = "question"

    ICONS = {
        TYPE_INFO: "ℹ️",
        TYPE_WARNING: "⚠️",
        TYPE_ERROR: "❌",
        TYPE_QUESTION: "❓",
    }

    @classmethod
    def show(cls, parent, title: str, text: str, msg_type: str = TYPE_INFO,
             buttons: List[str] = None, default_button: str = None) -> Optional[str]:
        dlg = cls(parent, title, text, msg_type, buttons, default_button)
        if dlg.exec() == QDialog.Accepted:
            return dlg.clicked_button
        return None

    @classmethod
    def information(cls, parent, title: str, text: str):
        dlg = cls(parent, title, text, cls.TYPE_INFO, ["确定"])
        dlg.exec()

    @classmethod
    def warning(cls, parent, title: str, text: str):
        dlg = cls(parent, title, text, cls.TYPE_WARNING, ["确定"])
        dlg.exec()

    @classmethod
    def critical(cls, parent, title: str, text: str):
        dlg = cls(parent, title, text, cls.TYPE_ERROR, ["确定"])
        dlg.exec()

    @classmethod
    def question(cls, parent, title: str, text: str,
                 buttons: List[str] = None, default_button: str = None) -> Optional[str]:
        if buttons is None:
            buttons = ["是", "否"]
        dlg = cls(parent, title, text, cls.TYPE_QUESTION, buttons, default_button)
        if dlg.exec() == QDialog.Accepted:
            return dlg.clicked_button
        return None

    def __init__(self, parent, title: str, text: str, msg_type: str = TYPE_INFO,
                 buttons: List[str] = None, default_button: str = None):
        super().__init__(parent)
        self.clicked_button = None
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(380, 180)

        if buttons is None:
            buttons = ["确定"]

        bg_color = "#F9FAFB"
        border_color = "#E5E7EB"

        if msg_type == self.TYPE_WARNING:
            border_color = "#F59E0B"
        elif msg_type == self.TYPE_ERROR:
            border_color = "#EF4444"
        elif msg_type == self.TYPE_INFO:
            border_color = "#3B82F6"

        self.setStyleSheet(f"""
            QDialog {{
                background: {bg_color};
                border-radius: 12px;
                font-family: "{FONT_FAMILY}";
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setFixedHeight(4)
        header.setStyleSheet(f"background: {border_color}; border-top-left-radius: 12px; border-top-right-radius: 12px;")
        layout.addWidget(header)

        content = QFrame()
        content.setStyleSheet("QFrame { background: transparent; border: none; }")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 16, 24, 16)
        content_layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_label = QLabel(self.ICONS.get(msg_type, "ℹ️"))
        icon_label.setFont(QFont(FONT_FAMILY, 28))
        icon_label.setStyleSheet("background: transparent; border: none;")
        icon_label.setAlignment(Qt.AlignTop)
        header_row.addWidget(icon_label)

        text_label = QLabel(text)
        text_label.setFont(QFont(FONT_FAMILY, 10))
        text_label.setStyleSheet("color: #374151; background: transparent; border: none;")
        text_label.setWordWrap(True)
        text_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header_row.addWidget(text_label, 1)

        content_layout.addLayout(header_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        for btn_text in reversed(buttons):
            btn = QPushButton(btn_text)
            btn.setFixedSize(80, 32)
            btn.setFont(FONT_BTN)
            btn.setCursor(Qt.PointingHandCursor)

            is_primary = (btn_text == default_button) or (btn_text == "确定" and len(buttons) == 1)
            is_danger = (btn_text in ["是", "停止", "删除"])

            if is_danger:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #EF4444; color: white; border-radius: 6px;
                        font-family: "{FONT_FAMILY}"; border: none;
                    }}
                    QPushButton:hover {{ background: #DC2626; }}
                    QPushButton:pressed {{ background: #B91C1C; }}
                """)
            elif is_primary:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #3B82F6; color: white; border-radius: 6px;
                        font-family: "{FONT_FAMILY}"; border: none;
                    }}
                    QPushButton:hover {{ background: #2563EB; }}
                    QPushButton:pressed {{ background: #1D4ED8; }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #E5E7EB; color: #374151; border-radius: 6px;
                        font-family: "{FONT_FAMILY}"; border: none;
                    }}
                    QPushButton:hover {{ background: #D1D5DB; }}
                    QPushButton:pressed {{ background: #9CA3AF; }}
                """)

            def make_handler(btn_text=btn_text):
                def handler():
                    self.clicked_button = btn_text
                    self.accept()
                return handler

            btn.clicked.connect(make_handler(btn_text))
            btn_row.addWidget(btn)

            if btn_text == default_button:
                btn.setDefault(True)
                btn.setFocus()

        content_layout.addLayout(btn_row)
        layout.addWidget(content)


class HistorySelectDialog(QDialog):
    def __init__(self, ip_label: str, type_label: str, history: List[Dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"选择{ip_label}{type_label}历史记录")
        self.setMinimumWidth(460)
        self.setMinimumHeight(320)
        self.selected_filepath = None
        self.history = history

        self.setStyleSheet(f"""
        QDialog {{ background: #F9FAFB; font-family: "{FONT_FAMILY}", sans-serif; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        title_frame = QFrame()
        title_frame.setObjectName("dialogTitleFrame")
        title_frame.setStyleSheet("""
            #dialogTitleFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #1E3A5F, stop:1 #2563EB);
                border-radius: 8px;
            }
        """)

        title_layout = QVBoxLayout(title_frame)
        title_layout.setContentsMargins(14, 10, 14, 10)
        title_layout.setSpacing(2)

        title_text = QLabel(f"📋 {ip_label}{type_label}历史记录")
        title_text.setFont(QFont(FONT_FAMILY, 13))
        title_text.setStyleSheet("color: white; font-weight: bold; border: none; background: transparent;")
        title_layout.addWidget(title_text)

        subtitle = QLabel(f"共 {len(history)} 份记录，请选择要加载的版本")
        subtitle.setFont(FONT_SMALL)
        subtitle.setStyleSheet("color: rgba(255,255,255,180); border: none; background: transparent;")
        title_layout.addWidget(subtitle)

        layout.addWidget(title_frame)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["保存时间", "IP数量", "文件"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setRowCount(len(history))

        self.table.setStyleSheet(f"""
        QTableWidget {{
            background: white; border: 1px solid #E5E7EB; border-radius: 6px;
            gridline-color: #F3F4F6; font-family: "{FONT_FAMILY}", sans-serif;
            selection-background-color: #3B82F6; selection-color: white;
            alternate-background-color: #F9FAFB;
        }}
        QHeaderView::section {{
            background: #F3F4F6; color: #374151; border: none; height: 30px;
            padding-left: 10px; font-family: "{FONT_FAMILY}"; font-weight: bold;
            border-bottom: 2px solid #E5E7EB;
        }}
        QTableWidget::item {{ padding: 6px; border-bottom: 1px solid #F3F4F6; }}
        QTableWidget::item:selected {{ background: #3B82F6; color: white; }}
        """)

        for i, h in enumerate(history):
            time_item = QTableWidgetItem(h['save_time'])
            time_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, time_item)
            count_item = QTableWidgetItem(f"{h['count']} 个")
            count_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, count_item)
            self.table.setItem(i, 2, QTableWidgetItem(h['filename']))

        if history:
            self.table.selectRow(0)
        self.table.cellDoubleClicked.connect(self._on_accept)

        layout.addWidget(self.table, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(90, 34)
        cancel_btn.setFont(FONT_BTN)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
        QPushButton {{
            background: #F3F4F6; color: #374151; border-radius: 6px;
            font-family: "{FONT_FAMILY}"; border: 1px solid #D1D5DB;
        }}
        QPushButton:hover {{ background: #E5E7EB; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        btn_layout.addSpacing(12)

        select_btn = QPushButton("加载")
        select_btn.setFixedSize(90, 34)
        select_btn.setFont(FONT_BTN)
        select_btn.setCursor(Qt.PointingHandCursor)
        select_btn.setStyleSheet(f"""
        QPushButton {{
            background: #3B82F6; color: white; border-radius: 6px;
            font-family: "{FONT_FAMILY}"; border: none;
        }}
        QPushButton:hover {{ background: #2563EB; }}
        """)
        select_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(select_btn)

        layout.addLayout(btn_layout)

    def _on_accept(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.history):
            self.selected_filepath = self.history[row]['filepath']
            self.accept()


class ExportSelectDialog(QDialog):
    def __init__(self, has_scan: bool, has_speed: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择导出内容")
        self.setFixedSize(340, 220)
        self.choice = None

        self.setStyleSheet(f"""
        QDialog {{ background: #F9FAFB; font-family: "{FONT_FAMILY}", sans-serif; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        title = QLabel("请选择要导出的内容")
        title.setFont(QFont(FONT_FAMILY, 12))
        title.setStyleSheet("color: #111827; font-weight: bold;")
        layout.addWidget(title)

        btn_style_base = """
        QPushButton {
            border-radius: 6px; font-family: "%s"; border: none;
            padding: 8px; text-align: center;
        }
        QPushButton:hover { opacity: 0.9; }
        """ % FONT_FAMILY

        if has_scan and has_speed:
            btn_both = QPushButton("📊 扫描结果 + 测速结果（分别保存）")
            btn_both.setFixedHeight(36)
            btn_both.setFont(FONT_BTN)
            btn_both.setCursor(Qt.PointingHandCursor)
            btn_both.setStyleSheet(btn_style_base + "QPushButton { background: #3B82F6; color: white; }")
            btn_both.clicked.connect(lambda: self._choose("both"))
            layout.addWidget(btn_both)

        if has_scan:
            btn_scan = QPushButton("🔍 仅扫描结果")
            btn_scan.setFixedHeight(36)
            btn_scan.setFont(FONT_BTN)
            btn_scan.setCursor(Qt.PointingHandCursor)
            btn_scan.setStyleSheet(btn_style_base + "QPushButton { background: #22C55E; color: white; }")
            btn_scan.clicked.connect(lambda: self._choose("scan"))
            layout.addWidget(btn_scan)

        if has_speed:
            btn_speed = QPushButton("⚡ 仅测速结果")
            btn_speed.setFixedHeight(36)
            btn_speed.setFont(FONT_BTN)
            btn_speed.setCursor(Qt.PointingHandCursor)
            btn_speed.setStyleSheet(btn_style_base + "QPushButton { background: #F97316; color: white; }")
            btn_speed.clicked.connect(lambda: self._choose("speed"))
            layout.addWidget(btn_speed)

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(32)
        cancel_btn.setFont(FONT_BTN)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(btn_style_base + "QPushButton { background: #F3F4F6; color: #6B7280; border: 1px solid #D1D5DB; }")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def _choose(self, choice: str):
        self.choice = choice
        self.accept()
