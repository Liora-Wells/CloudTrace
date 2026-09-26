#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Optional

# score = W_speed × 下载速度(MB/s) ÷ (1 + W_latency × 延迟(秒))
DEFAULT_SCORE_WEIGHTS = {"speed": 3.0, "latency": 3.0}


def score_result(result: Dict, weights: Optional[Dict] = None) -> float:
    """综合评分：带宽为主，延迟作分母惩罚（参考 cfnb 加权公式）。"""
    w = dict(DEFAULT_SCORE_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items() if v is not None})

    speed = float(result.get('download_speed') or 0.0)
    latency_ms = float(result.get('latency') or 0.0)
    raw = w['speed'] * speed / (1.0 + w['latency'] * (latency_ms / 1000.0))
    return round(raw, 1)


def apply_scores(results, weights: Optional[Dict] = None) -> list:
    """为测速结果批量写入 score 字段并按评分降序返回。"""
    for r in results:
        r['score'] = score_result(r, weights)
    results.sort(key=lambda x: (x.get('score') or 0.0), reverse=True)
    return results
