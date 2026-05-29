#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from core.compat import IS_WIN7

if IS_WIN7:
    try:
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from ui.main_window import CloudflareScanUI


if __name__ == '__main__':
    if sys.version_info < (3, 8):
        print("错误: 此程序需要 Python 3.8 或更高版本")
        sys.exit(1)
    
    app = QApplication(sys.argv)
    app.setApplicationName("CloudTrace 云迹")
    
    # 确保最后一个窗口关闭时应用程序也能正确退出
    app.setQuitOnLastWindowClosed(False)
    
    window = CloudflareScanUI()
    window.show()
    
    exit_code = app.exec()
    logging.info(f"应用程序退出，代码: {exit_code}")
    sys.exit(exit_code)
