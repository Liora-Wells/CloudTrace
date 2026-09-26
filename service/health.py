#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, List

from core.scanner import DEFAULT_SAMPLE_MAX, HTTPING_SCALE_TLS


def validate_settings(settings: Dict) -> List[str]:
    """配置体检：返回人类可读的警告清单（空列表 = 无问题）。"""
    warnings: List[str] = []

    threshold = int(settings.get("latency_threshold", 230) or 230)
    if threshold < 80:
        warnings.append(f"延迟阈值 {threshold}ms 过低，可能扫不出任何 IP，建议 150~300")

    workers = int(settings.get("workers", 200) or 200)
    if workers > 400:
        warnings.append(f"并发数 {workers} 较高，低配机或家庭路由可能丢包/端口耗尽，建议 ≤300")

    sample_max = int(settings.get("sample_max", DEFAULT_SAMPLE_MAX) or DEFAULT_SAMPLE_MAX)
    if sample_max > 20000:
        warnings.append(f"采样上限 {sample_max} 过大，扫描耗时会明显变长")
    if sample_max < 50:
        warnings.append(f"采样上限 {sample_max} 太小，可能没有可用结果")

    if settings.get("scan_mode") == "httping" and threshold * HTTPING_SCALE_TLS > 2000:
        warnings.append("HTTPing 模式下阈值换算后超过 2000ms，筛选形同虚设，建议调低基础阈值")

    w_speed = float(settings.get("score_speed_weight", 3.0) or 0)
    w_lat = float(settings.get("score_latency_weight", 3.0) or 0)
    if w_speed == 0 and w_lat == 0:
        warnings.append("评分权重全为 0，综合评分将失去意义")

    if settings.get("http_enabled") and settings.get("allow_lan") and not (settings.get("http_token") or "").strip():
        warnings.append("HTTP 面板已允许局域网访问但未设置 Token，任何内网设备都能操控扫描任务，建议设置 Token")

    port = int(settings.get("http_port", 17443) or 17443)
    if not (1 <= port <= 65535):
        warnings.append(f"HTTP 服务端口 {port} 无效")

    min_speed = float(settings.get("min_speed", 0) or 0)
    if min_speed > 50:
        warnings.append(f"测速阈值 {min_speed} MB/s 过高，绝大多数节点会被筛掉")

    return warnings
