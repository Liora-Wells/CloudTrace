#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PySide6.QtGui import QFont
from core.constants import FONT_FAMILY


FONT_TITLE = QFont(FONT_FAMILY, 20)
FONT_TITLE.setBold(True)
FONT_BTN = QFont(FONT_FAMILY, 11)
FONT_SMALL = FONT_BTN
FONT_STATUS = QFont(FONT_FAMILY, 10)
FONT_LABEL = QFont(FONT_FAMILY, 10)

# 设计稿配色
C_BLUE = "#2563EB"
C_NAVY = "#0F2B44"
C_NAVY2 = "#1E3A5F"
C_BG = "#F9FAFB"
C_CARD = "#FFFFFF"
C_BORDER = "#E5E7EB"
C_TEXT = "#111827"
C_MUTED = "#6B7280"
C_GREEN = "#22C55E"
C_ORANGE = "#F97316"
C_RED = "#EF4444"


SCROLLBAR_CSS = f"""
QScrollBar:vertical {{ background: #EEF1F5; width: 8px; border-radius: 4px; }}
QScrollBar::handle:vertical {{ background: #C4CBD6; min-height: 20px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: #A8B2C1; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{ background: #EEF1F5; height: 8px; border-radius: 4px; }}
QScrollBar::handle:horizontal {{ background: #C4CBD6; min-width: 20px; border-radius: 4px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
"""

# ---- 兼容旧版 ----
TABLE_STYLE = f"""
QTableWidget {{
    background: #0B3C5D; border-radius: 8px; color: white;
    gridline-color: #1E4D6B;
}}
QHeaderView::section {{
    background: #0F4C75; color: white; border: none; height: 32px;
    padding-left: 10px; font-family: "{FONT_FAMILY}";
}}
QTableWidget::item {{
    padding: 5px; border-bottom: 1px solid #1E4D6B;
    font-family: "{FONT_FAMILY}", sans-serif;
}}
{SCROLLBAR_CSS}
"""

LOG_STYLE = f"""
QTextEdit {{
    background: #0B3C5D; border: 1px solid #0F4C75; border-radius: 6px;
    padding: 10px; color: #ECF0F1; font-family: "{FONT_FAMILY}", sans-serif;
}}
{SCROLLBAR_CSS}
"""

# ---- 新版（浅色表格，设计稿风格） ----
TABLE_LIGHT_STYLE = f"""
QTableWidget {{
    background: white; border: 1px solid {C_BORDER}; border-radius: 8px;
    gridline-color: #F3F4F6; color: {C_TEXT};
    font-family: "{FONT_FAMILY}"; selection-background-color: #DBEAFE;
    selection-color: {C_TEXT}; alternate-background-color: #FAFBFC;
}}
QHeaderView::section {{
    background: {C_BG}; color: {C_MUTED}; border: none;
    border-bottom: 1px solid {C_BORDER}; height: 32px;
    padding-left: 10px; font-family: "{FONT_FAMILY}"; font-size: 12px;
}}
QTableWidget::item {{ padding: 6px; border-bottom: 1px solid #F3F4F6; }}
QTableWidget::item:selected {{ background: #DBEAFE; color: {C_TEXT}; }}
{SCROLLBAR_CSS}
"""

TERMINAL_STYLE = f"""
QPlainTextEdit {{
    background: #0D1117; border: 1px solid #161B22; border-radius: 8px;
    padding: 8px 10px; color: #C9D1D9;
    font-family: Consolas, "Courier New", monospace; font-size: 12px;
}}
{SCROLLBAR_CSS}
"""

SIDEBAR_STYLE = f"""
QFrame#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
    stop:0 {C_NAVY}, stop:1 {C_NAVY2});
}}
QPushButton[class="nav"] {{
    background: transparent; color: rgba(255,255,255,180);
    border: none; border-radius: 10px;
    font-family: "{FONT_FAMILY}"; font-size: 12px; padding: 10px 0;
}}
QPushButton[class="nav"]:hover {{ background: rgba(255,255,255,10); color: white; }}
QPushButton[class="nav"]:checked {{
    background: {C_BLUE}; color: white;
}}
"""

CARD_STYLE = f"""
QFrame#card {{
    background: {C_CARD}; border: 1px solid {C_BORDER}; border-radius: 12px;
}}
QLabel#cardTitle {{
    color: {C_MUTED}; font-size: 12px; font-weight: 600;
    font-family: "{FONT_FAMILY}"; background: transparent; border: none;
}}
"""

FIELD_STYLE = f"""
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: white; color: {C_TEXT};
    border: 1px solid #D1D5DB; border-radius: 6px;
    padding: 5px 8px; font-family: "{FONT_FAMILY}";
    selection-background-color: {C_BLUE}; selection-color: white;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {C_BLUE};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QLabel.fieldLabel {{
    color: #374151; font-size: 12px; font-weight: 500;
    font-family: "{FONT_FAMILY}"; background: transparent; border: none;
}}
QCheckBox {{
    color: #374151; font-size: 12px; font-family: "{FONT_FAMILY}";
    background: transparent; border: none; spacing: 6px;
}}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 3px;
    border: 1px solid #D1D5DB; background: white;
}}
QCheckBox::indicator:checked {{ background: {C_BLUE}; border: 1px solid {C_BLUE}; }}
"""

CHIP_STYLE = f"""
QPushButton[class="chip"] {{
    background: white; color: #374151;
    border: 1px solid {C_BORDER}; border-radius: 999px;
    padding: 5px 13px; font-size: 12px; font-family: "{FONT_FAMILY}";
}}
QPushButton[class="chip"]:hover {{ border-color: {C_BLUE}; color: {C_BLUE}; }}
QPushButton[class="chip"]:checked {{
    background: {C_BLUE}; border: 1px solid {C_BLUE}; color: white;
}}
"""

SEG_STYLE = f"""
QFrame#segGroup {{ border: 1px solid #D1D5DB; border-radius: 7px; background: white; }}
QPushButton[class="seg"] {{
    background: transparent; color: #374151; border: none;
    padding: 6px 16px; font-family: "{FONT_FAMILY}"; font-size: 13px;
    border-radius: 6px;
}}
QPushButton[class="seg"]:hover {{ color: {C_BLUE}; }}
QPushButton[class="seg"]:checked {{ background: {C_BLUE}; color: white; }}
"""

PROGRESS_STYLE = f"""
QProgressBar {{ background: #E5E7EB; border: none; border-radius: 2px; }}
QProgressBar::chunk {{ background: {C_GREEN}; border-radius: 2px; }}
"""

PILL_STYLE = f"""
QLabel#statusPill {{
    background: #F3F4F6; color: {C_MUTED}; border-radius: 999px;
    padding: 3px 12px; font-size: 12px; font-family: "{FONT_FAMILY}";
}}
QLabel#statusPill[status="run"] {{ background: #DCFCE7; color: #15803D; }}
QLabel#statusPill[status="busy"] {{ background: #FEF3C7; color: #B45309; }}
QLabel#statusPill[status="error"] {{ background: #FEE2E2; color: #B91C1C; }}
"""


def btn_stylesheet(color: str, text_color: str = "white", hover_color: str = None) -> str:
    if hover_color is None:
        hover_color = color
    return f"""
    QPushButton {{
        background: {color}; color: {text_color}; border-radius: 7px;
        font-family: "{FONT_FAMILY}"; border: none; padding: 6px 14px;
    }}
    QPushButton:disabled {{ background: #E5E7EB; color: #9CA3AF; }}
    QPushButton:hover:!disabled {{ background: {hover_color}; }}
    """


def ghost_btn_stylesheet() -> str:
    return f"""
    QPushButton {{
        background: white; color: #374151; border: 1px solid #D1D5DB;
        border-radius: 7px; font-family: "{FONT_FAMILY}"; padding: 6px 14px;
    }}
    QPushButton:disabled {{ color: #9CA3AF; background: #F9FAFB; }}
    QPushButton:hover:!disabled {{ background: #F3F4F6; }}
    """
