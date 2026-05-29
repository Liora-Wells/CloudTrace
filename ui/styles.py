#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PySide6.QtGui import QFont
from core.constants import FONT_FAMILY


FONT_TITLE = QFont(FONT_FAMILY, 28)
FONT_TITLE.setBold(True)
FONT_BTN = QFont(FONT_FAMILY, 11)
FONT_SMALL = FONT_BTN
FONT_STATUS = QFont(FONT_FAMILY, 10)
FONT_LABEL = QFont(FONT_FAMILY, 10)


SCROLLBAR_CSS = f"""
QScrollBar:vertical {{ background: #0F4C75; width: 8px; border-radius: 3px; }}
QScrollBar::handle:vertical {{ background: #1E90FF; min-height: 20px; border-radius: 3px; }}
QScrollBar::handle:vertical:hover {{ background: #00BFFF; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""

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


def btn_stylesheet(color: str, text_color: str = "white", hover_color: str = None) -> str:
    if hover_color is None:
        hover_color = color
    return f"""
    QPushButton {{
        background: {color}; color: {text_color}; border-radius: 6px;
        font-family: "{FONT_FAMILY}"; border: none;
    }}
    QPushButton:disabled {{ background: #E5E7EB; color: #9CA3AF; }}
    QPushButton:hover:!disabled {{ background: {hover_color}; border: 1px solid rgba(255,255,255,0.3); }}
    """
