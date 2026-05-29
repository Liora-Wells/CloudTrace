#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ssl
import socket
import time
import asyncio
import aiohttp
import logging
from typing import Optional

from core.compat import IS_WIN7
from core.constants import AIRPORT_CODES


logger = logging.getLogger("CloudTrace")


def create_compat_ssl_context():
    ctx = ssl.create_default_context()
    if IS_WIN7:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        if hasattr(ssl, 'TLSVersion'):
            try:
                ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                ctx.maximum_version = ssl.TLSVersion.TLSv1_2
            except AttributeError:
                pass
        else:
            ctx.options |= ssl.OP_NO_TLSv1_3
            ctx.options |= ssl.OP_NO_TLSv1_1
            ctx.options |= ssl.OP_NO_TLSv1
            ctx.options |= ssl.OP_NO_SSLv2
            ctx.options |= ssl.OP_NO_SSLv3
    return ctx


def get_iata_code_from_ip(ip: str, timeout: int = 3) -> Optional[str]:
    test_host = "speed.cloudflare.com"
    if ':' in ip:
        urls = [f"https://[{ip}]/cdn-cgi/trace", f"http://[{ip}]/cdn-cgi/trace"]
    else:
        urls = [f"https://{ip}/cdn-cgi/trace", f"http://{ip}/cdn-cgi/trace"]

    for url in urls:
        try:
            ctx = create_compat_ssl_context()
            if url.startswith('https://'):
                use_ssl = True
                host = url[8:].split('/')[0].strip('[]') if '[' in url else url[8:].split('/')[0]
            else:
                use_ssl = False
                host = url[7:].split('/')[0].strip('[]') if '[' in url else url[7:].split('/')[0]
            port = 443 if use_ssl else 80

            if ':' in host:
                addrinfo = socket.getaddrinfo(host, port, socket.AF_INET6, socket.SOCK_STREAM)
                family, socktype, proto, canonname, sockaddr = addrinfo[0]
                s = socket.socket(family, socktype, proto)
                s.settimeout(timeout)
                s.connect(sockaddr)
            else:
                s = socket.create_connection((host, port), timeout=timeout)

            if use_ssl:
                s = ctx.wrap_socket(s, server_hostname=test_host)

            request = f"GET /cdn-cgi/trace HTTP/1.1\r\nHost: {test_host}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n".encode()
            s.sendall(request)

            data = b""
            body = b""
            while True:
                try:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\r\n\r\n" in data:
                        header_end = data.find(b"\r\n\r\n")
                        body = data[header_end + 4:]
                        break
                except socket.timeout:
                    break
            s.close()

            response_text = body.decode('utf-8', errors='ignore')
            for line in response_text.splitlines():
                if line.startswith('colo='):
                    colo_value = line.split('=', 1)[1].strip()
                    if colo_value and colo_value.upper() != 'UNKNOWN':
                        return colo_value.upper()

            if b'CF-RAY' in data:
                for line in data.decode('utf-8', errors='ignore').split('\r\n'):
                    if line.startswith('CF-RAY:'):
                        cf_ray = line.split(':', 1)[1].strip()
                        if '-' in cf_ray:
                            parts = cf_ray.split('-')
                            for part in parts[-2:]:
                                if len(part) == 3 and part.isalpha():
                                    return part.upper()
        except Exception:
            continue
    return None


async def get_iata_code_async(session: aiohttp.ClientSession, ip: str, timeout: int = 3) -> Optional[str]:
    test_host = "speed.cloudflare.com"
    if ':' in ip:
        urls = [f"https://[{ip}]/cdn-cgi/trace", f"http://[{ip}]/cdn-cgi/trace"]
    else:
        urls = [f"https://{ip}/cdn-cgi/trace", f"http://{ip}/cdn-cgi/trace"]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Host": test_host
    }
    ssl_ctx = create_compat_ssl_context()

    for url in urls:
        try:
            use_ssl = url.startswith('https://')
            ssl_context = ssl_ctx if use_ssl else None
            async with session.get(
                url, headers=headers, ssl=ssl_context,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=False
            ) as response:
                if response.status == 200:
                    text = await response.text()
                    for line in text.strip().split('\n'):
                        if line.startswith('colo='):
                            colo_value = line.split('=', 1)[1].strip()
                            if colo_value and colo_value.upper() != 'UNKNOWN':
                                return colo_value.upper()
                    if 'CF-RAY' in response.headers:
                        cf_ray = response.headers['CF-RAY']
                        if '-' in cf_ray:
                            parts = cf_ray.split('-')
                            for part in parts[-2:]:
                                if len(part) == 3 and part.isalpha():
                                    return part.upper()
        except Exception:
            continue
    return None


def get_iata_translation(iata_code: str) -> str:
    return AIRPORT_CODES.get(iata_code, iata_code)


async def async_tcp_ping(ip: str, port: int, timeout: float = 1.0) -> Optional[float]:
    start_time = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        latency = (time.monotonic() - start_time) * 1000
        writer.close()
        await writer.wait_closed()
        return round(latency, 2)
    except Exception:
        return None


async def measure_tcp_latency(ip: str, port: int, ping_times: int = 4, timeout: float = 1.0) -> Optional[float]:
    latencies = []
    for i in range(ping_times):
        latency = await async_tcp_ping(ip, port, timeout)
        if latency is not None:
            latencies.append(latency)
        if i < ping_times - 1:
            await asyncio.sleep(0.05)
    if latencies:
        return min(latencies)
    return None
