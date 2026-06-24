# -*- coding: utf-8 -*-
"""Public automation client that shares session, cookie, and login state across modules."""

import time
from typing import Any, Callable, Dict, List, Optional

import requests

from .config_utils import _coerce_config_bool, _coerce_config_list
from .constants import DDDDOCR_AVAILABLE, DEFAULT_TIMEOUT, ddddocr
from .credits import CreditsMixin
from .daily_tasks import DailyTasksMixin
from .http import create_session
from .login import LoginMixin
from .logging_utils import log_error
from .missions import MissionsMixin
from .online import OnlineTimeMixin
from .reports import ReportMixin
from .social import SocialMixin
from .stop_controller import StopController


class GamemaleAutomation(
    LoginMixin,
    MissionsMixin,
    OnlineTimeMixin,
    DailyTasksMixin,
    SocialMixin,
    CreditsMixin,
    ReportMixin,
):
    """Gamemale 自动化任务客户端。

    所有功能模块共享同一个 requests.Session。登录成功后的 cookie、formhash
    和登录态都保存在这个对象上，后续任务按原有顺序逐个调用。
    """

    def __init__(
        self,
        account_config: Dict[str, Any],
        account_index: int = 0,
        controller: Optional[StopController] = None,
        save_cookie_callback: Optional[Callable[['GamemaleAutomation'], bool]] = None,
    ):
        self.config = account_config
        self.account_index = account_index
        self.account_name = account_config.get("username", f"账户{account_index+1}")
        self.session = create_session()
        self.formhash: Optional[str] = None
        self.is_logged_in = False
        self.mission_results: List[Dict[str, str]] = []
        self.mission_summary: Dict[str, int] = {}
        self.online_time_summary: Dict[str, object] = {}
        self._controller = controller
        self._save_cookie_callback = save_cookie_callback
        self._ocr = None

    def _is_stopped(self) -> bool:
        """检查是否已请求停止"""
        return self._controller is not None and self._controller.is_stopped()

    def _sleep(self, seconds: float):
        """可中断的等待"""
        if self._controller:
            self._controller.interruptible_sleep(seconds)
        else:
            time.sleep(seconds)

    def _init_ocr(self) -> bool:
        """延迟初始化 OCR"""
        if self._ocr is None and DDDDOCR_AVAILABLE and ddddocr is not None:
            self._ocr = ddddocr.DdddOcr(show_ad=False)
        return self._ocr is not None

    def _send_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """统一的请求发送方法，带默认超时"""
        kwargs.setdefault('timeout', DEFAULT_TIMEOUT)
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            if e.response is not None:
                log_error(f"请求失败: {url}, 状态码: {e.response.status_code}", self.account_name)
            else:
                log_error(f"请求失败: {url}, 错误: {e}", self.account_name)
            raise

    def extract_cookies_string(self) -> str:
        """从当前 session 提取 cookie 字符串"""
        return '; '.join(
            f"{c.name}={c.value}"
            for c in self.session.cookies
            if c.domain and 'gamemale.com' in c.domain
        )

    def _get_config_bool(self, keys: List[str], default: bool = False) -> bool:
        """按别名读取布尔配置，兼容不同入口脚本的命名习惯。"""
        for key in keys:
            if key in self.config:
                return _coerce_config_bool(self.config.get(key), default)
        return default

    def _get_config_list(self, keys: List[str]) -> List[str]:
        """按别名读取列表配置。"""
        values: List[str] = []
        for key in keys:
            values.extend(_coerce_config_list(self.config.get(key)))
        return values

    def _get_config_int(self, keys: List[str], default: int = 0) -> int:
        """按别名读取整数配置。"""
        for key in keys:
            if key not in self.config:
                continue
            try:
                return int(self.config.get(key))
            except (TypeError, ValueError):
                return default
        return default
