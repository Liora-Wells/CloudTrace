#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import asyncio
import logging
import threading
from typing import Optional

from aiohttp import web

from service.api import create_app


logger = logging.getLogger("CloudTrace")


class HttpServer:
    """在独立线程的独立事件循环里运行 aiohttp 服务（与 Qt 主线程解耦）。"""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._app: Optional[web.Application] = None
        self.host: Optional[str] = None
        self.port: Optional[int] = None
        self.error: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def address(self) -> Optional[str]:
        if not self.is_running or not self.host or not self.port:
            return None
        shown = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        return f"http://{shown}:{self.port}/"

    def start(self, host: str = "127.0.0.1", port: int = 17443) -> bool:
        """启动服务；已在运行且地址一致则幂等返回 True。"""
        if self.is_running:
            if self.host == host and self.port == port:
                return True
            self.stop()

        self.error = None
        ready = threading.Event()

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            app = create_app()
            self._app = app

            async def _setup():
                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, host, port)
                await site.start()
                return runner

            try:
                runner = loop.run_until_complete(_setup())
            except Exception as e:
                self.error = str(e)
                logger.error("HTTP 服务启动失败: %s", e)
                ready.set()
                try:
                    loop.close()
                finally:
                    self._loop = None
                    self._app = None
                return

            self.host, self.port = host, port
            ready.set()
            logger.info("HTTP 服务已启动 http://%s:%s/", host, port)
            try:
                loop.run_forever()
            finally:
                try:
                    loop.run_until_complete(runner.cleanup())
                except Exception:
                    pass
                loop.close()
                self._loop = None
                self._app = None
                self.host = self.port = None

        self._thread = threading.Thread(target=_run, name="CloudTrace-HTTP", daemon=True)
        self._thread.start()
        ready.wait(timeout=5.0)
        if not ready.is_set():
            self.error = "启动超时"
            return False
        return self.error is None

    def stop(self, timeout: float = 5.0):
        loop = self._loop
        app = self._app
        thread = self._thread
        if not loop or not thread:
            return

        def _shutdown():
            if app is not None:
                ev = app.get("sse_stop")
                if ev is not None:
                    ev.set()
            try:
                fut = asyncio.ensure_future(self._drain(), loop=loop)
                fut.add_done_callback(lambda _f: loop.stop())
            except Exception:
                loop.stop()

        try:
            loop.call_soon_threadsafe(_shutdown)
        except RuntimeError:
            pass
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.warning("HTTP 服务线程未能在 %.1fs 内退出", timeout)
        self._thread = None

    async def _drain(self):
        """等待 SSE 连接自然退出（stop event 已置位）。"""
        await asyncio.sleep(1.2)


http_server = HttpServer()
