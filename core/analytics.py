#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import defaultdict
from typing import Dict, List

from core.constants import AIRPORT_CODES


def region_stats(results: List[Dict]) -> List[Dict]:
    """按地区码统计，返回按数量降序: [{'code','name','count'}]（忽略 UNKNOWN）。"""
    counter = defaultdict(int)
    names = {}
    for r in results:
        code = (r.get('iata_code') or '').upper()
        if not code or code == 'UNKNOWN':
            continue
        counter[code] += 1
        names[code] = r.get('chinese_name') or AIRPORT_CODES.get(code, code)

    stats = [
        {'code': code, 'name': names.get(code) or AIRPORT_CODES.get(code, code), 'count': cnt}
        for code, cnt in counter.items()
    ]
    stats.sort(key=lambda x: x['count'], reverse=True)
    return stats


def filter_by_region(results: List[Dict], region_code: str) -> List[Dict]:
    code = (region_code or '').upper()
    if not code:
        return list(results)
    return [r for r in results if (r.get('iata_code') or '').upper() == code]


def filter_by_latency(results: List[Dict], max_latency: float) -> List[Dict]:
    return [r for r in results if (r.get('latency') or 0) < max_latency]
