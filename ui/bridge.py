#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PySide6.QtCore import QObject, Signal

from service.task_manager import task_manager
from service.events import (
    EV_LOG, EV_PROGRESS, EV_FUNNEL,
    EV_SCAN_DONE, EV_SPEED_PROGRESS, EV_SPEED_DONE,
)


class WorkerBridge(QObject):
    """事件总线 → Qt 信号桥。

    工作线程 emit → 本对象以 QueuedConnection 转发到主线程槽函数。
    """

    progress_update = Signal(int, int, int, float)
    status_message = Signal(str)
    funnel_updated = Signal(dict)
    scan_completed = Signal(list)
    scan_aborted = Signal()
    speed_progress = Signal(int, int, float)
    speed_completed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        bus = task_manager.bus
        bus.subscribe(EV_LOG, self.status_message.emit)
        bus.subscribe(EV_PROGRESS, lambda p: self.progress_update.emit(*p))
        bus.subscribe(EV_FUNNEL, self.funnel_updated.emit)
        bus.subscribe(EV_SPEED_PROGRESS, lambda p: self.speed_progress.emit(*p))
        bus.subscribe(EV_SCAN_DONE, self._on_scan_done)
        bus.subscribe(EV_SPEED_DONE, self.speed_completed.emit)

    def _on_scan_done(self, results):
        if results is not None:
            self.scan_completed.emit(results)
        else:
            self.scan_aborted.emit()
