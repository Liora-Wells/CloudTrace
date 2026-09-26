#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime
from typing import List, Tuple

from PySide6.QtWidgets import (
    QLayout, QFrame, QLabel, QPushButton, QPlainTextEdit,
    QHBoxLayout, QVBoxLayout, QWidget, QButtonGroup,
)
from PySide6.QtCore import Qt, QRect, QSize, QPoint, Signal
from PySide6.QtGui import QFont

from core.constants import FONT_FAMILY
from ui.styles import (
    SIDEBAR_STYLE, CARD_STYLE, TERMINAL_STYLE, CHIP_STYLE, SEG_STYLE,
    FONT_SMALL, FONT_BTN, C_BLUE, C_MUTED, C_GREEN, C_ORANGE, C_RED,
)


class FlowLayout(QLayout):
    """简单流式布局：控件从左到右排列，放不下自动换行。"""

    def __init__(self, parent=None, h_spacing=8, v_spacing=8):
        super().__init__(parent)
        self._items: List = []
        self._h_space = h_spacing
        self._v_space = v_spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        line_height = 0
        right = rect.right() - m.right()

        for item in self._items:
            wid = item.widget()
            space_x = self._h_space
            space_y = self._v_space
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > right and line_height > 0:
                x = rect.x() + m.left()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y() + m.bottom()


from PySide6.QtCore import QPoint  # noqa: E402


class Segmented(QWidget):
    """分段选择器（容器边框 + 内部按钮）。"""

    indexChanged = Signal(int)

    def __init__(self, items: List[str], current: int = 0, parent=None):
        super().__init__(parent)
        self._buttons: List[QPushButton] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        frame = QFrame()
        frame.setObjectName("segGroup")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(0)
        for i, text in enumerate(items):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFont(FONT_SMALL)
            btn.setProperty("class", "seg")
            lay.addWidget(btn)
            self._group.addButton(btn, i)
            self._buttons.append(btn)
            btn.clicked.connect(lambda _c, idx=i: self.indexChanged.emit(idx))

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        self.setStyleSheet(SEG_STYLE)
        self.set_index(current)

    def set_index(self, i: int):
        if 0 <= i < len(self._buttons):
            self._buttons[i].setChecked(True)

    def index(self) -> int:
        return self._group.checkedId()

    def current_text(self) -> str:
        i = self.index()
        return self._buttons[i].text() if 0 <= i < len(self._buttons) else ""


class Card(QFrame):
    """白色圆角卡片容器。"""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(CARD_STYLE)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(10)
        self._title = QLabel(title) if title else None
        if self._title:
            self._title.setObjectName("cardTitle")
            self._layout.addWidget(self._title)

    def body(self) -> QVBoxLayout:
        return self._layout


class RegionChips(QWidget):
    """地区计数芯片（点选过滤）。"""

    selection_changed = Signal(list)  # 选中的地区码列表

    def __init__(self, parent=None):
        super().__init__(parent)
        self._flow = FlowLayout(self, h_spacing=8, v_spacing=8)
        self.setLayout(self._flow)
        self._selected: set = set()
        self._codes: List[str] = []

    def set_stats(self, stats: List[dict]):
        """stats: [{'code','name','count'}]"""
        while self._flow.count():
            item = self._flow.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._codes = [s['code'] for s in stats]
        # 清掉已不存在的选中项
        self._selected &= set(self._codes)

        for s in stats:
            btn = QPushButton(f"{s['name']} {s['code']} · {s['count']}")
            btn.setCheckable(True)
            btn.setProperty("class", "chip")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFont(QFont(FONT_FAMILY, 9))
            btn.setStyleSheet(CHIP_STYLE)
            btn.setChecked(s['code'] in self._selected)
            btn.clicked.connect(lambda _c, code=s['code']: self._toggle(code))
            self._flow.addWidget(btn)

    def _toggle(self, code: str):
        if code in self._selected:
            self._selected.discard(code)
        else:
            self._selected.add(code)
        self.selection_changed.emit(self.selected_codes())

    def selected_codes(self) -> List[str]:
        return [c for c in self._codes if c in self._selected]

    def clear_selection(self):
        self._selected.clear()
        self.selection_changed.emit([])

    def select_all(self):
        self._selected = set(self._codes)
        self.selection_changed.emit(self.selected_codes())


class FunnelBar(QWidget):
    """漏斗统计条：生成 → 延迟达标 → 地区解析 → 完成。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._layout.addStretch()
        self._labels: List[QLabel] = []

    def set_steps(self, steps: List[Tuple[str, object]]):
        """steps: [(label, value)]；value 为 None 时不显示数值。"""
        while self._labels:
            lab = self._labels.pop()
            self._layout.removeWidget(lab)
            lab.deleteLater()

        for i, (label, value) in enumerate(steps):
            if i > 0:
                arr = QLabel("→")
                arr.setStyleSheet(f"color: #9CA3AF; font-size: 13px; border: none; background: transparent;")
                self._layout.insertWidget(self._layout.count() - 1, arr)
                self._labels.append(arr)
            text = label if value is None else f"{label} {value}"
            lab = QLabel(text)
            lab.setFont(QFont(FONT_FAMILY, 10))
            lab.setStyleSheet(
                "background: #EFF6FF; border: 1px solid #BFDBFE; color: #1E40AF;"
                "border-radius: 8px; padding: 5px 11px; font-family: '%s';" % FONT_FAMILY
            )
            self._layout.insertWidget(self._layout.count() - 1, lab)
            self._labels.append(lab)

    def clear(self):
        self.set_steps([])


class LogTerminal(QWidget):
    """深色终端日志（可折叠）。"""

    def __init__(self, title: str = "运行日志", parent=None):
        super().__init__(parent)
        self._max_lines = 2000

        head = QHBoxLayout()
        head.setSpacing(8)
        self._title = QLabel(title)
        self._title.setObjectName("cardTitle")
        self._toggle_btn = QPushButton("收起")
        self._toggle_btn.setFixedSize(56, 24)
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setFont(QFont(FONT_FAMILY, 9))
        self._clear_btn = QPushButton("清空")
        self._clear_btn.setFixedSize(56, 24)
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.setFont(QFont(FONT_FAMILY, 9))
        btn_style = (
            "QPushButton { background: white; border: 1px solid #D1D5DB; border-radius: 6px;"
            " color: #6B7280; } QPushButton:hover { background: #F3F4F6; }"
        )
        self._toggle_btn.setStyleSheet(btn_style)
        self._clear_btn.setStyleSheet(btn_style)
        head.addWidget(self._title)
        head.addStretch()
        head.addWidget(self._clear_btn)
        head.addWidget(self._toggle_btn)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet(TERMINAL_STYLE)
        self.output.setMinimumHeight(90)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addLayout(head)
        lay.addWidget(self.output)

        self._toggle_btn.clicked.connect(self._toggle)
        self._clear_btn.clicked.connect(self.output.clear)

    def _toggle(self):
        collapsed = self.output.isVisible()
        self.output.setVisible(not collapsed)
        self._toggle_btn.setText("展开" if collapsed else "收起")

    def append_line(self, msg: str):
        at_bottom = True
        sb = self.output.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        stamp = datetime.now().strftime("[%H:%M:%S] ")
        self.output.appendPlainText(stamp + str(msg))
        # 超出上限裁剪最旧行
        doc = self.output.document()
        if doc.blockCount() > self._max_lines:
            self.output.setPlainText(
                "\n".join(self.output.toPlainText().splitlines()[-self._max_lines:])
            )
        if at_bottom:
            sb.setValue(sb.maximum())


class SideNav(QFrame):
    """左侧导航栏。"""

    pageChanged = Signal(int)

    def __init__(self, items: List[Tuple[str, str]], parent=None):
        """items: [(icon_text, label)]"""
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(112)
        self.setStyleSheet(SIDEBAR_STYLE)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 16, 10, 12)
        lay.setSpacing(4)

        logo = QLabel("☁\nCloudTrace")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFont(QFont(FONT_FAMILY, 12))
        logo.setStyleSheet("color: white; background: transparent; border: none; font-weight: bold;")
        lay.addWidget(logo)
        lay.addSpacing(10)

        self._buttons: List[QPushButton] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, (icon, label) in enumerate(items):
            btn = QPushButton(f"{icon}\n{label}")
            btn.setCheckable(True)
            btn.setFixedHeight(56)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFont(QFont(FONT_FAMILY, 9))
            btn.setProperty("class", "nav")
            lay.addWidget(btn)
            self._group.addButton(btn, i)
            self._buttons.append(btn)
            btn.clicked.connect(lambda _c, idx=i: self.pageChanged.emit(idx))

        lay.addStretch()
        footer = QLabel("v" + _safe_version())
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: rgba(255,255,255,100); font-size: 10px; background: transparent; border: none;")
        lay.addWidget(footer)

        self.set_active(0)

    def set_active(self, i: int):
        if 0 <= i < len(self._buttons):
            self._buttons[i].setChecked(True)


def _safe_version() -> str:
    try:
        from core.constants import get_version
        return get_version()
    except Exception:
        return "?"
