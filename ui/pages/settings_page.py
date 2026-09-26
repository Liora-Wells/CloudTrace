#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Callable, Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QSpinBox,
    QDoubleSpinBox, QComboBox, QLineEdit, QPushButton, QScrollArea,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from core.constants import FONT_FAMILY
from settings import save_settings, DEFAULT_SETTINGS
from service.health import validate_settings
from ui.widgets import Card
from ui.styles import (
    FONT_SMALL, C_BLUE, C_MUTED, FIELD_STYLE, btn_stylesheet, ghost_btn_stylesheet,
)
from ui.dialogs import CustomMessageBox


class SettingsPage(QWidget):
    """设置页：分组卡片表单 + 保存/恢复/体检。"""

    saved = Signal(dict)

    def __init__(self, app_settings: dict, parent=None):
        super().__init__(parent)
        self.app_settings = app_settings
        self._providers: List[Callable[[], dict]] = []
        self._build()

    def set_param_provider(self, fn: Callable[[], dict]):
        self._providers.append(fn)

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

        grid_wrap = QHBoxLayout()
        grid_wrap.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(12)
        right = QVBoxLayout()
        right.setSpacing(12)

        s = self.app_settings

        # ---- 常规 ----
        card常规 = Card("常规")
        self.chk_tray = QCheckBox("关闭窗口时最小化到系统托盘")
        self.chk_tray.setChecked(bool(s.get("tray_on_close", False)))
        card常规.body().addWidget(self.chk_tray)
        left.addWidget(card常规)

        # ---- 扫描默认 ----
        card扫描 = Card("扫描默认值")
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        lbl1 = QLabel("扫描方式")
        lbl1.setProperty("class", "fieldLabel")
        self.combo_scan_mode = QComboBox()
        self.combo_scan_mode.addItems(["tcping", "httping"])
        self.combo_scan_mode.setCurrentText(s.get("scan_mode", "tcping"))
        row1.addWidget(lbl1)
        row1.addWidget(self.combo_scan_mode)
        row1.addStretch()
        card扫描.body().addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        lbl2 = QLabel("采样上限")
        lbl2.setProperty("class", "fieldLabel")
        self.spin_sample = QSpinBox()
        self.spin_sample.setRange(100, 50000)
        self.spin_sample.setSingleStep(500)
        self.spin_sample.setValue(int(s.get("sample_max", 5000)))
        row2.addWidget(lbl2)
        row2.addWidget(self.spin_sample)
        row2.addStretch()
        card扫描.body().addLayout(row2)
        left.addWidget(card扫描)

        # ---- 评分权重 ----
        card评分 = Card("综合评分权重")
        hint = QLabel("score = 速度权重 × MB/s ÷ (1 + 延迟权重 × 延迟秒)")
        hint.setFont(QFont(FONT_FAMILY, 8))
        hint.setStyleSheet(f"color: {C_MUTED}; border: none; background: transparent;")
        hint.setWordWrap(True)
        card评分.body().addWidget(hint)

        wrow = QHBoxLayout()
        wrow.setSpacing(8)
        lbl_ws = QLabel("速度权重")
        lbl_ws.setProperty("class", "fieldLabel")
        self.spin_w_speed = QDoubleSpinBox()
        self.spin_w_speed.setRange(0, 50)
        self.spin_w_speed.setSingleStep(0.5)
        self.spin_w_speed.setValue(float(s.get("score_speed_weight", 3.0)))
        lbl_wl = QLabel("延迟权重")
        lbl_wl.setProperty("class", "fieldLabel")
        self.spin_w_latency = QDoubleSpinBox()
        self.spin_w_latency.setRange(0, 50)
        self.spin_w_latency.setSingleStep(0.5)
        self.spin_w_latency.setValue(float(s.get("score_latency_weight", 3.0)))
        wrow.addWidget(lbl_ws)
        wrow.addWidget(self.spin_w_speed)
        wrow.addWidget(lbl_wl)
        wrow.addWidget(self.spin_w_latency)
        wrow.addStretch()
        card评分.body().addLayout(wrow)
        left.addWidget(card评分)

        # ---- 测速 ----
        card测速 = Card("测速")
        srow = QHBoxLayout()
        srow.setSpacing(8)
        lbl_url = QLabel("测速地址")
        lbl_url.setProperty("class", "fieldLabel")
        self.combo_speed_url = QComboBox()
        self.combo_speed_url.addItems(["auto", "手动输入"])
        saved_url = s.get("speed_url", "auto")
        self.combo_speed_url.setCurrentText("手动输入" if saved_url not in ("auto", "") else "auto")
        self.combo_speed_url.setFixedWidth(110)
        self.input_speed_url = QLineEdit(saved_url if saved_url not in ("auto", "") else "")
        self.input_speed_url.setPlaceholderText("speed.cloudflare.com/__down?bytes=99999999")
        self.input_speed_url.setVisible(self.combo_speed_url.currentText() == "手动输入")
        self.combo_speed_url.currentTextChanged.connect(
            lambda t: self.input_speed_url.setVisible(t == "手动输入"))
        srow.addWidget(lbl_url)
        srow.addWidget(self.combo_speed_url)
        srow.addWidget(self.input_speed_url, 1)
        card测速.body().addLayout(srow)

        self.chk_verify = QCheckBox("测速前验证节点为 Cloudflare（防劫持/非CF，稍慢更准）")
        self.chk_verify.setChecked(bool(s.get("verify_nodes", True)))
        card测速.body().addWidget(self.chk_verify)

        mrow = QHBoxLayout()
        mrow.setSpacing(8)
        lbl_min = QLabel("合格阈值")
        lbl_min.setProperty("class", "fieldLabel")
        self.spin_min_speed = QDoubleSpinBox()
        self.spin_min_speed.setRange(0, 200)
        self.spin_min_speed.setDecimals(1)
        self.spin_min_speed.setSuffix(" MB/s")
        self.spin_min_speed.setValue(float(s.get("min_speed", 0)))
        lbl_gap = QLabel("测速间隔")
        lbl_gap.setProperty("class", "fieldLabel")
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(0, 15)
        self.spin_interval.setSuffix(" s")
        self.spin_interval.setValue(int(s.get("download_interval", 3)))
        mrow.addWidget(lbl_min)
        mrow.addWidget(self.spin_min_speed)
        mrow.addWidget(lbl_gap)
        mrow.addWidget(self.spin_interval)
        mrow.addStretch()
        card测速.body().addLayout(mrow)
        left.addWidget(card测速)

        # ---- HTTP 服务面板 ----
        card_http = Card("HTTP 服务面板")
        self.chk_http = QCheckBox("启用 HTTP 服务（浏览器访问管理面板）")
        self.chk_http.setChecked(bool(s.get("http_enabled", True)))
        card_http.body().addWidget(self.chk_http)

        hrow = QHBoxLayout()
        hrow.setSpacing(8)
        lbl_port = QLabel("监听端口")
        lbl_port.setProperty("class", "fieldLabel")
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535)
        self.spin_port.setValue(int(s.get("http_port", 17443)))
        self.chk_lan = QCheckBox("允许局域网访问")
        self.chk_lan.setChecked(bool(s.get("allow_lan", False)))
        hrow.addWidget(lbl_port)
        hrow.addWidget(self.spin_port)
        hrow.addSpacing(14)
        hrow.addWidget(self.chk_lan)
        hrow.addStretch()
        card_http.body().addLayout(hrow)

        trow = QHBoxLayout()
        trow.setSpacing(8)
        lbl_token = QLabel("访问 Token")
        lbl_token.setProperty("class", "fieldLabel")
        self.input_token = QLineEdit(s.get("http_token", ""))
        self.input_token.setPlaceholderText("留空则不鉴权（仅建议本机使用）")
        self.input_token.setEchoMode(QLineEdit.Password)
        trow.addWidget(lbl_token)
        trow.addWidget(self.input_token, 1)
        card_http.body().addLayout(trow)

        self.lbl_http_hint = QLabel("")
        self.lbl_http_hint.setFont(QFont(FONT_FAMILY, 8))
        self.lbl_http_hint.setStyleSheet(f"color: {C_MUTED}; border: none; background: transparent;")
        self.lbl_http_hint.setWordWrap(True)
        card_http.body().addWidget(self.lbl_http_hint)
        right.addWidget(card_http)

        # ---- 数据 ----
        card数据 = Card("数据")
        self.lbl_data_hint = QLabel("扫描/测速结果自动保存于 CloudTrace_history，最多各保留 5 份")
        self.lbl_data_hint.setFont(QFont(FONT_FAMILY, 9))
        self.lbl_data_hint.setStyleSheet(f"color: {C_MUTED}; border: none; background: transparent;")
        self.lbl_data_hint.setWordWrap(True)
        card数据.body().addWidget(self.lbl_data_hint)
        right.addWidget(card数据)

        right.addStretch()
        grid_wrap.addLayout(left, 1)
        grid_wrap.addLayout(right, 1)
        lay.addLayout(grid_wrap)

        # ---- 按钮 ----
        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.btn_save = QPushButton("💾 保存设置")
        self.btn_restore = QPushButton("恢复默认")
        self.btn_health = QPushButton("体检配置")
        for b in (self.btn_save, self.btn_restore, self.btn_health):
            b.setFixedHeight(34)
            b.setFont(FONT_SMALL)
            b.setCursor(Qt.PointingHandCursor)
        self.btn_save.setStyleSheet(btn_stylesheet(C_BLUE))
        self.btn_restore.setStyleSheet(ghost_btn_stylesheet())
        self.btn_health.setStyleSheet(ghost_btn_stylesheet())
        self.btn_save.clicked.connect(self.save)
        self.btn_restore.clicked.connect(self.restore_defaults)
        self.btn_health.clicked.connect(self.show_health)
        btns.addWidget(self.btn_save)
        btns.addWidget(self.btn_restore)
        btns.addWidget(self.btn_health)
        btns.addStretch()
        lay.addLayout(btns)
        lay.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self.setStyleSheet(FIELD_STYLE)
        self._update_http_hint()

        self.chk_http.stateChanged.connect(lambda _s: self._update_http_hint())
        self.spin_port.valueChanged.connect(lambda _v: self._update_http_hint())

    def _update_http_hint(self):
        if self.chk_http.isChecked():
            host = "127.0.0.1" if not self.chk_lan.isChecked() else "<本机IP>"
            self.lbl_http_hint.setText(
                f"面板地址: http://{host}:{self.spin_port.value()}/  ·  "
                "桌面版与 Web 面板共享同一任务状态"
            )
        else:
            self.lbl_http_hint.setText("HTTP 服务已关闭（仅桌面版可用）")

    # ---------------- 操作 ----------------
    def _collect(self) -> dict:
        s = dict(self.app_settings)
        s["tray_on_close"] = self.chk_tray.isChecked()
        s["scan_mode"] = self.combo_scan_mode.currentText()
        s["sample_max"] = self.spin_sample.value()
        s["score_speed_weight"] = self.spin_w_speed.value()
        s["score_latency_weight"] = self.spin_w_latency.value()
        s["speed_url"] = (self.input_speed_url.text().strip()
                          if self.combo_speed_url.currentText() == "手动输入" else "auto")
        s["verify_nodes"] = self.chk_verify.isChecked()
        s["min_speed"] = self.spin_min_speed.value()
        s["download_interval"] = self.spin_interval.value()
        s["http_enabled"] = self.chk_http.isChecked()
        s["http_port"] = self.spin_port.value()
        s["allow_lan"] = self.chk_lan.isChecked()
        s["http_token"] = self.input_token.text().strip()
        return s

    def _merged_for_health(self) -> dict:
        merged = self._collect()
        for fn in self._providers:
            try:
                merged.update(fn())
            except Exception:
                pass
        return merged

    def save(self):
        collected = self._collect()
        self.app_settings.clear()
        self.app_settings.update(collected)
        save_settings(self.app_settings)
        warnings = validate_settings(self._merged_for_health())
        msg = "设置已保存"
        if warnings:
            msg += "\n\n⚠ 体检提醒:\n" + "\n".join(f"· {w}" for w in warnings)
        CustomMessageBox.information(self, "保存设置", msg)
        self.saved.emit(dict(self.app_settings))

    def restore_defaults(self):
        ans = CustomMessageBox.question(self, "恢复默认", "确定恢复全部默认设置吗？")
        if ans not in ("是", "确定", "Yes"):
            return
        self.app_settings.clear()
        self.app_settings.update(dict(DEFAULT_SETTINGS))
        save_settings(self.app_settings)
        CustomMessageBox.information(self, "完成", "已恢复默认设置，重启后所有默认值生效")
        self.saved.emit(dict(self.app_settings))

    def show_health(self):
        warnings = validate_settings(self._merged_for_health())
        if warnings:
            CustomMessageBox.warning(
                self, "配置体检",
                "发现以下可优化项:\n" + "\n".join(f"· {w}" for w in warnings)
            )
        else:
            CustomMessageBox.information(self, "配置体检", "未发现配置问题 ✓")

    def reload_from_settings(self):
        s = self.app_settings
        self.chk_tray.setChecked(bool(s.get("tray_on_close", False)))
        self.combo_scan_mode.setCurrentText(s.get("scan_mode", "tcping"))
        self.spin_sample.setValue(int(s.get("sample_max", 5000)))
        self.spin_w_speed.setValue(float(s.get("score_speed_weight", 3.0)))
        self.spin_w_latency.setValue(float(s.get("score_latency_weight", 3.0)))
        self.chk_verify.setChecked(bool(s.get("verify_nodes", True)))
        self.spin_min_speed.setValue(float(s.get("min_speed", 0)))
        self.spin_interval.setValue(int(s.get("download_interval", 3)))
        self.chk_http.setChecked(bool(s.get("http_enabled", True)))
        self.spin_port.setValue(int(s.get("http_port", 17443)))
        self.chk_lan.setChecked(bool(s.get("allow_lan", False)))
        self.input_token.setText(s.get("http_token", ""))
        self._update_http_hint()
