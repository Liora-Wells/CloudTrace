#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import ipaddress
from typing import List, Tuple, Dict


def parse_ip_list(text: str, default_port: int = 443) -> Tuple[List[Dict], List[str]]:
    """解析非标 IP 列表。

    支持格式（每行一个）：
        1.2.3.4
        1.2.3.4 8443
        2606:4700::1111
        [2606:4700::1111]:8443
    返回 (entries, errors)；entries: [{'ip': str, 'port': int, 'ip_version': 4|6}]
    """
    entries: List[Dict] = []
    errors: List[str] = []
    seen = set()

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue

        ip_str = line
        port = default_port

        if line.startswith('['):
            # [v6]:port 形式
            end = line.find(']')
            if end == -1:
                errors.append(f"第{lineno}行: 括号未闭合 \"{line}\"")
                continue
            ip_str = line[1:end]
            rest = line[end + 1:]
            if rest.startswith(':'):
                port_str = rest[1:].strip()
                if not port_str.isdigit():
                    errors.append(f"第{lineno}行: 端口无效 \"{line}\"")
                    continue
                port = int(port_str)
            elif rest:
                errors.append(f"第{lineno}行: 格式无效 \"{line}\"")
                continue
        else:
            parts = line.split()
            if len(parts) == 1:
                # 可能是 "ip:port"（v4）或纯 IP
                if parts[0].count(':') == 1:
                    maybe_ip, maybe_port = parts[0].split(':')
                    if maybe_port.isdigit():
                        ip_str, port = maybe_ip, int(maybe_port)
                    else:
                        ip_str = parts[0]
                else:
                    ip_str = parts[0]
            elif len(parts) == 2:
                ip_str, port_str = parts
                if not port_str.isdigit():
                    errors.append(f"第{lineno}行: 端口无效 \"{line}\"")
                    continue
                port = int(port_str)
            else:
                errors.append(f"第{lineno}行: 格式无效 \"{line}\"")
                continue

        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            errors.append(f"第{lineno}行: 不是有效 IP \"{line}\"")
            continue

        if not (1 <= port <= 65535):
            errors.append(f"第{lineno}行: 端口超出范围 \"{line}\"")
            continue

        key = (str(addr), port)
        if key in seen:
            continue
        seen.add(key)
        entries.append({
            'ip': str(addr),
            'port': port,
            'ip_version': addr.version,
        })

    return entries, errors


def load_entries_from_file(filepath: str, default_port: int = 443) -> Tuple[List[Dict], List[str]]:
    """从 txt/csv 文件读取并解析（逗号视为空格）。"""
    try:
        if not os.path.exists(filepath):
            return [], [f"文件不存在: {filepath}"]
        with open(filepath, 'r', encoding='utf-8-sig', errors='ignore') as f:
            text = f.read().replace(',', ' ')
        return parse_ip_list(text, default_port)
    except Exception as e:
        return [], [f"读取文件失败: {e}"]
