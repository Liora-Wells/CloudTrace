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
from typing import List, Optional, Dict

from PySide6.QtCore import QThread, Signal

from config import (
    IS_WIN7, get_event_loop_policy, load_or_update_ip_cache,
    AIRPORT_CODES,
)
from network import (
    create_compat_ssl_context, get_iata_code_async, get_iata_code_from_ip,
    get_iata_translation, measure_tcp_latency,
)


logger = logging.getLogger("CloudTrace")


class BaseScanner:
    def __init__(self, log_callback=None, progress_callback=None, port=443,
                 max_workers=200, timeout=1.0, ping_times=3, latency_threshold=230,
                 custom_cidrs=None):
        self.max_workers = max_workers
        self.timeout = timeout
        self.ping_times = ping_times
        self.latency_threshold = latency_threshold
        self.running = True
        self.log_callback = log_callback
        self.progress_callback = progress_callback
        self.port = port
        self.custom_cidrs = custom_cidrs or {}

    @property
    def ip_version(self) -> int:
        raise NotImplementedError

    @property
    def ip_label(self) -> str:
        return "IPv4" if self.ip_version == 4 else "IPv6"

    def generate_ips_from_cidrs(self) -> List[str]:
        raise NotImplementedError

    async def test_ip_latency(self, session, ip):
        if not self.running:
            return None
        return await measure_tcp_latency(ip, self.port, self.ping_times, self.timeout)

    async def test_single_ip(self, session, ip):
        if not self.running:
            return None
        latency = await self.test_ip_latency(session, ip)
        if latency is not None and latency < self.latency_threshold:
            iata_code = None
            if self.running:
                try:
                    iata_code = await get_iata_code_async(session, ip, self.timeout)
                except Exception as e:
                    if self.log_callback:
                        self.log_callback(f"获取地区码失败 {ip}: {str(e)}")
            return {
                'ip': ip, 'latency': latency, 'iata_code': iata_code,
                'chinese_name': get_iata_translation(iata_code) if iata_code else "未知地区",
                'success': True, 'ip_version': self.ip_version,
                'scan_time': datetime.now().strftime("%H:%M:%S"),
                'port': self.port, 'ping_times': self.ping_times
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
        if self.ip_version == 6:
            connector_kwargs['family'] = socket.AF_INET6

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
                self.log_callback(f"正在从Cloudflare {self.ip_label} IP段生成随机IP... (端口: {self.port})")
                self.log_callback(f"并发数: {self.max_workers} | 延迟阈值: {self.latency_threshold}ms")
            ip_list = self.generate_ips_from_cidrs()
            if not ip_list:
                if self.log_callback:
                    self.log_callback(f"错误: 未能生成{self.ip_label} IP列表")
                return None
            if self.log_callback:
                self.log_callback(f"已生成 {len(ip_list)} 个随机{self.ip_label} IP")
                self.log_callback(f"开始延迟测试...")
            results = await self.batch_test_ips(ip_list)
            if not self.running:
                if self.log_callback:
                    self.log_callback(f"{self.ip_label}扫描被用户中止")
                return None
            if results:
                with_iata = sum(1 for r in results if r.get('iata_code'))
                if self.log_callback:
                    self.log_callback(f"{self.ip_label}扫描完成: 共{len(results)}个IP可用，{with_iata}个获取地区码")
            return results
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"{self.ip_label}扫描过程中出现错误: {str(e)}")
            return None

    def stop(self):
        self.running = False


class IPv4Scanner(BaseScanner):
    @property
    def ip_version(self):
        return 4

    def generate_ips_from_cidrs(self) -> List[str]:
        ip_list = []
        cidr_mode = self.custom_cidrs.get("mode", "仅官方")
        custom_list = self.custom_cidrs.get("list", [])
        official_cidrs = load_or_update_ip_cache(4)

        if cidr_mode == "仅自定义":
            cidrs = custom_list
        elif cidr_mode == "官方+自定义":
            cidrs = official_cidrs + custom_list
        else:
            cidrs = official_cidrs

        for cidr in cidrs:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
                if network.version != 4:
                    continue
                for subnet in network.subnets(new_prefix=24):
                    hosts = list(subnet.hosts())
                    for ip in random.sample(hosts, min(2, len(hosts))):
                        ip_list.append(str(ip))
            except ValueError as e:
                if self.log_callback:
                    self.log_callback(f"处理CIDR {cidr} 时出错: {e}")
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
        cidr_mode = self.custom_cidrs.get("mode", "仅官方")
        custom_list = self.custom_cidrs.get("list", [])
        official_cidrs = load_or_update_ip_cache(6)

        if cidr_mode == "仅自定义":
            cidrs = custom_list
        elif cidr_mode == "官方+自定义":
            cidrs = official_cidrs + custom_list
        else:
            cidrs = official_cidrs

        for cidr in cidrs:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
                if network.version != 6:
                    continue
                if network.num_addresses > 2:
                    prefixlen = network.prefixlen
                    if prefixlen <= 32:
                        sample_size = 2800
                    elif prefixlen <= 40:
                        sample_size = 500
                    else:
                        sample_size = 200

                    max_hosts = min(sample_size, network.num_addresses - 2)
                    for _ in range(max_hosts):
                        random_ip_int = random.randint(
                            int(network.network_address) + 1,
                            int(network.broadcast_address) - 1
                            )
                        ip_list.append(str(ipaddress.IPv6Address(random_ip_int)))
            except ValueError as e:
                if self.log_callback:
                    self.log_callback(f"处理CIDR {cidr} 时出错: {e}")
        return ip_list


class ScanWorker(QThread):
    progress_update = Signal(int, int, int, float)
    status_message = Signal(str)
    scan_completed = Signal(list)

    def __init__(self, scanner: BaseScanner):
        super().__init__()
        self.scanner = scanner

    def run(self):
        self.scanner.log_callback = lambda msg: self.status_message.emit(msg)
        self.scanner.progress_callback = lambda c, t, s, sp: self.progress_update.emit(c, t, s, sp)

        asyncio.set_event_loop_policy(get_event_loop_policy())

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(self.scanner.run_scan_async())
            if results is not None:
                self.scan_completed.emit(results)
        except asyncio.CancelledError:
            pass
        finally:
            loop.close()

    def stop(self):
        if self.scanner:
            self.scanner.stop()


class SpeedTestWorker(QThread):
    progress_update = Signal(int, int, float)
    status_message = Signal(str)
    speed_test_completed = Signal(list)

    def __init__(self, results, region_code=None, max_test_count=10, current_port=443):
        super().__init__()
        self.results = results
        self.region_code = region_code.upper() if region_code else None
        self.max_test_count = max_test_count
        self.download_interval = 3
        self.download_time_limit = 3
        self.test_host = "speed.cloudflare.com"
        self.running = True
        self.current_port = current_port

    def download_speed(self, ip, port):
        ctx = create_compat_ssl_context()
        req = (
            "GET /__down?bytes=50000000 HTTP/1.1\r\n"
            f"Host: {self.test_host}\r\n"
            "User-Agent: Mozilla/5.0\r\n"
            "Accept: */*\r\n"
            "Connection: close\r\n\r\n"
        ).encode()
        try:
            if ':' in ip:
                addrinfo = socket.getaddrinfo(ip, port, socket.AF_INET6, socket.SOCK_STREAM)
                family, socktype, proto, canonname, sockaddr = addrinfo[0]
                sock = socket.socket(family, socktype, proto)
                sock.settimeout(3)
                sock.connect(sockaddr)
            else:
                sock = socket.create_connection((ip, port), timeout=3)
            ss = ctx.wrap_socket(sock, server_hostname=self.test_host)
            ss.settimeout(1.0)
            ss.sendall(req)
            start = time.time()

            header_buf = b""
            body = 0
            header_done = False

            while time.time() - start < self.download_time_limit:
                if not self.running:
                    break
                try:
                    buf = ss.recv(8192)
                except socket.timeout:
                    continue
                if not buf:
                    break
                if not header_done:
                    header_buf += buf
                    if b"\r\n\r\n" in header_buf:
                        header_done = True
                        body += len(header_buf.split(b"\r\n\r\n", 1)[1])
                else:
                    body += len(buf)
            ss.close()
            dur = time.time() - start
            return round((body / 1024 / 1024) / max(dur, 0.1), 2)
        except Exception as e:
            self.status_message.emit(f"测速失败 {ip}: {str(e)}")
            return 0.0

    def run(self):
        try:
            if not self.results:
                self.status_message.emit("错误：没有可用的IP进行测速")
                self.speed_test_completed.emit([])
                return

            if self.region_code:
                filtered_results = [r for r in self.results if r.get('iata_code') and r['iata_code'].upper() == self.region_code]
                region_name = AIRPORT_CODES.get(self.region_code, '未知地区')
                self.status_message.emit(f"开始地区测速：{self.region_code} ({region_name}) (端口: {self.current_port})")
                self.status_message.emit(f"找到 {len(filtered_results)} 个 {self.region_code} 地区的IP")
            else:
                filtered_results = self.results
                self.status_message.emit(f"开始完全测速 (端口: {self.current_port})")

            if not filtered_results:
                self.status_message.emit("没有找到可用的IP进行测速")
                self.speed_test_completed.emit([])
                return

            filtered_results.sort(key=lambda x: x.get('latency', float('inf')))
            target_ips = filtered_results[:min(self.max_test_count, len(filtered_results))]

            test_type = "地区测速" if self.region_code else "完全测速"
            self.status_message.emit(f"{test_type}：将对 {len(target_ips)} 个IP进行测速")

            speed_results = []
            for i, ip_info in enumerate(target_ips):
                if not self.running:
                    break
                ip = ip_info['ip']
                latency = ip_info.get('latency', 0)
                self.status_message.emit(f"[{i+1}/{len(target_ips)}] 正在测速 {ip}(端口: {self.current_port})")
                self.progress_update.emit(i+1, len(target_ips), 0)
                download_speed = self.download_speed(ip, self.current_port)
                colo = get_iata_code_from_ip(ip, timeout=3)
                if not colo or colo == "Unknown":
                    colo = ip_info.get('iata_code', 'UNKNOWN')
                speed_result = {
                    'ip': ip, 'latency': latency, 'download_speed': download_speed,
                    'iata_code': colo.upper() if colo else 'UNKNOWN',
                    'chinese_name': AIRPORT_CODES.get(colo.upper(), '未知地区') if colo else '未知地区',
                    'test_type': test_type, 'port': self.current_port
                }
                speed_results.append(speed_result)
                self.status_message.emit(f"  测速结果: {download_speed} MB/s, 地区: {speed_result['chinese_name']}")
                if i < len(target_ips) - 1:
                    for _ in range(self.download_interval * 10):
                        if not self.running:
                            break
                        time.sleep(0.1)

            speed_results.sort(key=lambda x: x['download_speed'], reverse=True)
            if speed_results:
                self.status_message.emit(f"测速完成！成功 {len(speed_results)}/{len(target_ips)} 个IP")
            else:
                self.status_message.emit("所有IP测速失败")
            self.speed_test_completed.emit(speed_results)
        except Exception as e:
            self.status_message.emit(f"测速过程中出现错误: {str(e)}")
            self.speed_test_completed.emit([])

    def stop(self):
        self.running = False
