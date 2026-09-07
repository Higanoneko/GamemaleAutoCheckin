# -*- coding: utf-8 -*-
"""Public automation client that shares session, cookie, and login state across modules."""

import os
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

import requests

from .cloudflare import (
    CloudflareInterrupted,
    CloudflarePassPool,
    CloudflareSolverError,
    extract_turnstile_sitekey,
    filter_gamemale_cookies,
    is_turnstile_challenge,
    normalize_solver,
    select_pass_cookies,
    solve_turnstile,
    submit_turnstile_token,
)
from .config_utils import (
    _coerce_config_bool,
    _coerce_config_list,
    _merge_cloudflare_configs,
)
from .constants import BASE_URL, DDDDOCR_AVAILABLE, DEFAULT_TIMEOUT, ddddocr
from .credits import CreditsMixin
from .daily_tasks import DailyTasksMixin
from .http import create_session
from .login import LoginMixin
from .logging_utils import log_error, log_info, log_success, log_warning
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
        cf_share: Optional[CloudflarePassPool] = None,
        cloudflare_config: Optional[Dict[str, Any]] = None,
    ) -> None:
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
        # Cloudflare 配置：账户内局部块非空字段优先于顶层全局块
        # （两处同结构 {solver, api_key, max_solves}，均未配置时回落环境变量）
        self._cloudflare_config = _merge_cloudflare_configs(
            account_config, cloudflare_config,
        )
        # Cloudflare 人机验证解算状态
        self._cf_solved_count = 0
        self._cf_max_solves = max(0, self._get_cf_max_solves())
        # 多账户共享的放行 Cookie 池（同批账户间复用，减少打码次数）
        self._cf_pool = cf_share
        self._cf_pool_tried = False
        self._cf_cookie_names_before: Optional[Set[str]] = None

    def _get_cf_max_solves(self) -> int:
        """读取单次运行允许的解算次数上限（局部/顶层 cloudflare.max_solves，默认 2）。

        已按“局部优先于全局”合并进 _cloudflare_config。
        """
        try:
            return int(self._cloudflare_config.get("max_solves"))
        except (TypeError, ValueError):
            return 2

    def _get_cloudflare_solver_config(self) -> Tuple[str, str]:
        """读取 Turnstile 解算服务配置（局部 > 全局 > 环境变量）。

        配置块统一为 {solver, api_key} 形态（可含 max_solves）：
          - 账户内局部 cloudflare 块：非空字段优先；
          - 顶层全局 cloudflare 块（与 accounts 同级，由入口脚本注入）；
          - 环境变量 GAMEMALE_CF_SOLVER / GAMEMALE_CF_API_KEY
            （兼容 CF_SOLVER / CF_API_KEY）作为最终兜底。
        """
        solver = str(
            self._cloudflare_config.get("solver")
            or self._cloudflare_config.get("provider")
            or ""
        ).strip()
        api_key = str(
            self._cloudflare_config.get("api_key")
            or self._cloudflare_config.get("key")
            or ""
        ).strip()

        solver = solver or os.environ.get("GAMEMALE_CF_SOLVER") or os.environ.get("CF_SOLVER")
        api_key = api_key or os.environ.get("GAMEMALE_CF_API_KEY") or os.environ.get("CF_API_KEY")

        solver = str(solver or "").strip()
        api_key = str(api_key or "").strip()
        if solver:
            try:
                solver = normalize_solver(solver)
            except ValueError as e:
                log_warning(str(e), self.account_name)
                solver = ""
        return solver, api_key

    def _is_stopped(self) -> bool:
        """检查是否已请求停止"""
        return self._controller is not None and self._controller.is_stopped()

    def _sleep(self, seconds: float) -> None:
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

    def _send_request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """统一的请求发送方法，带默认超时与 Cloudflare 验证页自动处理。

        当响应是 Cloudflare Turnstile 人机验证页时，按"共享放行 Cookie >
        打码平台解算"的顺序尝试放行会话并重放原请求；解算次数上限
        （_cf_max_solves）保证不会无限重试。
        """
        kwargs.setdefault('timeout', DEFAULT_TIMEOUT)
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
        except requests.RequestException as e:
            if e.response is not None:
                log_error(f"请求失败: {url}, 状态码: {e.response.status_code}", self.account_name)
            else:
                log_error(f"请求失败: {url}, 错误: {e}", self.account_name)
            raise

        if is_turnstile_challenge(response.text):
            if self._resolve_cloudflare_challenge(response):
                # 放行成功，重放原请求；若仍命中验证页会再次尝试（有次数上限）
                return self._send_request(method, url, **kwargs)
        return response

    def _resolve_cloudflare_challenge(self, response: requests.Response) -> bool:
        """处理 Cloudflare 人机验证页，按"共享放行 > 打码平台"顺序尝试放行。

        Returns:
            True 表示验证通过，调用方应重放原请求；False 表示无法放行。
        """
        # 第一优先：同批账户共享的放行 Cookie（免费复用，避免每个账户都打码）
        if self._cf_pool is not None and not self._cf_pool_tried:
            shared = self._cf_pool.items()
            if shared:
                self._cf_pool_tried = True
                injected = self._inject_cookies(shared)
                log_info(
                    f"复用共享的 Cloudflare 放行 Cookie（{injected} 个），重放请求…",
                    self.account_name,
                )
                return True

        if self._cf_solved_count >= self._cf_max_solves:
            log_warning(
                f"检测到 Cloudflare 人机验证，但本次运行解算次数已达上限"
                f"（{self._cf_max_solves} 次），跳过",
                self.account_name,
            )
            return False
        if self._is_stopped():
            log_warning("收到停止信号，跳过 Cloudflare 人机验证", self.account_name)
            return False

        # 记录解算前会话 Cookie 名，成功后 diff 出放行标记并共享给后续账户
        if self._cf_pool is not None and self._cf_cookie_names_before is None:
            self._cf_cookie_names_before = {c.name for c in self.session.cookies}

        # 兜底：第三方打码平台（按次计费）
        return self._resolve_cloudflare_via_captcha_api(response)

    def _inject_cookies(self, cookies: Iterable[Tuple[str, str, str]]) -> int:
        """把 Cookie 注入当前会话（仅 gamemale.com 域），返回成功注入数。

        纯函数 filter_gamemale_cookies 负责域/名称筛选，这里只执行会话注入。
        """
        injected = 0
        for name, value, domain in filter_gamemale_cookies(cookies):
            self.session.cookies.set(name, value, domain=domain)
            injected += 1
        return injected

    def _share_pass_cookies(self) -> None:
        """解算成功后，把会话中新增的非会话类 Cookie 存入共享池（供后续账户复用）。"""
        if self._cf_pool is None:
            return
        before = self._cf_cookie_names_before or set()
        candidates = [
            (c.name, c.value, c.domain)
            for c in self.session.cookies
        ]
        pass_cookies = select_pass_cookies(before, candidates)
        if pass_cookies:
            self._cf_pool.update(pass_cookies)
            log_info(
                f"已收集 {len(pass_cookies)} 个放行 Cookie 供后续账户复用",
                self.account_name,
            )

    def _save_session_cookies_after_pass(self) -> None:
        """放行成功后回写会话 Cookie 到配置，减少下次运行的打码次数。

        仅在已登录状态下回写，避免把未登录会话的 Cookie 覆盖到配置里。
        """
        if not (self.is_logged_in and self._save_cookie_callback):
            return
        try:
            if self._save_cookie_callback(self):
                log_info("已把含放行标记的 Cookie 回写到配置，下次运行可直接放行", self.account_name)
        except Exception as e:
            log_warning(f"回写 Cookie 失败（不影响本次任务）: {e}", self.account_name)

    def _resolve_cloudflare_via_captcha_api(self, response: requests.Response) -> bool:
        """通过第三方打码平台解算 Turnstile 并放行会话（付费兜底方案）。

        解算次数上限（_cf_max_solves）由 _resolve_cloudflare_challenge 统一把关，
        到达上限时不会进入本方法。
        """
        solver, api_key = self._get_cloudflare_solver_config()
        if not solver or not api_key:
            log_error(
                "检测到 Cloudflare Turnstile 人机验证，但未配置任何解算通道。\n"
                "请二选一：\n"
                "  1) 打码平台：在配置文件顶层 cloudflare: {solver, api_key} "
                "（与 accounts 同级，全局生效）或单个账户内同结构的 cloudflare "
                "块（局部优先），或在环境变量 GAMEMALE_CF_SOLVER / "
                "GAMEMALE_CF_API_KEY 中填写密钥"
                "（支持 2captcha / capsolver / yescaptcha，单次约 ¥0.02~0.05）；\n"
                "  2) 在浏览器中打开 gamemale.com 完成人机验证后，重新复制完整的 Cookie。",
                self.account_name,
            )
            return False

        sitekey = extract_turnstile_sitekey(response.text)
        if not sitekey:
            log_error("无法从验证页提取 Turnstile sitekey", self.account_name)
            return False

        log_info(
            f"检测到 Cloudflare 人机验证页，正在通过 {solver} 解算 Turnstile"
            "（通常需要 10~60 秒）…",
            self.account_name,
        )
        try:
            token = solve_turnstile(
                solver, api_key, sitekey,
                response.url or f"{BASE_URL}/forum.php",
                should_stop=self._is_stopped,
            )
        except CloudflareSolverError as e:
            log_error(f"Turnstile 解算失败: {e}", self.account_name)
            return False
        except CloudflareInterrupted:
            log_warning("已停止，中断 Cloudflare 人机验证", self.account_name)
            return False
        except Exception as e:
            log_error(f"Turnstile 解算异常: {e}", self.account_name)
            return False

        log_success("Turnstile 解算成功，正在向论坛提交验证…", self.account_name)
        try:
            passed = submit_turnstile_token(
                self.session, token, response.url or f"{BASE_URL}/forum.php"
            )
        except Exception as e:
            log_error(f"提交 Cloudflare 验证失败: {e}", self.account_name)
            return False

        self._cf_solved_count += 1
        if passed:
            log_success("Cloudflare 验证通过，本会话已放行", self.account_name)
            self._share_pass_cookies()
            self._save_session_cookies_after_pass()
            return True
        log_error("论坛拒绝了验证结果（token 无效或平台异常），无法放行", self.account_name)
        return False

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

    def _get_config_str(self, keys: List[str], default: str = "") -> str:
        """按别名读取字符串配置，跳过空值以兼容旧键名。"""
        for key in keys:
            value = self.config.get(key)
            if value:
                return str(value).strip()
        return default
