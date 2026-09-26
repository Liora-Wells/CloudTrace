#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QStackedWidget, QFileDialog, QApplication, QStyle, QSystemTrayIcon, QMenu,
    QDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon

from core.constants import FONT_FAMILY, resource_path, get_version
from core.factory import create_scanner, create_speed_task
from core.export import write_export
from core.analytics import region_stats
from settings import (
    load_settings, ensure_save_dir, save_custom_cidrs,
    save_results_to_file, load_results_from_file, delete_history,
)
from ui.styles import (
    C_BLUE, C_ORANGE, C_GREEN, C_RED, C_MUTED,
    btn_stylesheet, ghost_btn_stylesheet, PILL_STYLE, PROGRESS_STYLE,
)
from ui.widgets import SideNav
from ui.dialogs import CustomMessageBox, ExportDialog
from ui.pages.scan_page import ScanPage
from ui.pages.result_page import ResultPage
from ui.pages.speed_page import SpeedPage
from ui.pages.history_page import HistoryPage
from ui.pages.settings_page import SettingsPage
from service.task_manager import task_manager
from service.http_server import http_server
from ui.bridge import WorkerBridge

logger = logging.getLogger("CloudTrace")

PAGE_SCAN = 0
PAGE_RESULT = 1
PAGE_SPEED = 2
PAGE_HISTORY = 3
PAGE_SETTINGS = 4

PAGE_TITLES = ["扫描", "扫描结果", "测速结果", "历史记录", "设置"]
CTA_STYLES = {
    PAGE_SCAN: ("▶ 开始扫描", C_BLUE),
    PAGE_RESULT: ("🚀 批量测速", C_ORANGE),
    PAGE_SPEED: ("⬇ 导出结果", C_GREEN),
    PAGE_HISTORY: ("🔄 前往扫描", C_BLUE),
    PAGE_SETTINGS: ("💾 保存设置", C_BLUE),
}


class CloudflareScanUI(QWidget):
    """主窗口薄壳：左侧导航 + 顶栏状态 + 页面栈，编排任务与页面。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"CloudTrace 云迹 V{get_version()}")
        self.resize(1100, 780)
        self.setMinimumSize(960, 640)

        self._setup_window_icon()
        self.setStyleSheet(f"""
        QWidget {{ font-family: "{FONT_FAMILY}", sans-serif; background: #F9FAFB; color: #111827; }}
        """)

        self.scanning = False
        self.speed_testing = False
        self.scan_results: List[Dict] = []
        self.speed_results: List[Dict] = []
        self.current_scan_port = 443
        self.current_ip_version = 4
        self.current_funnel: Dict[str, int] = {}
        self.current_page = PAGE_SCAN

        ensure_save_dir()
        self.app_settings = load_settings()

        self._setup_bridge()
        self._build_ui()
        self._init_tray()
        self._set_page(PAGE_SCAN)
        self._sync_http_server()

    # ================= 桥接 =================
    def _setup_bridge(self):
        self.bridge = WorkerBridge(self)
        self.bridge.progress_update.connect(self._on_progress)
        self.bridge.status_message.connect(self._on_log)
        self.bridge.funnel_updated.connect(self._on_funnel)
        self.bridge.scan_completed.connect(self._scan_finished)
        self.bridge.scan_aborted.connect(self._scan_aborted)
        self.bridge.speed_progress.connect(self._on_speed_progress)
        self.bridge.speed_completed.connect(self._speed_finished)

    def _on_log(self, msg: str):
        self.scan_page.log(msg)
        self.speed_page.log(msg)

    def _on_funnel(self, funnel: dict):
        self.current_funnel = dict(funnel)
        steps = []
        if funnel.get("generated"):
            steps = [
                ("生成", funnel.get("generated")),
                ("延迟达标", funnel.get("latency_ok")),
                ("地区解析", funnel.get("with_iata")),
            ]
        self.scan_page.set_funnel(steps)

    # ================= UI 构建 =================
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = SideNav([
            ("📡", "扫描"), ("📋", "结果"), ("🚀", "测速"),
            ("🕘", "历史"), ("⚙️", "设置"),
        ])
        self.sidebar.pageChanged.connect(self._set_page)
        root.addWidget(self.sidebar)

        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # ---- 顶栏 ----
        topbar = QHBoxLayout()
        topbar.setContentsMargins(20, 10, 20, 8)
        topbar.setSpacing(12)

        self.lbl_title = QLabel(PAGE_TITLES[0])
        self.lbl_title.setFont(QFont(FONT_FAMILY, 15))
        self.lbl_title.setStyleSheet("font-weight: bold; border: none; background: transparent;")
        topbar.addWidget(self.lbl_title)

        self.lbl_pill = QLabel("就绪")
        self.lbl_pill.setObjectName("statusPill")
        self.lbl_pill.setProperty("status", "idle")
        topbar.addWidget(self.lbl_pill)

        self.lbl_meta = QLabel("")
        self.lbl_meta.setStyleSheet(f"color: {C_MUTED}; font-size: 12px; border: none; background: transparent;")
        topbar.addWidget(self.lbl_meta)

        topbar.addStretch()

        self.lbl_speed = QLabel("速度: 0 IP/s")
        self.lbl_speed.setStyleSheet(f"color: {C_MUTED}; font-size: 12px; border: none; background: transparent;")
        topbar.addWidget(self.lbl_speed)

        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_stop.setFixedHeight(32)
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(ghost_btn_stylesheet())
        self.btn_stop.clicked.connect(self._confirm_stop)
        topbar.addWidget(self.btn_stop)

        self.btn_cta = QPushButton(CTA_STYLES[PAGE_SCAN][0])
        self.btn_cta.setFixedHeight(32)
        self.btn_cta.setCursor(Qt.PointingHandCursor)
        self.btn_cta.clicked.connect(self._on_cta)
        topbar.addWidget(self.btn_cta)

        main.addLayout(topbar)

        # ---- 进度条 ----
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(PROGRESS_STYLE)
        main.addWidget(self.progress_bar)

        # ---- 页面栈 ----
        self.stack = QStackedWidget()
        self.scan_page = ScanPage(self.app_settings)
        self.result_page = ResultPage()
        self.speed_page = SpeedPage(self.app_settings)
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage(self.app_settings)

        for page in (self.scan_page, self.result_page, self.speed_page,
                     self.history_page, self.settings_page):
            self.stack.addWidget(page)
        main.addWidget(self.stack, 1)

        root.addLayout(main, 1)
        self.setStyleSheet(PILL_STYLE)

        # ---- 页面信号 ----
        self.scan_page.start_requested.connect(self._start_scan_from_page)

        self.result_page.single_speed_requested.connect(self._on_single_speed)
        self.result_page.region_speed_requested.connect(self._on_region_speed)
        self.result_page.full_speed_requested.connect(self._start_full_speed)
        self.result_page.export_requested.connect(lambda: self._export(initial="scan"))

        self.speed_page.start_region_requested.connect(self._start_region_speed_text)
        self.speed_page.start_full_requested.connect(self._start_full_speed)
        self.speed_page.export_requested.connect(lambda: self._export(initial="speed"))

        self.history_page.load_requested.connect(self._load_history)
        self.history_page.export_requested.connect(self._export_history)
        self.history_page.delete_requested.connect(self._delete_history)

        self.settings_page.set_param_provider(self.scan_page.health_snapshot)
        self.settings_page.set_param_provider(self.speed_page.health_snapshot)
        self.settings_page.saved.connect(self._sync_http_server)

    def _sync_http_server(self, *_args):
        """按设置启动/停止 HTTP 面板服务。"""
        s = self.app_settings
        if s.get("http_enabled", True):
            host = "0.0.0.0" if s.get("allow_lan") else "127.0.0.1"
            port = int(s.get("http_port", 17443))
            ok = http_server.start(host, port)
            if ok:
                msg = f"HTTP 面板已就绪: {http_server.address}"
                if s.get("http_token"):
                    msg += " (需要 Token)"
            else:
                msg = f"HTTP 服务启动失败: {http_server.error}"
        else:
            http_server.stop()
            msg = "HTTP 面板已关闭"
        self.scan_page.log(msg)

    # ================= 页面导航 =================
    def _set_page(self, idx: int):
        if not (0 <= idx < self.stack.count()):
            return
        self.current_page = idx
        self.stack.setCurrentIndex(idx)
        self.sidebar.set_active(idx)
        self.lbl_title.setText(PAGE_TITLES[idx])
        text, color = CTA_STYLES[idx]
        self.btn_cta.setText(text)
        self.btn_cta.setStyleSheet(btn_stylesheet(color))

    def _on_cta(self):
        idx = self.current_page
        if idx == PAGE_SCAN:
            self._start_scan_from_page()
        elif idx == PAGE_RESULT:
            codes = self.result_page.chips.selected_codes()
            if codes:
                self._on_region_speed(codes)
            else:
                self._start_full_speed()
        elif idx == PAGE_SPEED:
            self._export(initial="speed" if self.speed_results else "scan")
        elif idx == PAGE_HISTORY:
            self._set_page(PAGE_SCAN)
        elif idx == PAGE_SETTINGS:
            self.settings_page.save()

    # ================= 状态 =================
    def _set_status(self, text: str, mode: str = "idle"):
        self.lbl_pill.setText(text)
        self.lbl_pill.setProperty("status", mode)
        self.lbl_pill.style().unpolish(self.lbl_pill)
        self.lbl_pill.style().polish(self.lbl_pill)

    def _set_busy(self, busy: bool):
        self.btn_stop.setEnabled(busy)
        self.btn_cta.setEnabled(not busy)
        self.scan_page.set_busy(busy)
        self.result_page.set_busy(busy)
        self.speed_page.set_busy(busy)

    def _on_progress(self, completed: int, total: int, success: int, speed: float):
        if total > 0:
            self.progress_bar.setValue(int(completed / total * 100))
        self.lbl_speed.setText(f"速度: {speed:.0f} IP/s | 成功: {success}")
        self._set_status(f"扫描 {completed}/{total}", "run")

    def _on_speed_progress(self, current: int, total: int, _speed: float):
        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))
        self._set_status(f"测速 {current}/{total}", "run")

    # ================= 扫描 =================
    def _start_scan_from_page(self):
        if task_manager.busy:
            CustomMessageBox.warning(self, "提示", "已有任务正在运行")
            return
        params = self.scan_page.collect()
        if params is None:
            return
        if params["source_mode"] in ("仅自定义", "官方+自定义"):
            save_custom_cidrs(params["cidr_text"])

        scanner = create_scanner(params)
        if not task_manager.start_scan(scanner, scanner.ip_version):
            CustomMessageBox.warning(self, "提示", "任务启动失败：已有任务正在运行")
            return

        self.scanning = True
        self.scan_results = []
        self.speed_results = []
        self.current_funnel = {}
        self.current_ip_version = scanner.ip_version
        self.current_scan_port = params["port"]

        self.result_page.set_empty()
        self.speed_page.set_results([])
        self.scan_page.set_funnel([])
        self.progress_bar.setValue(0)
        self.lbl_speed.setText("速度: 0 IP/s")
        self.lbl_meta.setText(
            f"{scanner.ip_label} · 端口 {params['port']} · "
            f"并发 {params['workers']} · {'HTTPing' if params['scan_mode'] == 'httping' else 'TCPing'}"
        )
        self._set_status("扫描中…", "run")
        self._set_busy(True)

    def _scan_finished(self, results: List[Dict]):
        self.scanning = False
        self.scan_results = results or []
        self.progress_bar.setValue(100)

        if results:
            save_results_to_file(results, self.current_ip_version, "scan")
            scan_mode = results[0].get("scan_mode", "tcping")
            self.result_page.set_results(results, dict(self.current_funnel), scan_mode)
            self.scan_page.log(f"✅ 扫描完成: {len(results)} 个可用IP，已存入历史")
            for line in self._region_lines(results)[:10]:
                self.scan_page.log(line)
            self._set_status(f"完成 · {len(results)} IP", "run")
            self._set_page(PAGE_RESULT)
            if not self.isVisible():
                self.tray_icon.showMessage(
                    "CloudTrace 扫描完成",
                    f"找到 {len(results)} 个可用 IP",
                    QSystemTrayIcon.Information, 3000,
                )
        else:
            self.scan_page.log("扫描完成: 未找到可用IP")
            self._set_status("完成（无结果）", "idle")

        self._set_busy(False)

    def _scan_aborted(self):
        self.scanning = False
        self.progress_bar.setValue(0)
        self._set_status("已停止", "idle")
        self._set_busy(False)

    def _region_lines(self, results: List[Dict]) -> List[str]:
        return [f"  {s['code']}  {s['name']}: {s['count']}" for s in region_stats(results)]

    # ================= 测速 =================
    def _start_speed_test(self, region_code: Optional[str] = None,
                          selected_ips: Optional[List[Dict]] = None,
                          label: Optional[str] = None):
        if task_manager.busy:
            CustomMessageBox.warning(self, "提示", "已有任务正在运行")
            return
        if not self.scan_results:
            CustomMessageBox.warning(self, "提示", "请先扫描或加载扫描结果")
            return

        opts = self.speed_page.collect()
        opts["current_port"] = self.current_scan_port
        opts["region_code"] = region_code
        opts["selected_ips"] = selected_ips
        opts["label"] = label
        task = create_speed_task(self.scan_results, opts, self.app_settings)
        if not task_manager.start_speed_test(task):
            CustomMessageBox.warning(self, "提示", "任务启动失败：已有任务正在运行")
            return

        self.speed_testing = True
        self.progress_bar.setValue(0)
        self._set_status("测速中…", "busy")
        self._set_busy(True)
        self._set_page(PAGE_SPEED)

    def _on_single_speed(self, info):
        if isinstance(info, dict) and "_multiple" in info:
            self._start_speed_test(selected_ips=info["_multiple"], label="自选测速")
        else:
            self._start_speed_test(selected_ips=[info], label="单点测速")

    def _on_region_speed(self, codes: List[str]):
        codes_u = {c.upper() for c in codes}
        matched = [r for r in self.scan_results
                   if (r.get("iata_code") or "").upper() in codes_u]
        if not matched:
            CustomMessageBox.warning(self, "提示", "所选地区没有匹配的 IP")
            return
        self._start_speed_test(selected_ips=matched, label="地区测速")

    def _start_region_speed_text(self):
        region = self.speed_page.collect()["region"]
        matched = [r for r in self.scan_results
                   if (r.get("iata_code") or "").upper() == region]
        if not matched:
            available = sorted({(r.get("iata_code") or "").upper()
                                for r in self.scan_results if r.get("iata_code")})
            CustomMessageBox.warning(
                self, "提示",
                f"未找到地区码 {region} 的IP\n可用地区码: {', '.join(available[:30])}"
            )
            return
        self._start_speed_test(region_code=region)

    def _start_full_speed(self):
        self._start_speed_test()

    def _speed_finished(self, results: List[Dict]):
        self.speed_testing = False
        self.speed_results = results or []
        self.progress_bar.setValue(100)
        self.speed_page.set_results(self.speed_results)

        if results:
            save_results_to_file(results, self.current_ip_version, "speed")
            best = results[0]
            self._set_status(f"完成 · 最快 {best.get('download_speed', 0)} MB/s", "run")
            self.scan_page.log(
                f"✅ 测速完成: {len(results)} 个结果，最优 {best.get('ip')} "
                f"({best.get('download_speed')} MB/s, 评分 {best.get('score')})"
            )
            if not self.isVisible():
                self.tray_icon.showMessage(
                    "CloudTrace 测速完成",
                    f"最快 {best.get('download_speed', 0)} MB/s（{best.get('chinese_name', '')}）",
                    QSystemTrayIcon.Information, 3000,
                )
        else:
            self._set_status("测速完成（无结果）", "idle")

        self._set_busy(False)
        self._set_page(PAGE_SPEED)

    # ================= 停止 =================
    def _confirm_stop(self):
        if not task_manager.busy:
            return
        ans = CustomMessageBox.question(
            self, "确认停止",
            "确定要停止当前正在运行的任务吗？\n未完成的进度将会丢失。",
            ["停止", "取消"], "取消",
        )
        if ans == "停止":
            self.stop_all_tasks()

    def stop_all_tasks(self):
        task_manager.stop()
        self.scanning = False
        self.speed_testing = False
        self._set_status("已停止", "idle")
        self._set_busy(False)
        self.scan_page.log("⚠️ 任务已停止")

    # ================= 导出 =================
    def _export(self, initial: str = None):
        has_scan = bool(self.scan_results)
        has_speed = bool(self.speed_results)
        if not has_scan and not has_speed:
            CustomMessageBox.warning(self, "提示", "没有可导出的结果")
            return

        dlg = ExportDialog(has_scan, has_speed, self, initial_choice=initial)
        if dlg.exec() != QDialog.Accepted or not dlg.choice:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved = []
        try:
            if dlg.choice in ("scan", "both") and has_scan:
                path, _ = QFileDialog.getSaveFileName(
                    self, "保存扫描结果", f"cf_scan_{timestamp}.csv",
                    "CSV文件 (*.csv);;JSON文件 (*.json);;所有文件 (*)",
                )
                if path:
                    write_export(path, self.scan_results, "scan", fields=dlg.fields)
                    saved.append(path)
            if dlg.choice in ("speed", "both") and has_speed:
                path, _ = QFileDialog.getSaveFileName(
                    self, "保存测速结果", f"cf_speed_{timestamp}.csv",
                    "CSV文件 (*.csv);;JSON文件 (*.json);;所有文件 (*)",
                )
                if path:
                    write_export(path, self.speed_results, "speed", fields=dlg.fields,
                                 qualified_only=dlg.qualified_only, min_speed=dlg.min_speed)
                    saved.append(path)
            if saved:
                msg = "已导出:\n" + "\n".join(saved)
                self.scan_page.log(f"✅ {msg}")
                CustomMessageBox.information(self, "导出成功", msg)
        except Exception as e:
            logger.exception("导出失败")
            CustomMessageBox.critical(self, "错误", f"导出失败: {e}")

    # ================= 历史 =================
    def _load_history(self, filepath: str, type_key: str):
        data = load_results_from_file(filepath)
        if data is None or not data.get("results"):
            CustomMessageBox.warning(self, "错误", "加载失败：文件损坏或结果为空")
            return
        results = data["results"]
        save_time = data.get("save_time", "未知")

        if type_key == "scan":
            self.scan_results = results
            self.current_ip_version = data.get("ip_version", self.current_ip_version)
            self.current_scan_port = results[0].get("port", 443)
            scan_mode = results[0].get("scan_mode", "tcping")
            self.result_page.set_results(results, {}, scan_mode)
            self.scan_page.log(f"✅ 已加载扫描记录 ({save_time})，共 {len(results)} 个IP")
            self._set_status(f"已加载 {len(results)} IP", "idle")
            self._set_page(PAGE_RESULT)
        else:
            self.speed_results = results
            self.current_ip_version = data.get("ip_version", self.current_ip_version)
            self.speed_page.set_results(results)
            self.scan_page.log(f"✅ 已加载测速记录 ({save_time})，共 {len(results)} 条")
            self._set_status(f"已加载 {len(results)} 条测速", "idle")
            self._set_page(PAGE_SPEED)

    def _export_history(self, filepath: str, type_key: str):
        data = load_results_from_file(filepath)
        if data is None or not data.get("results"):
            CustomMessageBox.warning(self, "错误", "加载失败：文件损坏或结果为空")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"cf_{type_key}_{timestamp}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出历史记录", default_name,
            "CSV文件 (*.csv);;JSON文件 (*.json);;所有文件 (*)",
        )
        if not path:
            return
        try:
            write_export(path, data["results"], type_key)
            CustomMessageBox.information(self, "导出成功", f"已导出:\n{path}")
        except Exception as e:
            CustomMessageBox.critical(self, "错误", f"导出失败: {e}")

    def _delete_history(self, filepath: str):
        if delete_history(filepath):
            self.history_page.refresh()
            CustomMessageBox.information(self, "完成", "已删除")
        else:
            CustomMessageBox.warning(self, "错误", "删除失败")

    # ================= 托盘 / 关闭 =================
    def _setup_window_icon(self):
        try:
            icon_path = resource_path("favicon.ico")
            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
                if not icon.isNull():
                    self.setWindowIcon(icon)
                    return
        except Exception as e:
            logging.warning(f"加载窗口图标失败: {e}")
        default_icon = QApplication.style().standardIcon(QStyle.SP_ComputerIcon)
        self.setWindowIcon(default_icon)

    def _init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self._setup_tray_icon()
        self.tray_icon.setToolTip(f"CloudTrace 云迹 V{get_version()}")

        tray_menu = QMenu()
        action_show = tray_menu.addAction("显示主窗口")
        action_show.triggered.connect(self._tray_show_window)
        tray_menu.addSeparator()

        self.action_ipv4_scan = tray_menu.addAction("开始 IPv4 扫描")
        self.action_ipv4_scan.triggered.connect(lambda: self._tray_start_scan(4))
        self.action_ipv6_scan = tray_menu.addAction("开始 IPv6 扫描")
        self.action_ipv6_scan.triggered.connect(lambda: self._tray_start_scan(6))
        tray_menu.addSeparator()

        action_quit = tray_menu.addAction("退出")
        action_quit.triggered.connect(self._quit_application)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _setup_tray_icon(self):
        try:
            icon_path = resource_path("favicon.ico")
            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
                if not icon.isNull():
                    self.tray_icon.setIcon(icon)
                    return
        except Exception as e:
            logging.warning(f"加载托盘图标失败: {e}")
        default_icon = QApplication.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray_icon.setIcon(default_icon)

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._tray_show_window()

    def _tray_show_window(self):
        self.show()
        self.activateWindow()
        self.raise_()

    def _tray_start_scan(self, ip_version: int):
        if task_manager.busy:
            CustomMessageBox.warning(self, "提示", "已有任务正在运行")
            return
        self._tray_show_window()
        self._set_page(PAGE_SCAN)
        self.scan_page.seg_version.set_index(0 if ip_version == 4 else 1)
        self._start_scan_from_page()

    def _quit_application(self):
        logging.info("用户请求退出应用程序")
        task_manager.stop(wait=True, timeout=3.0)
        http_server.stop()
        if hasattr(self, "tray_icon"):
            self.tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if self.app_settings.get("tray_on_close", False):
            event.ignore()
            self.hide()
            if hasattr(self, "tray_icon") and self.tray_icon.isSystemTrayAvailable():
                self.tray_icon.showMessage(
                    "CloudTrace 云迹",
                    "程序已最小化到系统托盘",
                    QSystemTrayIcon.Information, 2000,
                )
        else:
            self._quit_application()
            event.accept()

    # (HTTP 状态展示已并入 _sync_http_server)
