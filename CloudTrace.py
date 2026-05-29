#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys

from core.compat import IS_WIN7

if IS_WIN7:
    try:
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass

from PySide6.QtWidgets import QApplication
from ui.main_window import CloudflareScanUI


if __name__ == '__main__':
    if sys.version_info < (3, 8):
        print("错误: 此程序需要 Python 3.8 或更高版本")
        sys.exit(1)
    app = QApplication(sys.argv)
    window = CloudflareScanUI()
    window.show()
    sys.exit(app.exec())
