#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import platform
import logging
import asyncio


logger = logging.getLogger("CloudTrace")
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)


IS_WIN7 = (platform.system() == "Windows" and platform.release() == "7")

if IS_WIN7:
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass
    os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '0'
    os.environ['QT_SCALE_FACTOR'] = '1'
    os.environ['QT_FONT_DPI'] = '96'

if sys.version_info < (3, 8):
    print("错误: 此程序需要 Python 3.8 或更高版本")
    sys.exit(1)


def get_event_loop_policy():
    if sys.platform == 'win32':
        if IS_WIN7:
            return asyncio.WindowsSelectorEventLoopPolicy()
        else:
            return asyncio.WindowsProactorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()
