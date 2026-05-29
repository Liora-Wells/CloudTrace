#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging

from core.constants import APP_DIR


logger = logging.getLogger("CloudTrace")

SAVE_DIR = os.path.join(APP_DIR, "CloudTrace_history")

SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
CUSTOM_CIDRS_FILE = os.path.join(APP_DIR, "custom_cidrs.txt")

DEFAULT_SETTINGS = {
    "tray_on_close": False,
    "cidr_mode": "仅官方",
}


def load_settings() -> dict:
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            merged = dict(DEFAULT_SETTINGS)
            merged.update(saved)
            return merged
    except Exception:
        pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("保存设置失败: %s", e)


def load_custom_cidrs() -> str:
    try:
        if os.path.exists(CUSTOM_CIDRS_FILE):
            with open(CUSTOM_CIDRS_FILE, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception:
        pass
    return ""


def save_custom_cidrs(text: str):
    try:
        with open(CUSTOM_CIDRS_FILE, 'w', encoding='utf-8') as f:
            f.write(text)
    except Exception as e:
        logger.error("保存自定义CIDR失败: %s", e)
