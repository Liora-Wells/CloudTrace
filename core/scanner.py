#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import random
import time
import socket
import asyncio
import aiohttp
import ipaddress
import logging
from datetime import datetime
from typing import List, Optional, Dict, Callable

from core.constants import load_or_update_ip_cache, AIRPORT_CODES, PORT_OPTIONS
from core.network import (
    get_iata_code_async, get_iata_code_from_ip, verify_cloudflare,
    get_iata_translation, measure_tcp_latency, measure_http_latency,
    download_speed, DEFAULT_TEST_HOST,
)
from core.scoring import apply_scores


logger = logging.getLogger("CloudTrace")

# HTTPS 端口集合（HTTPing 时决定用 TLS 还是明文）
HTTPS_PORTS = {int(p) for p in PORT_OPTIONS}  # 443/2053/2083/2087/2096/8443
# HTTPing 延迟相对 TCPing 的放大倍率（仅作阈值/颜色等级参考，非精确换算）
HTTPING_SCALE_TLS = 4.0
HTTPING_SCALE_NO_TLS = 1.3

DEFAULT_SAMPLE_MAX = 5000


def effective_latency_threshold(threshold: int, scan_mode: str, port: int) -> float:
    """按扫描模式换算实际延迟阈值。"""
    if scan_mode != "httping":
        return float(threshold)
    scale = HTTPING_SCALE_TLS if port in HTTPS_PORTS else HTTPING_SCALE_NO_TLS
    return threshold * scale


class BaseScanner:
    def __init__(self, log_callback=None, progress_callback=None, funnel_callback=None,
                 port=443, max_workers=200, timeout=1.0, ping_times=3,
                 latency_threshold=230, custom_cidrs=None,
                 sample_max=DEFAULT_SAMPLE_MAX, scan_mode="tcping"):
        self.max_workers = max_workers
        self.timeout = timeout
        self.ping_times = ping_times
        self.latency_threshold = latency_threshold
        self.running = True
        self.log_callback = log_callback
        self.progress_callback = progress_callback
        self.funnel_callback = funnel_callback
        self.port = port
        self.custom_cidrs = custom_cidrs or {}
        self.sample_max = max(1, int(sample_max or DEFAULT_SAMPLE_MAX))
        self.scan_mode = scan_mode if scan_mode in ("tcping", "httping") else "tcping"
        # 逐 IP 覆盖表（非标导入时使用）：ip → port / ip_version
        self._entry_ports: Dict[str, int] = {}
        self._entry_versions: Dict[str, int] = {}
        # 漏斗计数：生成 → 延迟达标 → 有地区码
        self.funnel = {"generated": 0, "latency_ok": 0, "with_iata": 0}

    @property
    def ip_version(self) -> int:
        raise NotImplementedError

    @property
    def ip_label(self) -> str:
        return "IPv4" if self.ip_version == 4 else "IPv6"

    def port_for(self, ip: str) -> int:
        return self._entry_ports.get(ip, self.port)

    def version_for(self, ip: str) -> int:
        return self._entry_versions.get(ip, self.ip_version)

    def connector_family(self):
        return socket.AF_INET6 if self.ip_version == 6 else None

    def resolve_cidrs(self) -> List[str]:
        """按 CIDR 模式合并官方段与自定义段（IPv4/IPv6 共用逻辑）。"""
        cidr_mode = self.custom_cidrs.get("mode", "仅官方")
        custom_list = self.custom_cidrs.get("list", [])
        official_cidrs = load_or_update_ip_cache(self.ip_version)

        if cidr_mode == "仅自定义":
            return list(custom_list)
        if cidr_mode == "官方+自定义":
            return list(official_cidrs) + list(custom_list)
        return list(official_cidrs)

    def generate_ips_from_cidrs(self) -> List[str]:
        raise NotImplementedError

    async def test_ip_latency(self, session, ip):
        if not self.running:
            return None
        port = self.port_for(ip)
        if self.scan_mode == "httping":
            use_tls = port in HTTPS_PORTS
            return await measure_http_latency(session, ip, port, self.timeout, use_tls)
        return await measure_tcp_latency(ip, port, self.ping_times, self.timeout)

    async def test_single_ip(self, session, ip):
        if not self.running:
            return None
        port = self.port_for(ip)
        threshold = effective_latency_threshold(self.latency_threshold, self.scan_mode, port)
        latency = await self.test_ip_latency(session, ip)
        if latency is not None and latency < threshold:
            self.funnel["latency_ok"] += 1
            iata_code = None
            if self.running:
                try:
                    iata_code = await get_iata_code_async(session, ip, self.timeout)
                except Exception as e:
                    if self.log_callback:
                        self.log_callback(f"获取地区码失败 {ip}: {str(e)}")
            if iata_code:
                self.funnel["with_iata"] += 1
            return {
                'ip': ip, 'latency': latency, 'iata_code': iata_code,
                'chinese_name': get_iata_translation(iata_code) if iata_code else "未知地区",
                'success': True, 'ip_version': self.version_for(ip),
                'scan_time': datetime.now().strftime("%H:%M:%S"),
                'port': port, 'ping_times': self.ping_times,
                'scan_mode': self.scan_mode,
            }
        return None

    async def batch_test_ips(self, ip_list: List[str]):
        semaphore = asyncio.Semaphore(self.max_workers)

        async def test_with_semaphore(session, ip):
            async with semaphore:
                return await self.test_single_ip(session, ip)

        connector_kwargs = {
            'limit': self.max_workers, 'force_close': True,
            'enable_cleanup_closed': True, 'limit_per_host': 0
        }
        family = self.connector_family()
        if family:
            connector_kwargs['family'] = family

        connector = aiohttp.TCPConnector(**connector_kwargs)
        successful_results = []
        start_time = time.time()

        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = []
            for ip in ip_list:
                if not self.running:
                    break
                tasks.append(asyncio.create_task(test_with_semaphore(session, ip)))

            completed = 0
            total = len(tasks)
            last_update_time = time.time()

            pending = set(tasks)
            while pending:
                if not self.running:
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    break
                done, pending = await asyncio.wait(pending, timeout=0.5, return_when=asyncio.FIRST_COMPLETED)

                for future in done:
                    completed += 1
                    try:
                        result = future.result()
                        if result:
                            successful_results.append(result)
                    except Exception:
                        pass

                current_time = time.time()
                if current_time - last_update_time >= 0.5 or completed == total:
                    elapsed = current_time - start_time
                    ips_per_second = completed / elapsed if elapsed > 0 else 0
                    if self.progress_callback:
                        self.progress_callback(completed, total, len(successful_results), ips_per_second)
                    last_update_time = current_time

        return successful_results

    async def run_scan_async(self):
        try:
            if self.log_callback:
                mode_txt = "HTTPing (TTFB)" if self.scan_mode == "httping" else "TCPing (握手)"
                self.log_callback(f"正在从Cloudflare {self.ip_label} IP段生成随机IP... (端口: {self.port}, 模式: {mode_txt})")
                self.log_callback(f"并发数: {self.max_workers} | 延迟阈值: {self.latency_threshold}ms | 采样上限: {self.sample_max}")
            ip_list = self.generate_ips_from_cidrs()
            if not ip_list:
                if self.log_callback:
                    self.log_callback(f"错误: 未能生成{self.ip_label} IP列表")
                return None
            self.funnel["generated"] = len(ip_list)
            if self.funnel_callback:
                self.funnel_callback(dict(self.funnel))
            if self.log_callback:
                self.log_callback(f"已生成 {len(ip_list)} 个随机{self.ip_label} IP（已去重）")
                self.log_callback(f"开始延迟测试...")
            results = await self.batch_test_ips(ip_list)
            if not self.running:
                if self.log_callback:
                    self.log_callback(f"{self.ip_label}扫描被用户中止")
                return None
            if results:
                with_iata = sum(1 for r in results if r.get('iata_code'))
                if self.log_callback:
                    self.log_callback(
                        f"{self.ip_label}扫描完成: 共{len(results)}个IP可用，{with_iata}个获取地区码"
                        f"（{self.funnel['generated']} → {self.funnel['latency_ok']} → {with_iata}）"
                    )
            return results
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"{self.ip_label}扫描过程中出现错误: {str(e)}")
            logger.exception("扫描异常")
            return None

    def stop(self):
        self.running = False


class IPv4Scanner(BaseScanner):
    @property
    def ip_version(self):
        return 4

    def generate_ips_from_cidrs(self) -> List[str]:
        ip_list = []
        seen = set()

        for cidr in self.resolve_cidrs():
            try:
                network = ipaddress.ip_network(cidr, strict=False)
                if network.version != 4:
                    continue
                for subnet in network.subnets(new_prefix=24):
                    hosts = list(subnet.hosts())
                    for ip in random.sample(hosts, min(2, len(hosts))):
                        s = str(ip)
                        if s not in seen:
                            seen.add(s)
                            ip_list.append(s)
            except ValueError as e:
                if self.log_callback:
                    self.log_callback(f"处理CIDR {cidr} 时出错: {e}")

        if len(ip_list) > self.sample_max:
            ip_list = random.sample(ip_list, self.sample_max)
        return ip_list


class IPv6Scanner(BaseScanner):
    @property
    def ip_version(self):
        return 6

    def __init__(self, **kwargs):
        kwargs.setdefault('latency_threshold', 320)
        kwargs.setdefault('ping_times', 2)
        super().__init__(**kwargs)

    def generate_ips_from_cidrs(self) -> List[str]:
        ip_list = []
        seen = set()

        for cidr in self.resolve_cidrs():
            try:
                network = ipaddress.ip_network(cidr, strict=False)
                if network.version != 6:
                    continue
                if network.num_addresses <= 2:
                    continue
                prefixlen = network.prefixlen
                if prefixlen <= 32:
                    sample_size = 2800
                elif prefixlen <= 40:
                    sample_size = 500
                else:
                    sample_size = 200

                attempts = 0
                added = 0
                max_attempts = sample_size * 3
                while added < sample_size and attempts < max_attempts:
                    attempts += 1
                    random_ip_int = random.randint(
                        int(network.network_address) + 1,
                        int(network.broadcast_address) - 1
                    )
                    s = str(ipaddress.IPv6Address(random_ip_int))
                    if s not in seen:
                        seen.add(s)
                        ip_list.append(s)
                        added += 1
            except ValueError as e:
                if self.log_callback:
                    self.log_callback(f"处理CIDR {cidr} 时出错: {e}")

        if len(ip_list) > self.sample_max:
            ip_list = random.sample(ip_list, self.sample_max)
        return ip_list


class ImportedScanner(BaseScanner):
    """非标 IP:端口 直测扫描器：跳过 CIDR 采样，逐条直测。"""

    def __init__(self, entries=None, **kwargs):
        super().__init__(**kwargs)
        self.entries = list(entries or [])
        seen = set()
        versions = set()
        for e in self.entries:
            ip = e['ip']
            if ip in seen:
                continue
            seen.add(ip)
            self._entry_ports[ip] = int(e.get('port', self.port))
            self._entry_versions[ip] = int(e.get('ip_version', 4))
            versions.add(self._entry_versions[ip])
        self._versions = versions or {4}

    @property
    def ip_version(self):
        return 6 if self._versions == {6} else 4

    @property
    def ip_label(self) -> str:
        if len(self._versions) > 1:
            return "非标(混合)"
        return "IPv4" if self.ip_version == 4 else "IPv6"

    def connector_family(self):
        # 混合列表不强制 family，交由系统路由选择
        if self._versions == {6}:
            return socket.AF_INET6
        return None

    def resolve_cidrs(self):
        return []

    def generate_ips_from_cidrs(self) -> List[str]:
        return [e['ip'] for e in self.entries]


class SpeedTestTask:
    """下载测速任务（普通线程类，无 Qt 依赖；由 TaskManager 驱动）。"""

    def __init__(self, results, region_code=None, max_test_count=10, current_port=443,
                 speed_url="auto", min_speed=0.0, selected_ips=None,
                 verify_nodes=True, score_weights=None,
                 download_interval=3, label=None):
        self.results = results
        self.region_code = region_code.upper() if region_code else None
        self.max_test_count = max_test_count
        self.download_interval = max(0, int(download_interval))
        self.download_time_limit = 3
        self.running = True
        self.current_port = current_port
        self.min_speed = float(min_speed or 0.0)
        self.selected_ips = selected_ips  # 单点/勾选测速：直接给定 IP 信息列表
        self.verify_nodes = bool(verify_nodes)
        self.score_weights = score_weights
        self.label = label  # 覆盖默认 test_type 文案
        self.test_host, self.download_path = self._parse_speed_url(speed_url)
        # 回调由 TaskManager 注入
        self.log_callback: Optional[Callable[[str], None]] = None
        self.progress_callback: Optional[Callable[[int, int, int], None]] = None

    @staticmethod
    def _parse_speed_url(url: str):
        """解析测速地址 → (host, path)。仅支持 Cloudflare 代理的域名（连的是 CF IP）。"""
        raw = (url or "auto").strip()
        if not raw or raw.lower() == "auto":
            return DEFAULT_TEST_HOST, "/__down?bytes=50000000"
        raw = raw.replace("https://", "").replace("http://", "")
        host, sep, rest = raw.partition("/")
        path = "/" + rest if sep else "/"
        if "?" not in path and "bytes=" not in path:
            path += ("&" if "?" in path else "?") + "bytes=50000000"
        return host or DEFAULT_TEST_HOST, path

    def _log(self, msg: str):
        if self.log_callback:
            self.log_callback(msg)

    def _pick_targets(self) -> List[Dict]:
        if self.selected_ips:
            targets = list(self.selected_ips)
            self._log(f"指定测速: {len(targets)} 个IP")
            return targets

        if self.region_code:
            filtered = [r for r in self.results
                        if r.get('iata_code') and r['iata_code'].upper() == self.region_code]
            region_name = AIRPORT_CODES.get(self.region_code, '未知地区')
            self._log(f"开始地区测速：{self.region_code} ({region_name}) (端口: {self.current_port})")
            self._log(f"找到 {len(filtered)} 个 {self.region_code} 地区的IP")
        else:
            filtered = list(self.results)
            self._log(f"开始完全测速 (端口: {self.current_port})")

        filtered.sort(key=lambda x: x.get('latency', float('inf')))
        return filtered[:min(self.max_test_count, len(filtered))]

    def run(self) -> List[Dict]:
        try:
            if not self.results:
                self._log("错误：没有可用的IP进行测速")
                return []

            target_ips = self._pick_targets()
            if not target_ips:
                self._log("没有找到可用的IP进行测速")
                return []

            test_type = self.label or ("单点测速" if self.selected_ips
                                       else "地区测速" if self.region_code else "完全测速")
            self._log(f"{test_type}：将对 {len(target_ips)} 个IP进行测速")

            speed_results = []
            skipped = 0
            for i, ip_info in enumerate(target_ips):
                if not self.running:
                    break
                ip = ip_info['ip']
                port = int(ip_info.get('port') or self.current_port)
                latency = ip_info.get('latency', 0)
                self._log(f"[{i+1}/{len(target_ips)}] 正在测速 {ip}(端口: {port})")
                if self.progress_callback:
                    self.progress_callback(i + 1, len(target_ips), 0)

                # 可用性验证：确认节点确实是 Cloudflare（防劫持/非CF）
                verified = None
                if self.verify_nodes:
                    verified = verify_cloudflare(ip, timeout=3)
                    if not verified:
                        skipped += 1
                        self._log(f"  可用性验证失败（非 Cloudflare 节点），跳过: {ip}")
                        continue

                speed, err = download_speed(
                    ip, port, host=self.test_host,
                    path=self.download_path, time_limit=self.download_time_limit,
                    should_continue=lambda: self.running,
                )
                if err:
                    self._log(f"  测速失败 {ip}: {err}")

                # 优先复用扫描阶段已解析的地区码，缺失时才回查
                colo = ip_info.get('iata_code')
                if not colo or colo == "Unknown":
                    colo = get_iata_code_from_ip(ip, timeout=3)
                colo = colo.upper() if colo else 'UNKNOWN'
                speed_result = {
                    'ip': ip, 'latency': latency, 'download_speed': speed,
                    'iata_code': colo,
                    'chinese_name': AIRPORT_CODES.get(colo, '未知地区'),
                    'test_type': test_type, 'port': port,
                    'verified': verified,
                }
                speed_results.append(speed_result)
                self._log(f"  测速结果: {speed} MB/s, 地区: {speed_result['chinese_name']}")

                if i < len(target_ips) - 1:
                    for _ in range(self.download_interval * 10):
                        if not self.running:
                            break
                        time.sleep(0.1)

            if skipped:
                self._log(f"可用性验证淘汰 {skipped} 个非 CF 节点")
            if self.min_speed > 0:
                before = len(speed_results)
                speed_results = [r for r in speed_results if r['download_speed'] >= self.min_speed]
                if before != len(speed_results):
                    self._log(f"阈值筛选: {before} → {len(speed_results)} (≥ {self.min_speed} MB/s)")

            # 综合评分排序（score = W_speed×MB/s ÷ (1 + W_latency×lat秒)）
            speed_results = apply_scores(speed_results, self.score_weights)
            if speed_results:
                best = speed_results[0]
                self._log(
                    f"测速完成！成功 {len(speed_results)}/{len(target_ips)} 个IP，"
                    f"最优 {best['ip']} ({best['download_speed']} MB/s, 评分 {best.get('score')})"
                )
            else:
                self._log("所有IP测速失败")
            return speed_results
        except Exception as e:
            self._log(f"测速过程中出现错误: {str(e)}")
            logger.exception("测速异常")
            return []

    def stop(self):
        self.running = False
