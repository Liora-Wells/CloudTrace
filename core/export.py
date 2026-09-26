#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import io
import json
from datetime import datetime
from typing import Dict, List, Optional


# 可导出字段 → CSV 表头
SCAN_FIELDS = {
    'ip': 'IP地址',
    'iata_code': '地区码',
    'chinese_name': '地区',
    'latency': '延迟(ms)',
    'ip_version': 'IP版本',
    'port': '端口',
    'scan_mode': '扫描方式',
    'scan_time': '扫描时间',
}

SPEED_FIELDS = {
    'ip': 'IP地址',
    'iata_code': '地区码',
    'chinese_name': '地区',
    'latency': '延迟(ms)',
    'download_speed': '下载速度(MB/s)',
    'score': '综合评分',
    'verified': '可用性验证',
    'port': '端口',
    'test_type': '测速类型',
}


def fields_for(result_type: str) -> Dict[str, str]:
    return dict(SCAN_FIELDS) if result_type == "scan" else dict(SPEED_FIELDS)


def _select(results: List[Dict], result_type: str, fields: Optional[List[str]],
            qualified_only: bool, min_speed: float):
    data = list(results)
    if qualified_only and result_type == "speed":
        data = [r for r in data if (r.get('download_speed') or 0) >= min_speed]
    available = fields_for(result_type)
    selected = [k for k in available if fields is None or k in fields]
    return data, selected


def render_export(results: List[Dict], result_type: str,
                  fields: Optional[List[str]] = None,
                  qualified_only: bool = False,
                  min_speed: float = 0.0,
                  fmt: str = "csv") -> str:
    """把结果渲染为 CSV/JSON 文本（供文件导出与 HTTP 下载共用）。"""
    data, selected = _select(results, result_type, fields, qualified_only, min_speed)
    available = fields_for(result_type)

    if fmt == "json":
        payload = {
            'export_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'result_type': result_type,
            'count': len(data),
            'fields': selected,
            'results': [{k: r.get(k) for k in selected} for r in data],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    buf = io.StringIO()
    writer = csv.writer(buf)
    with_rank = (result_type == "speed" and 'ip' in selected)
    header = (["排名"] if with_rank else []) + [available[k] for k in selected]
    writer.writerow(header)
    for i, r in enumerate(data):
        row = [r.get(k, '') for k in selected]
        if with_rank:
            row.insert(0, i + 1)
        writer.writerow(row)
    return buf.getvalue()


def write_export(filepath: str, results: List[Dict], result_type: str,
                 fields: Optional[List[str]] = None,
                 qualified_only: bool = False,
                 min_speed: float = 0.0) -> int:
    """导出到文件（按扩展名判断 CSV/JSON）。返回实际导出条数。"""
    fmt = "json" if filepath.lower().endswith('.json') else "csv"
    data, _ = _select(results, result_type, fields, qualified_only, min_speed)
    content = render_export(results, result_type, fields, qualified_only, min_speed, fmt)
    encoding = "utf-8-sig" if fmt == "csv" else "utf-8"
    with open(filepath, 'w', encoding=encoding, newline='') as f:
        f.write(content)
    return len(data)
