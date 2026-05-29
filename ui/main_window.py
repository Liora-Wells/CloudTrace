#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import ipaddress
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton,
    QLineEdit, QProgressBar, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QHBoxLayout, QHeaderView,
    QTextEdit, QComboBox, QFileDialog,
    QSpinBox, QDialog, QFrame, QPlainTextEdit, QSystemTrayIcon, QMenu, QCheckBox,
    QApplication, QGroupBox, QSizePolicy, QStyle,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QIcon, QAction

from core.constants import (
    FONT_FAMILY, BTN_W, BTN_H, SPACING, APP_DIR,
    resource_path, get_version, PORT_OPTIONS, AIRPORT_CODES,
)
from settings import (
    load_settings, save_settings, load_custom_cidrs, save_custom_cidrs,
)
from ui.styles import (
    FONT_TITLE, FONT_BTN, FONT_SMALL, FONT_STATUS, FONT_LABEL,
    TABLE_STYLE, LOG_STYLE, btn_stylesheet,
)
from ui.dialogs import CustomMessageBox, HistorySelectDialog, ExportSelectDialog
from core.scanner import IPv4Scanner, IPv6Scanner, ScanWorker, SpeedTestWorker
from settings import (
    ensure_save_dir, save_results_to_file, load_results_from_file,
    get_history_list,
)


class CloudflareScanUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"CloudTrace 云迹 V{get_version()}")
        self.resize(480, 850)
        self.setMinimumSize(460, 650)

        self._setup_window_icon()
        
        self.setStyleSheet(f"""
        QWidget {{ font-family: "{FONT_FAMILY}", sans-serif; background: #F9FAFB; }}
        """)

        self.scan_worker = None
        self.speed_test_worker = None
        self.scanning = False
        self.speed_testing = False
        self.scan_results = []
        self.speed_results = []
        self.current_scan_port = 443
        self.current_ip_version = 4

        ensure_save_dir()
        self.app_settings = load_settings()
        self.init_ui()
        self._init_tray()

    def _setup_window_icon(self):
        """设置窗口图标，带降级策略"""
        try:
            icon_path = resource_path("favicon.ico")
            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
                if not icon.isNull():
                    self.setWindowIcon(icon)
                    return
        except Exception as e:
            logging.warning(f"加载窗口图标失败: {e}")
        
        # 使用默认图标作为后备
        default_icon = QApplication.style().standardIcon(QStyle.SP_ComputerIcon)
        self.setWindowIcon(default_icon)

    def make_btn(self, text, color, text_color="white", enabled=True, width=BTN_W):
        btn = QPushButton(text)
        btn.setFixedSize(width, BTN_H)
        btn.setFont(FONT_BTN)
        btn.setEnabled(enabled)
        btn.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        btn.setStyleSheet(btn_stylesheet(color, text_color))
        return btn

    def make_stop_btn(self, text, enabled=True):
        btn = QPushButton(text)
        btn.setFixedSize(BTN_W, BTN_H)
        btn.setFont(FONT_BTN)
        btn.setEnabled(enabled)
        btn.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        btn.setStyleSheet(btn_stylesheet("#EF4444", "white", "#DC2626"))
        return btn

    def _make_label(self, text):
        label = QLabel(text)
        label.setFont(FONT_SMALL)
        label.setStyleSheet(f'color: #E2E8F0; font-family: "{FONT_FAMILY}";')
        return label

    def _init_tray(self):
        """初始化系统托盘"""
        self.tray_icon = QSystemTrayIcon(self)
        
        # 设置托盘图标，带降级策略
        self._setup_tray_icon()
        self.tray_icon.setToolTip(f"CloudTrace 云迹 V{get_version()}")

        tray_menu = QMenu()

        action_show = tray_menu.addAction("显示主窗口")
        action_show.triggered.connect(self._tray_show_window)

        tray_menu.addSeparator()

        self.action_ipv4_scan = tray_menu.addAction("开始 IPv4 扫描")
        self.action_ipv4_scan.triggered.connect(self.start_ipv4_scan)

        self.action_ipv6_scan = tray_menu.addAction("开始 IPv6 扫描")
        self.action_ipv6_scan.triggered.connect(self.start_ipv6_scan)

        tray_menu.addSeparator()

        action_quit = tray_menu.addAction("退出")
        action_quit.triggered.connect(self._quit_application)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _setup_tray_icon(self):
        """设置托盘图标，带降级策略"""
        try:
            icon_path = resource_path("favicon.ico")
            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
                if not icon.isNull():
                    self.tray_icon.setIcon(icon)
                    return
        except Exception as e:
            logging.warning(f"加载托盘图标失败: {e}")
        
        # 使用默认图标作为后备
        default_icon = QApplication.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray_icon.setIcon(default_icon)

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._tray_show_window()

    def _tray_show_window(self):
        self.show()
        self.activateWindow()
        self.raise_()

    def _quit_application(self):
        """安全退出应用程序"""
        logging.info("用户请求退出应用程序")
        
        # 先停止所有任务
        if self.scan_worker:
            self.scan_worker.stop()
        if self.speed_test_worker:
            self.speed_test_worker.stop()
        
        # 隐藏托盘图标
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
        
        # 退出应用
        QApplication.quit()

    def init_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(14, 14, 14, 14)
        main.setSpacing(10)

        title_frame = QFrame()
        title_frame.setObjectName("titleFrame")
        title_frame.setStyleSheet("""
            #titleFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #1E3A5F, stop:0.5 #1E4976, stop:1 #2563EB);
                border-radius: 12px;
            }
        """)

        title_layout = QVBoxLayout(title_frame)
        title_layout.setContentsMargins(20, 14, 20, 14)
        title_layout.setSpacing(2)

        title = QLabel('☁ CloudTrace 云迹')
        title.setFont(FONT_TITLE)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: white; background: transparent; border: none;")
        title_layout.addWidget(title)

        subtitle = QLabel(f'V{get_version()}  ·  Cloudflare IP 优选扫描工具')
        subtitle.setFont(QFont(FONT_FAMILY, 10))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: rgba(255,255,255,180); background: transparent; border: none;")
        title_layout.addWidget(subtitle)

        main.addWidget(title_frame)

        control = QVBoxLayout()
        control.setSpacing(SPACING)
        control.setAlignment(Qt.AlignCenter)

        row1 = QHBoxLayout()
        row1.setSpacing(SPACING)
        row1.addStretch()

        self.btn_ipv4 = self.make_btn("IPv4 扫描", "#3B82F6")
        self.btn_ipv4.clicked.connect(self.start_ipv4_scan)
        row1.addWidget(self.btn_ipv4)

        row1.addSpacing(SPACING)

        self.btn_ipv6 = self.make_btn("IPv6 扫描", "#22C55E")
        self.btn_ipv6.clicked.connect(self.start_ipv6_scan)
        row1.addWidget(self.btn_ipv6)

        row1.addSpacing(SPACING)

        self.btn_stop = self.make_stop_btn("停止任务", enabled=False)
        self.btn_stop.clicked.connect(self.confirm_stop_all_tasks)
        row1.addWidget(self.btn_stop)
        row1.addStretch()

        control.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(SPACING)
        row2.addStretch()

        self.btn_load_ipv4_scan = self.make_btn("加载IPv4扫描结果", "#0EA5E9", width=160)
        self.btn_load_ipv4_scan.clicked.connect(self.load_ipv4_scan_results)
        row2.addWidget(self.btn_load_ipv4_scan)

        row2.addSpacing(SPACING)

        self.btn_load_ipv6_scan = self.make_btn("加载IPv6扫描结果", "#10B981", width=160)
        self.btn_load_ipv6_scan.clicked.connect(self.load_ipv6_scan_results)
        row2.addWidget(self.btn_load_ipv6_scan)
        row2.addStretch()

        control.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(SPACING)
        row3.addStretch()

        self.btn_area = self.make_btn("地区测速", "#EC4899", enabled=False)
        self.btn_area.clicked.connect(self.start_region_speed_test)
        row3.addWidget(self.btn_area)

        row3.addSpacing(SPACING)

        self.btn_full = self.make_btn("完全测速", "#F97316", enabled=False)
        self.btn_full.clicked.connect(self.start_full_speed_test)
        row3.addWidget(self.btn_full)

        row3.addSpacing(SPACING)

        self.btn_export = self.make_btn("导出结果", "#8B5CF6", enabled=False)
        self.btn_export.clicked.connect(self.export_results)
        row3.addWidget(self.btn_export)
        row3.addStretch()

        control.addLayout(row3)

        INPUT_BG = "#0F2B44"
        INPUT_BORDER = "#1A3D5C"
        TEXT_COLOR = "#F1F5F9"
        LABEL_COLOR = "#FFFFFF"
        FOCUS_COLOR = "#3B82F6"

        PARAM_BG = "#2153a5"
        PARAM_BORDER = "#1E4D6B"

        param_style = f"""
            QFrame#paramRow {{
                background: {PARAM_BG};
                border: 1px solid {PARAM_BORDER};
                border-radius: 8px;
                padding: 8px 14px;
            }}
            QLabel {{
                color: {LABEL_COLOR}; font-size: 11px;
                font-family: "{FONT_FAMILY}"; background: transparent; border: none;
                font-weight: 500;
            }}
            QLineEdit, QSpinBox, QComboBox {{
                background: {INPUT_BG}; color: {TEXT_COLOR};
                border: 1px solid {INPUT_BORDER}; border-radius: 4px;
                padding: 2px 6px; font-family: "{FONT_FAMILY}";
            }}
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border: 1px solid {FOCUS_COLOR};
            }}
            QCheckBox {{
                color: {LABEL_COLOR}; font-size: 11px;
                font-family: "{FONT_FAMILY}"; background: transparent; border: none;
                spacing: 4px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px; border-radius: 3px;
                border: 1px solid {INPUT_BORDER}; background: {INPUT_BG};
            }}
            QCheckBox::indicator:checked {{
                background: {FOCUS_COLOR}; border: 1px solid {FOCUS_COLOR};
            }}
        """

        param_frame = QFrame()
        param_frame.setObjectName("paramRow")
        param_frame.setStyleSheet(param_style)

        param_layout = QVBoxLayout(param_frame)
        param_layout.setContentsMargins(8, 8, 8, 8)
        param_layout.setSpacing(6)

        def _make_group(label_text, widget):
            group_layout = QVBoxLayout()
            group_layout.setSpacing(2)
            group_layout.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(label_text)
            lbl.setObjectName("paramLabel")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(FONT_SMALL)
            group_layout.addWidget(lbl)
            group_layout.addWidget(widget)
            return group_layout

        row_scan = QHBoxLayout()
        row_scan.setSpacing(20)
        row_scan.addStretch()

        self.input_region = QLineEdit()
        self.input_region.setFixedSize(75, 28)
        self.input_region.setFont(FONT_BTN)
        self.input_region.setPlaceholderText("")
        self.input_region.setAlignment(Qt.AlignCenter)
        self.input_region.textChanged.connect(self.auto_uppercase)
        row_scan.addLayout(_make_group("地区码", self.input_region))

        self.input_speed_count = QSpinBox()
        self.input_speed_count.setFixedSize(60, 28)
        self.input_speed_count.setFont(FONT_SMALL)
        self.input_speed_count.setRange(1, 50)
        self.input_speed_count.setValue(10)
        self.input_speed_count.setAlignment(Qt.AlignCenter)
        row_scan.addLayout(_make_group("数量", self.input_speed_count))

        self.combo_port = QComboBox()
        self.combo_port.setFixedSize(75, 28)
        self.combo_port.setFont(FONT_SMALL)
        for port in PORT_OPTIONS:
            self.combo_port.addItem(port)
        self.combo_port.setCurrentText("443")
        row_scan.addLayout(_make_group("端口", self.combo_port))

        self.input_workers = QSpinBox()
        self.input_workers.setFixedSize(65, 28)
        self.input_workers.setFont(FONT_SMALL)
        self.input_workers.setRange(10, 500)
        self.input_workers.setValue(200)
        self.input_workers.setSingleStep(50)
        self.input_workers.setAlignment(Qt.AlignCenter)
        row_scan.addLayout(_make_group("并发", self.input_workers))

        self.input_threshold = QSpinBox()
        self.input_threshold.setFixedSize(65, 28)
        self.input_threshold.setFont(FONT_SMALL)
        self.input_threshold.setRange(50, 999)
        self.input_threshold.setValue(230)
        self.input_threshold.setSingleStep(10)
        self.input_threshold.setAlignment(Qt.AlignCenter)
        row_scan.addLayout(_make_group("阈值ms", self.input_threshold))

        row_scan.addStretch()
        param_layout.addLayout(row_scan)

        row_extra = QHBoxLayout()
        row_extra.setSpacing(20)
        row_extra.addStretch()

        self.combo_cidr_mode = QComboBox()
        self.combo_cidr_mode.setFixedSize(120, 28)
        self.combo_cidr_mode.setFont(FONT_SMALL)
        self.combo_cidr_mode.addItems(["仅官方", "仅自定义", "官方+自定义"])
        self.combo_cidr_mode.setCurrentText(self.app_settings.get("cidr_mode", "仅官方"))
        self.combo_cidr_mode.currentTextChanged.connect(self.on_cidr_mode_changed)
        row_extra.addLayout(_make_group("CIDR", self.combo_cidr_mode))

        self.chk_tray_on_close = QCheckBox()
        self.chk_tray_on_close.setFont(FONT_SMALL)
        self.chk_tray_on_close.setToolTip("关闭窗口时最小化到托盘")
        self.chk_tray_on_close.setChecked(self.app_settings.get("tray_on_close", False))
        self.chk_tray_on_close.stateChanged.connect(self._on_tray_setting_changed)
        tray_layout = QVBoxLayout()
        tray_layout.setSpacing(2)
        tray_layout.setContentsMargins(0, 0, 0, 0)
        tray_lbl = QLabel("托盘")
        tray_lbl.setObjectName("paramLabel")
        tray_lbl.setAlignment(Qt.AlignCenter)
        tray_lbl.setFont(FONT_SMALL)
        tray_layout.addWidget(tray_lbl)
        tray_layout.addWidget(self.chk_tray_on_close)
        row_extra.addLayout(tray_layout)

        row_extra.addStretch()
        param_layout.addLayout(row_extra)

        param_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        control.addWidget(param_frame)

        self.text_custom_cidrs = QPlainTextEdit()
        self.text_custom_cidrs.setFont(FONT_SMALL)
        self.text_custom_cidrs.setMaximumHeight(80)
        self.text_custom_cidrs.setPlaceholderText("每行一个 CIDR，如:\n1.2.3.0/24\n2606:4700::/32")
        self.text_custom_cidrs.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {INPUT_BG}; color: {TEXT_COLOR};
                border: 1px solid {INPUT_BORDER}; border-radius: 4px;
                padding: 4px 6px; font-family: "{FONT_FAMILY}";
            }}
        """)
        saved_cidrs = load_custom_cidrs()
        if saved_cidrs:
            self.text_custom_cidrs.setPlainText(saved_cidrs)
        self.text_custom_cidrs.setVisible(self.combo_cidr_mode.currentText() != "仅官方")
        control.addWidget(self.text_custom_cidrs)

        main.addLayout(control)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
        QProgressBar { background: #E5E7EB; border-radius: 4px; }
        QProgressBar::chunk { background: #22C55E; border-radius: 4px; }
        """)
        main.addWidget(self.progress_bar)

        status_frame = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet(f'color: #6B7280; font-size: 12px; padding: 4px; font-family: "{FONT_FAMILY}";')
        self.speed_label = QLabel("速度: 0 IP/秒")
        self.speed_label.setStyleSheet(f'color: #6B7280; font-size: 12px; padding: 4px; font-family: "{FONT_FAMILY}";')
        status_frame.addWidget(self.status_label)
        status_frame.addStretch()
        status_frame.addWidget(self.speed_label)
        main.addLayout(status_frame)

        log_label = QLabel("扫描状态和统计信息")
        log_label.setFont(FONT_LABEL)
        log_label.setStyleSheet(f'color: #111827; font-size: 14px; font-family: "{FONT_FAMILY}";')
        main.addWidget(log_label)
        self.status_display = QTextEdit()
        self.status_display.setFont(FONT_STATUS)
        self.status_display.setMaximumHeight(180)
        self.status_display.setReadOnly(True)
        self.status_display.setStyleSheet(LOG_STYLE)
        main.addWidget(self.status_display)

        speed_label = QLabel("测速结果")
        speed_label.setFont(FONT_LABEL)
        speed_label.setStyleSheet(f'color: #111827; font-size: 14px; font-family: "{FONT_FAMILY}";')
        main.addWidget(speed_label)
        self.speed_table = QTableWidget()
        self.speed_table.setColumnCount(7)
        self.speed_table.setHorizontalHeaderLabels(["排名", "IP地址", "地区", "延迟", "下载速度", "端口", "测速类型"])
        for i in range(self.speed_table.columnCount() - 1):
            self.speed_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.speed_table.horizontalHeader().setSectionResizeMode(self.speed_table.columnCount() - 1, QHeaderView.Stretch)
        self.speed_table.verticalHeader().setVisible(False)
        self.speed_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.speed_table.doubleClicked.connect(self.copy_table_cell)
        self.speed_table.setStyleSheet(TABLE_STYLE)
        main.addWidget(self.speed_table, 1)

    def auto_uppercase(self, text):
        if text != text.upper():
            self.input_region.setText(text.upper())

    def on_cidr_mode_changed(self, mode_text):
        self.text_custom_cidrs.setVisible(mode_text != "仅官方")
        self.app_settings["cidr_mode"] = mode_text
        save_settings(self.app_settings)

    def _on_tray_setting_changed(self, state):
        self.app_settings["tray_on_close"] = bool(state)
        save_settings(self.app_settings)

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        logging.info(f"窗口关闭事件触发，托盘选项: {self.chk_tray_on_close.isChecked()}")
        
        if self.chk_tray_on_close.isChecked():
            # 最小化到托盘
            event.ignore()
            self.hide()
            
            # 显示提示消息
            if hasattr(self, 'tray_icon') and self.tray_icon.isSystemTrayAvailable():
                self.tray_icon.showMessage(
                    "CloudTrace 云迹",
                    "程序已最小化到系统托盘",
                    QSystemTrayIcon.Information,
                    2000
                )
        else:
            # 完全退出程序
            logging.info("用户选择完全退出程序")
            self._quit_application()
            event.accept()

    def _parse_custom_cidrs(self, ip_version: int) -> Optional[List[str]]:
        text = self.text_custom_cidrs.toPlainText().strip()
        if not text:
            CustomMessageBox.warning(self, "提示", "自定义 CIDR 不能为空")
            return None

        valid = []
        invalid = []
        for i, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                net = ipaddress.ip_network(line, strict=False)
                if net.version == ip_version:
                    valid.append(line)
            except ValueError:
                invalid.append((i, line))

        if invalid:
            msg_lines = [f'第{no}行 "{val}" 不是有效的 CIDR' for no, val in invalid[:10]]
            if len(invalid) > 10:
                msg_lines.append(f"... 共 {len(invalid)} 行无效")
            CustomMessageBox.warning(self, "CIDR 格式错误", "\n".join(msg_lines))
            return None

        if not valid:
            ip_label = "IPv4" if ip_version == 4 else "IPv6"
            CustomMessageBox.warning(self, "提示", f"未找到有效的{ip_label} CIDR")
            return None

        return valid

    def _format_region_stats(self, results: List[Dict]) -> List[str]:
        region_stats = {}
        for r in results:
            code = r.get('iata_code')
            if code and code.upper() != 'UNKNOWN':
                code = code.upper()
                name = r.get('chinese_name', code)
                key = (code, name)
                region_stats[key] = region_stats.get(key, 0) + 1

        lines = []
        for (code, name), cnt in sorted(region_stats.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {code}  {name}: {cnt}")
        return lines

    def update_ui_state(self, busy=False):
        self.btn_ipv4.setEnabled(not busy)
        self.btn_ipv6.setEnabled(not busy)
        self.btn_load_ipv4_scan.setEnabled(not busy)
        self.btn_load_ipv6_scan.setEnabled(not busy)
        self.btn_stop.setEnabled(busy)

        has_results = bool(self.scan_results)
        self.btn_area.setEnabled(not busy and has_results)
        self.btn_full.setEnabled(not busy and has_results)
        self.btn_export.setEnabled(not busy and (has_results or bool(self.speed_results)))

        if hasattr(self, 'action_ipv4_scan'):
            self.action_ipv4_scan.setEnabled(not busy)
        if hasattr(self, 'action_ipv6_scan'):
            self.action_ipv6_scan.setEnabled(not busy)

    def load_ipv4_scan_results(self):
        if self.scanning or self.speed_testing:
            CustomMessageBox.warning(self, "提示", "请先停止当前任务")
            return
        self._load_scan_results(4)

    def load_ipv6_scan_results(self):
        if self.scanning or self.speed_testing:
            CustomMessageBox.warning(self, "提示", "请先停止当前任务")
            return
        self._load_scan_results(6)

    def _load_scan_results(self, ip_version: int):
        ip_label = "IPv4" if ip_version == 4 else "IPv6"
        history = get_history_list(ip_version, "scan")
        if not history:
            CustomMessageBox.information(
                self, "提示",
                f"未找到{ip_label}扫描结果\n请先执行一次{ip_label}扫描"
            )
            return

        if len(history) == 1:
            self._do_load_scan(history[0]['filepath'], ip_label, ip_version)
            return

        dialog = HistorySelectDialog(ip_label, "扫描", history, self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_filepath:
            self._do_load_scan(dialog.selected_filepath, ip_label, ip_version)

    def _do_load_scan(self, filepath: str, ip_label: str, ip_version: int):
        data = load_results_from_file(filepath)
        if data is None or not data.get('results'):
            CustomMessageBox.warning(self, "错误", "加载失败：文件损坏或结果为空")
            return

        results = data['results']
        save_time = data.get('save_time', '未知')

        self.scan_results = results
        self.current_ip_version = ip_version

        port_from_result = results[0].get('port', 443) if results else 443
        self.current_scan_port = port_from_result
        self.combo_port.setCurrentText(str(port_from_result))

        self.status_display.clear()
        self.status_display.append(f"✅ 已加载{ip_label}扫描结果")
        self.status_display.append(f"  保存时间: {save_time}")
        self.status_display.append(f"  结果数量: {len(results)} 个IP")

        region_lines = self._format_region_stats(results)
        if region_lines:
            self.status_display.append("  地区分布:")
            for line in region_lines[:15]:
                self.status_display.append(line)

        latencies = [r.get('latency', 0) for r in results if r.get('latency')]
        if latencies:
            self.status_display.append(f"  延迟: {min(latencies):.1f}ms ~ {max(latencies):.1f}ms (平均 {sum(latencies)/len(latencies):.1f}ms)")

        self.status_display.append("=" * 30)
        self.status_display.append("输入地区码 → 点击「地区测速」")

        self.status_label.setText(f"已加载{ip_label}结果 ({len(results)}个)")
        self.speed_label.setText(f"保存时间: {save_time}")
        self.update_ui_state(busy=False)

    def start_ipv4_scan(self):
        if self.scanning or self.speed_testing:
            return
        cidr_mode = self.combo_cidr_mode.currentText()
        custom_cidrs = None
        if cidr_mode != "仅官方":
            parsed = self._parse_custom_cidrs(4)
            if parsed is None:
                return
            custom_cidrs = {"mode": cidr_mode, "list": parsed}
            save_custom_cidrs(self.text_custom_cidrs.toPlainText())

        self.current_ip_version = 4
        port = int(self.combo_port.currentText())
        threshold = self.input_threshold.value()
        workers = self.input_workers.value()
        self.current_scan_port = port

        scanner = IPv4Scanner(
            port=port,
            max_workers=workers,
            latency_threshold=threshold,
            custom_cidrs=custom_cidrs,
        )
        self._start_scan(scanner, "IPv4")

    def start_ipv6_scan(self):
        if self.scanning or self.speed_testing:
            return
        cidr_mode = self.combo_cidr_mode.currentText()
        custom_cidrs = None
        if cidr_mode != "仅官方":
            parsed = self._parse_custom_cidrs(6)
            if parsed is None:
                return
            custom_cidrs = {"mode": cidr_mode, "list": parsed}
            save_custom_cidrs(self.text_custom_cidrs.toPlainText())

        self.current_ip_version = 6
        port = int(self.combo_port.currentText())
        threshold = self.input_threshold.value()
        workers = self.input_workers.value()
        self.current_scan_port = port

        scanner = IPv6Scanner(
            port=port,
            max_workers=workers,
            latency_threshold=threshold,
            custom_cidrs=custom_cidrs,
        )
        self._start_scan(scanner, "IPv6")

    def _start_scan(self, scanner, label: str):
        self.scanning = True
        self.update_ui_state(busy=True)
        self.scan_results = []
        self.speed_results = []
        self.speed_table.setRowCount(0)

        self.status_display.clear()
        self.status_display.append(f"正在开始{label}扫描...")
        self.status_display.append("=" * 25)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"{label}扫描中...")
        self.speed_label.setText("速度: 0 IP/秒")

        self.scan_worker = ScanWorker(scanner)
        self.scan_worker.progress_update.connect(self.update_progress)
        self.scan_worker.status_message.connect(self.status_message)
        self.scan_worker.scan_completed.connect(self.scan_finished)
        self.scan_worker.finished.connect(lambda: setattr(self, 'scan_worker', None))
        self.scan_worker.start()

    def scan_finished(self, results):
        self.scan_results = results

        if results:
            saved = save_results_to_file(results, self.current_ip_version, "scan")
            ip_label = "IPv4" if self.current_ip_version == 4 else "IPv6"
            if saved:
                self.status_display.append(f"✅ {ip_label}扫描结果已自动保存")

            region_lines = self._format_region_stats(results)
            if region_lines:
                self.status_display.append("地区分布:")
                for line in region_lines[:15]:
                    self.status_display.append(line)

            self.status_display.append(f"扫描完成: {len(results)} 个可用IP")
        else:
            self.status_display.append("扫描完成: 未找到可用IP")

        self.scanning = False
        self.progress_bar.setValue(100)
        self.status_label.setText(f"扫描完成 ({len(results)}个IP)" if results else "扫描完成")
        self.update_ui_state(busy=False)

        if not self.isVisible() and results:
            ip_label = "IPv4" if self.current_ip_version == 4 else "IPv6"
            self.tray_icon.showMessage(
                "CloudTrace 扫描完成",
                f"{ip_label}扫描完成，找到 {len(results)} 个可用 IP",
                QSystemTrayIcon.Information,
                3000
            )

    def update_progress(self, completed, total, success, speed):
        if total > 0:
            self.progress_bar.setValue(int(completed / total * 100))
        self.status_label.setText(f"进度: {completed}/{total}")
        self.speed_label.setText(f"速度: {speed:.0f} IP/s | 成功: {success}")

    def status_message(self, msg):
        self.status_display.append(msg)
        sb = self.status_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def start_region_speed_test(self):
        if self.speed_testing:
            return
        if not self.scan_results:
            CustomMessageBox.warning(self, "提示", "请先扫描或加载扫描结果")
            return
        region_code = self.input_region.text().strip().upper()
        if not region_code:
            CustomMessageBox.warning(self, "提示", "请输入地区码（如 HKG, NRT, SIN）")
            return
        matched = [r for r in self.scan_results if r.get('iata_code') and r['iata_code'].upper() == region_code]
        if not matched:
            available = sorted(set(r.get('iata_code', '').upper() for r in self.scan_results if r.get('iata_code')))
            CustomMessageBox.warning(
                self, "提示",
                f"未找到地区码 {region_code} 的IP\n可用地区码: {', '.join(available[:30])}"
            )
            return
        self._start_speed_test(region_code)

    def start_full_speed_test(self):
        if self.speed_testing:
            return
        if not self.scan_results:
            CustomMessageBox.warning(self, "提示", "请先扫描或加载扫描结果")
            return
        self._start_speed_test(region_code=None)

    def _start_speed_test(self, region_code=None):
        self.speed_testing = True
        self.update_ui_state(busy=True)
        self.speed_results = []
        self.speed_table.setRowCount(0)

        max_count = self.input_speed_count.value()
        port = int(self.combo_port.currentText())
        self.current_scan_port = port

        self.speed_test_worker = SpeedTestWorker(
            self.scan_results, region_code, max_count, port
        )
        self.speed_test_worker.progress_update.connect(self.update_speed_progress)
        self.speed_test_worker.status_message.connect(self.status_message)
        self.speed_test_worker.speed_test_completed.connect(self.speed_test_finished)
        self.speed_test_worker.finished.connect(lambda: setattr(self, 'speed_test_worker', None))
        self.speed_test_worker.start()

    def update_speed_progress(self, current, total, speed):
        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))
        self.status_label.setText(f"测速进度: {current}/{total}")

    def speed_test_finished(self, results):
        self.speed_results = results
        self.speed_testing = False
        self.progress_bar.setValue(100)
        self.update_ui_state(busy=False)

        if results:
            save_results_to_file(results, self.current_ip_version, "speed")
            self._populate_speed_table(results)
            self.status_label.setText(f"测速完成 ({len(results)}个IP)")
        else:
            self.status_label.setText("测速完成: 无结果")

        if not self.isVisible() and results:
            best = results[0] if results else None
            speed_msg = f"{best['download_speed']:.1f} MB/s" if best else "无结果"
            region_msg = f"（{best['chinese_name']}）" if best else ""
            self.tray_icon.showMessage(
                "CloudTrace 测速完成",
                f"测速完成，最快 {speed_msg}{region_msg}",
                QSystemTrayIcon.Information,
                3000
            )

    def _populate_speed_table(self, results):
        self.speed_table.setRowCount(len(results))
        for i, r in enumerate(results):
            rank_item = QTableWidgetItem(str(i + 1))
            rank_item.setTextAlignment(Qt.AlignCenter)
            if i == 0:
                rank_item.setForeground(QColor("#FFD700"))
            elif i == 1:
                rank_item.setForeground(QColor("#C0C0C0"))
            elif i == 2:
                rank_item.setForeground(QColor("#CD7F32"))
            self.speed_table.setItem(i, 0, rank_item)

            self.speed_table.setItem(i, 1, QTableWidgetItem(r.get('ip', '')))

            code = r.get('iata_code', '')
            name = r.get('chinese_name', code)
            self.speed_table.setItem(i, 2, QTableWidgetItem(f"{name}({code})"))

            latency = r.get('latency', 0)
            latency_item = QTableWidgetItem(f"{latency:.1f}ms")
            latency_item.setTextAlignment(Qt.AlignCenter)
            if latency < 100:
                latency_item.setForeground(QColor("#22C55E"))
            elif latency < 200:
                latency_item.setForeground(QColor("#F97316"))
            else:
                latency_item.setForeground(QColor("#EF4444"))
            self.speed_table.setItem(i, 3, latency_item)

            speed = r.get('download_speed', 0)
            speed_item = QTableWidgetItem(f"{speed:.2f} MB/s")
            speed_item.setTextAlignment(Qt.AlignCenter)
            if speed >= 10:
                speed_item.setForeground(QColor("#22C55E"))
            elif speed >= 5:
                speed_item.setForeground(QColor("#F97316"))
            else:
                speed_item.setForeground(QColor("#EF4444"))
            self.speed_table.setItem(i, 4, speed_item)

            port_item = QTableWidgetItem(str(r.get('port', '')))
            port_item.setTextAlignment(Qt.AlignCenter)
            self.speed_table.setItem(i, 5, port_item)

            self.speed_table.setItem(i, 6, QTableWidgetItem(r.get('test_type', '')))

    def confirm_stop_all_tasks(self):
        if not self.scanning and not self.speed_testing:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("确认停止")
        dialog.setFixedSize(400, 200)
        dialog.setModal(True)
        dialog.setStyleSheet(f"""
            QDialog {{
                background: #F9FAFB;
                border-radius: 12px;
                font-family: "{FONT_FAMILY}";
            }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #1E3A5F, stop:1 #2563EB);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
        """)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 16, 20, 16)
        header_layout.setSpacing(4)

        header_title = QLabel("⚠️ 确认停止任务")
        header_title.setFont(QFont(FONT_FAMILY, 12))
        header_title.setStyleSheet("color: white; font-weight: bold; background: transparent; border: none;")
        header_layout.addWidget(header_title)

        header_subtitle = QLabel("正在运行的任务将被中断")
        header_subtitle.setFont(FONT_SMALL)
        header_subtitle.setStyleSheet("color: rgba(255,255,255,180); background: transparent; border: none;")
        header_layout.addWidget(header_subtitle)

        layout.addWidget(header_frame)

        content_frame = QFrame()
        content_frame.setStyleSheet("QFrame { background: #F9FAFB; border: none; }")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(16)

        msg_label = QLabel("确定要停止当前正在运行的任务吗？\n未完成的进度将会丢失。")
        msg_label.setFont(QFont(FONT_FAMILY, 10))
        msg_label.setStyleSheet("color: #374151; background: transparent; border: none;")
        msg_label.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(msg_label)

        layout.addWidget(content_frame)

        btn_frame = QFrame()
        btn_frame.setStyleSheet("QFrame { background: #F9FAFB; border: none; }")
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(24, 0, 24, 24)
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(100, 36)
        cancel_btn.setFont(FONT_BTN)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: #E5E7EB;
                color: #374151;
                border-radius: 8px;
                font-family: "{FONT_FAMILY}";
                border: none;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #D1D5DB;
            }}
            QPushButton:pressed {{
                background: #9CA3AF;
            }}
        """)
        cancel_btn.clicked.connect(dialog.reject)

        confirm_btn = QPushButton("停止任务")
        confirm_btn.setFixedSize(100, 36)
        confirm_btn.setFont(FONT_BTN)
        confirm_btn.setCursor(Qt.PointingHandCursor)
        confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background: #EF4444;
                color: white;
                border-radius: 8px;
                font-family: "{FONT_FAMILY}";
                border: none;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #DC2626;
            }}
            QPushButton:pressed {{
                background: #B91C1C;
            }}
        """)
        confirm_btn.clicked.connect(dialog.accept)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(confirm_btn)
        layout.addWidget(btn_frame)

        result = dialog.exec()

        if result == QDialog.Accepted:
            self.stop_all_tasks()

    def stop_all_tasks(self):
        if self.scan_worker:
            self.scan_worker.stop()
        if self.speed_test_worker:
            self.speed_test_worker.stop()
        self.scanning = False
        self.speed_testing = False
        self.status_display.append("⚠️ 所有任务已停止")
        self.status_label.setText("已停止")
        self.update_ui_state(busy=False)

    def copy_table_cell(self, index):
        item = self.speed_table.item(index.row(), index.column())
        if item:
            QApplication.clipboard().setText(item.text())
            self.status_display.append(f"已复制: {item.text()}")

    def export_results(self):
        has_scan = bool(self.scan_results)
        has_speed = bool(self.speed_results)
        if not has_scan and not has_speed:
            CustomMessageBox.warning(self, "提示", "没有可导出的结果")
            return
        dialog = ExportSelectDialog(has_scan, has_speed, self)
        if dialog.exec() != QDialog.Accepted or not dialog.choice:
            return
        choice = dialog.choice
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        saved_files = []
        try:
            if choice in ("scan", "both") and has_scan:
                scan_path, _ = QFileDialog.getSaveFileName(
                    self, "保存扫描结果",
                    f"cf_scan_{timestamp_str}.csv",
                    "CSV文件 (*.csv);;JSON文件 (*.json);;所有文件 (*)"
                )
                if scan_path:
                    self._write_export_file(scan_path, "scan", self.scan_results)
                    saved_files.append(scan_path)
            if choice in ("speed", "both") and has_speed:
                speed_path, _ = QFileDialog.getSaveFileName(
                    self, "保存测速结果",
                    f"cf_speed_{timestamp_str}.csv",
                    "CSV文件 (*.csv);;JSON文件 (*.json);;所有文件 (*)"
                )
                if speed_path:
                    self._write_export_file(speed_path, "speed", self.speed_results)
                    saved_files.append(speed_path)
            if saved_files:
                msg = "已导出:\n" + "\n".join(saved_files)
                self.status_display.append(f"✅ {msg}")
                CustomMessageBox.information(self, "导出成功", msg)
        except Exception as e:
            CustomMessageBox.critical(self, "错误", f"导出失败: {str(e)}")

    def _write_export_file(self, filepath: str, result_type: str, results: List[Dict]):
        if filepath.endswith('.json'):
            export_data = {
                'export_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'result_type': result_type,
                'count': len(results),
                'results': results,
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
        else:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                if result_type == "speed":
                    writer.writerow(["排名", "IP地址", "地区码", "地区", "延迟", "下载速度", "端口", "测速类型"])
                    for i, r in enumerate(results):
                        writer.writerow([
                            i + 1, r.get('ip', ''), r.get('iata_code', ''),
                            r.get('chinese_name', ''), r.get('latency', 0),
                            r.get('download_speed', 0), r.get('port', ''),
                            r.get('test_type', '')
                        ])
                else:
                    writer.writerow(["IP地址", "地区码", "地区", "延迟", "IP版本", "端口", "扫描时间"])
                    for r in results:
                        writer.writerow([
                            r.get('ip', ''), r.get('iata_code', ''),
                            r.get('chinese_name', ''), r.get('latency', 0),
                            r.get('ip_version', ''), r.get('port', ''),
                            r.get('scan_time', '')
                        ])
