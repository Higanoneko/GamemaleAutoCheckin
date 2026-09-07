# -*- coding: utf-8 -*-
"""Cooperative stop controller used by local and QingLong runners."""

import threading


class StopController:
    """
    基于 threading.Event 的优雅停止控制器。

    用 event.wait(timeout) 替代 time.sleep(timeout)，当收到停止信号时
    event 被 set()，wait() 立即返回，实现可中断的等待。
    """

    def __init__(self) -> None:
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        """请求停止，所有 interruptible_sleep 立即唤醒"""
        self._stop_event.set()

    def is_stopped(self) -> bool:
        """检查是否已请求停止"""
        return self._stop_event.is_set()

    def interruptible_sleep(self, seconds: float) -> None:
        """
        可中断的等待。等效于 time.sleep(seconds)，
        但当 request_stop() 被调用时会立即返回。
        """
        self._stop_event.wait(timeout=seconds)

    def reset(self) -> None:
        """重置停止状态"""
        self._stop_event.clear()


stop_controller: StopController = StopController()
