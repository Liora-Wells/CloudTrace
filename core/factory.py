#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ipaddress
from typing import Dict, List, Optional, Tuple

from core.scanner import IPv4Scanner, IPv6Scanner, ImportedScanner, SpeedTestTask


def parse_cidr_lines(lines: List[str], ip_version: int) -> Tuple[List[str], List[Tuple[int, str]]]:
    """校验 CIDR 行列表。返回 (有效CIDR, [(行号, 原文)...无效])。"""
    valid: List[str] = []
    errors: List[Tuple[int, str]] = []
    for i, line in enumerate(lines, 1):
        line = (line or "").strip()
        if not line:
            continue
        try:
            net = ipaddress.ip_network(line, strict=False)
            if net.version == ip_version:
                valid.append(line)
        except ValueError:
            errors.append((i, line))
    return valid, errors


def create_scanner(params: Dict) -> object:
    """按统一参数字典构建扫描器（Qt 与 HTTP API 共用）。

    params: {
        ip_version, source_mode(仅官方/仅自定义/官方+自定义/非标列表),
        cidrs[], entries[], port, workers, threshold, sample_max,
        ping_times(0=自动), scan_mode(tcping/httping)
    }
    """
    common = dict(
        port=int(params.get("port", 443)),
        max_workers=int(params.get("workers", 200)),
        latency_threshold=int(params.get("threshold", 230)),
        sample_max=int(params.get("sample_max", 5000)),
        scan_mode=params.get("scan_mode", "tcping"),
    )
    ping_times = int(params.get("ping_times", 0) or 0)
    if ping_times > 0:
        common["ping_times"] = ping_times

    source_mode = params.get("source_mode", "仅官方")
    if source_mode == "非标列表":
        return ImportedScanner(entries=params.get("entries") or [], **common)

    custom = None
    if source_mode != "仅官方":
        custom = {"mode": source_mode, "list": params.get("cidrs") or []}
    cls = IPv4Scanner if int(params.get("ip_version", 4)) == 4 else IPv6Scanner
    return cls(custom_cidrs=custom, **common)


def create_speed_task(scan_results: List[Dict], opts: Dict, settings: Dict) -> SpeedTestTask:
    """按统一参数字典构建测速任务（Qt 与 HTTP API 共用）。

    opts: {
        region_code, selected_ips[], count, current_port,
        speed_url, min_speed, label
    }
    settings: 应用设置 dict（评分权重/验证开关/间隔）
    """
    return SpeedTestTask(
        scan_results,
        region_code=opts.get("region_code"),
        max_test_count=int(opts.get("count", 10)),
        current_port=int(opts.get("current_port", 443)),
        speed_url=opts.get("speed_url") or "auto",
        min_speed=float(opts.get("min_speed") or 0),
        selected_ips=opts.get("selected_ips"),
        verify_nodes=bool(settings.get("verify_nodes", True)),
        score_weights={
            "speed": settings.get("score_speed_weight", 3.0),
            "latency": settings.get("score_latency_weight", 3.0),
        },
        download_interval=int(settings.get("download_interval", 3)),
        label=opts.get("label"),
    )
