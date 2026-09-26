#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CloudTrace 自动打包脚本（双目标）
  - 桌面版: PySide6 图形界面 + 内置 HTTP 面板服务
  - 面板版: 纯 HTTP 服务（无 Qt，浏览器访问管理面板）

使用前请确保已安装: pip install pyinstaller
如果打包后运行错误可先执行： pip install "charset_normalizer==2.1.1"
"""

import os
import subprocess
import sys

# ===================== 配置区 =====================
APP_NAME = "CloudTrace"
PANEL_NAME = "CloudTrace-Panel"
ICON_FILE = "favicon.ico"

# UPX 压缩工具路径 (下载地址: https://upx.github.io/，解压后填入路径，留空则不启用)
# 若在此处填写有效路径，打包时将直接使用，不再询问；若留空，则打包时会提示输入。
UPX_DIR = r""
# ===============================================


def check_pyinstaller():
    try:
        import PyInstaller
        print(f"[✓] 检测到 PyInstaller 版本: {PyInstaller.__version__}")
    except ImportError:
        print("[✗] 未检测到 PyInstaller，正在尝试安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def choose_targets():
    """选择打包目标"""
    print("\n请选择打包目标：")
    print("  1. 桌面版 (Qt 图形界面 + 内置 HTTP 面板)")
    print("  2. 面板版 (纯 HTTP 服务，无 Qt，体积更小)")
    print("  3. 两者都打包")
    while True:
        choice = input("请输入数字 (1/2/3，默认 1): ").strip() or "1"
        if choice in ("1", "2", "3"):
            break
        print("输入无效，请重新输入。")
    targets = []
    if choice in ("1", "3"):
        targets.append("desktop")
    if choice in ("2", "3"):
        targets.append("server")
    return targets


def choose_pack_mode():
    """让用户选择打包模式：单文件或文件夹"""
    print("\n请选择打包模式：")
    print("  1. 单文件 (单个 .exe，启动稍慢)")
    print("  2. 文件夹 (多个文件，启动较快)")
    while True:
        choice = input("请输入数字 (1 或 2，默认 2): ").strip() or "2"
        if choice in ("1", "2"):
            break
        print("输入无效，请重新输入。")
    return choice == "1"


def get_version():
    """获取用户输入的版本号，回车使用默认值"""
    try:
        with open("version.txt", "r", encoding="utf-8") as f:
            default = f.read().strip() or "1.0.0"
    except FileNotFoundError:
        default = "1.0.0"
    ver = input(f"\n请输入版本号 (默认 {default}): ").strip() or default
    print(f"[+] 使用版本号: {ver}")
    return ver


def get_upx_dir():
    """询问 UPX 目录路径（可留空跳过）"""
    print("\nUPX 压缩工具 (可减小程序体积，下载地址: https://upx.github.io/)")
    upx = input("请输入 UPX 目录路径 (留空跳过): ").strip()
    if upx:
        if not os.path.exists(upx):
            print(f"[!] 路径不存在，将不使用 UPX")
            return ""
        return upx
    return ""


def build_desktop(version, one_file, upx_dir):
    """桌面版：Qt 界面 + 内置 HTTP 服务"""
    print("\n🚀 开始打包 桌面版 ...")
    excludes = [
        "tkinter", "matplotlib", "numpy", "PIL", "scipy", "pandas",
        "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtSvg",
        "PySide6.QtXml", "PySide6.QtTest", "PySide6.QtSql",
        "PySide6.QtMultimedia", "PySide6.QtWebEngine",
        "PySide6.QtWebChannel", "PySide6.QtBluetooth",
        "aiohttp.worker",
    ]
    hidden = [
        "PySide6.QtWidgets", "PySide6.QtCore", "PySide6.QtGui",
        "asyncio", "ssl",
        "core", "core.compat", "core.constants", "core.network", "core.scanner",
        "core.scoring", "core.importer", "core.export", "core.analytics", "core.factory",
        "settings", "settings.settings", "settings.history",
        "service", "service.events", "service.task_manager", "service.api",
        "service.http_server", "service.health",
        "ui", "ui.styles", "ui.dialogs", "ui.bridge", "ui.widgets", "ui.main_window",
        "ui.pages", "ui.pages.scan_page", "ui.pages.result_page", "ui.pages.speed_page",
        "ui.pages.history_page", "ui.pages.settings_page",
    ]
    cmd_base = []
    for excl in excludes:
        cmd_base.extend(["--exclude-module", excl])
    for imp in hidden:
        cmd_base.extend(["--hidden-import", imp])

    full = [
        sys.executable, "-m", "PyInstaller",
        "--name", f"{APP_NAME}-{version}", "--noconfirm", "--clean", "--windowed",
        "--onefile" if one_file else "--onedir",
        "--add-data", "version.txt;.",
    ]
    if os.path.isdir("web"):
        full.extend(["--add-data", "web;."])
    if ICON_FILE and os.path.exists(ICON_FILE):
        full.extend(["--icon", ICON_FILE, "--add-data", f"{ICON_FILE};."])
    if upx_dir:
        full.extend(["--upx-dir", upx_dir, "--upx-exclude", "PySide6"])
    for pkg in ["aiohttp", "charset_normalizer", "multidict", "yarl", "idna", "attr", "aiosignal"]:
        full.extend(["--collect-all", pkg])
    full.extend(cmd_base)
    full.append("CloudTrace.py")

    print(f"\n[桌面版] 执行命令: \n{' '.join(full)}\n")
    subprocess.run(full, check=True)


def build_server(version, one_file, upx_dir):
    """面板版：纯 HTTP 服务（无 Qt）"""
    print("\n🚀 开始打包 面板版 ...")
    excludes = ["tkinter", "matplotlib", "numpy", "PIL", "scipy", "pandas", "PySide6"]
    hidden = [
        "asyncio", "ssl",
        "core", "core.compat", "core.constants", "core.network", "core.scanner",
        "core.scoring", "core.importer", "core.export", "core.analytics", "core.factory",
        "settings", "settings.settings", "settings.history",
        "service", "service.events", "service.task_manager", "service.api",
        "service.http_server", "service.health",
    ]
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", f"{PANEL_NAME}-{version}", "--noconfirm", "--clean", "--console",
        "--onefile" if one_file else "--onedir",
        "--add-data", "version.txt;.",
    ]
    if os.path.isdir("web"):
        cmd.extend(["--add-data", "web;."])
    if upx_dir:
        cmd.extend(["--upx-dir", upx_dir, "--upx-exclude", "PySide6"])
    for pkg in ["aiohttp", "charset_normalizer", "multidict", "yarl", "idna", "attr", "aiosignal"]:
        cmd.extend(["--collect-all", pkg])
    for excl in excludes:
        cmd.extend(["--exclude-module", excl])
    for imp in hidden:
        cmd.extend(["--hidden-import", imp])
    cmd.append("serve.py")

    print(f"\n[面板版] 执行命令: \n{' '.join(cmd)}\n")
    subprocess.run(cmd, check=True)


def main():
    check_pyinstaller()

    targets = choose_targets()
    version = get_version()
    with open("version.txt", "w", encoding="utf-8") as f:
        f.write(version)
    print(f"[✓] 已生成 version.txt，内容：{version}")

    one_file = choose_pack_mode()
    print(f"[+] 已选择打包模式: {'单文件' if one_file else '文件夹'}")

    if UPX_DIR and os.path.exists(UPX_DIR):
        upx_dir = UPX_DIR
        print(f"[✓] 使用预设 UPX 路径: {upx_dir}")
    else:
        if UPX_DIR:
            print("[!] 预设 UPX 路径不存在或无效")
        upx_dir = get_upx_dir()

    if "desktop" in targets:
        build_desktop(version, one_file, upx_dir)
    if "server" in targets:
        build_server(version, one_file, upx_dir)

    print("\n" + "=" * 50)
    print("✅ 打包完成！")
    if "desktop" in targets:
        if one_file:
            print(f"🖥  桌面版: dist/{APP_NAME}-{version}.exe")
        else:
            print(f"🖥  桌面版: dist/{APP_NAME}-{version}/{APP_NAME}-{version}.exe")
    if "server" in targets:
        if one_file:
            print(f"🌐 面板版: dist/{PANEL_NAME}-{version}.exe")
        else:
            print(f"🌐 面板版: dist/{PANEL_NAME}-{version}/{PANEL_NAME}-{version}.exe")
    print("=" * 50)


if __name__ == "__main__":
    main()
    input("按回车键退出...")
