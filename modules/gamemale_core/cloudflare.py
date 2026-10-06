# -*- coding: utf-8 -*-
"""Cloudflare Turnstile challenge handling for GameMale.

GameMale 论坛在 Cloudflare 边缘后部署了源站人机验证插件
（Discuz 插件 dev8133_cloudflare）：无放行标记的会话会被返回
"请稍候 / 检查站点连接是否安全" 的验证页，页面内嵌 Cloudflare
Turnstile widget。只有拿到真实的 Turnstile token 并 POST 回
plugin.php?id=dev8133_cloudflare 之后，会话才会被放行。

本模块负责：
  1. 识别验证页；
  2. 提取 Turnstile sitekey；
  3. 通过第三方打码平台（2captcha / capsolver / yescaptcha）
     解算 Turnstile 并取回 token；
  4. 把 token 提交给论坛验证接口，换取放行。
"""

import re
import time
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

import requests

from .constants import BASE_URL, DEFAULT_TIMEOUT

# dev8133_cloudflare 插件验证接口路径
VERIFY_ENDPOINT = "plugin.php?id=dev8133_cloudflare"

# 支持的 Turnstile 解算服务
SUPPORTED_SOLVERS = ("2captcha", "capsolver", "yescaptcha")

# 默认解算超时（秒）
DEFAULT_SOLVE_TIMEOUT = 240
# 轮询间隔（秒）
DEFAULT_POLL_INTERVAL = 5

# 打码平台 API 地址
CAPTCHA2_BASE = "https://2captcha.com"
CAPSOLVER_BASE = "https://api.capsolver.com"
YESCAPTCHA_BASE = "https://api.yescaptcha.com"


class CloudflareChallengeError(Exception):
    """Cloudflare 人机验证相关问题（无法放行等）。"""


class CloudflareSolverError(CloudflareChallengeError):
    """第三方解算服务错误（余额不足、超时、服务端拒绝等）。"""


class CloudflareInterrupted(CloudflareChallengeError):
    """解算过程中收到停止信号。"""


# 常规会话 Cookie（Discuz 会话 / 自定义会话），与"人机验证放行"无关，
# 且带账户/会话属性，跨账户共享无益甚至有害，收集放行 Cookie 时排除。
_CF_EXCLUDE_COOKIE_PREFIXES = ("TVj0_2132_",)
_CF_EXCLUDE_COOKIE_NAMES = {"server_name_session"}


def _is_regular_session_cookie(name: str) -> bool:
    """判断 Cookie 是否为常规会话 Cookie（非放行标记候选）。"""
    if name in _CF_EXCLUDE_COOKIE_NAMES:
        return True
    return any(name.startswith(prefix) for prefix in _CF_EXCLUDE_COOKIE_PREFIXES)


def select_pass_cookies(
    before_names: Set[str],
    cookies: Iterable[Tuple[str, str, str]],
) -> List[Tuple[str, str, str]]:
    """从 (name, value, domain) 候选中筛出可共享的放行 Cookie。

    放行 Cookie 的特征：解算前后新增、非常规会话类、且属于
    gamemale.com 域。纯函数，供解算成功后与共享池之间做 diff。
    """
    return [
        (name, value, domain)
        for name, value, domain in cookies
        if name not in before_names
        and not _is_regular_session_cookie(name)
        and 'gamemale.com' in domain
    ]


def filter_gamemale_cookies(
    cookies: Iterable[Tuple[str, str, str]],
) -> List[Tuple[str, str, str]]:
    """只保留 gamemale.com 域且 name 非空的 Cookie（纯函数）。"""
    return [
        (name, value, domain)
        for name, value, domain in cookies
        if name and 'gamemale.com' in domain
    ]


class CloudflarePassPool:
    """多账户间共享的 Cloudflare 放行 Cookie 池。

    GameMale 的人机验证与具体论坛账户无关：同一出口下，一个会话验证放行后
    获得的放行 Cookie 理论上可被同批其它账户复用，避免每个账户都打码一次。

    仅收集"解算后新增、且非常规会话类"的 Cookie（通过前后 diff 识别，
    放行标记通常就是这类新 Cookie），不会混入登录态 Cookie，跨账户注入安全。
    """

    def __init__(self) -> None:
        # key: (domain, name) -> (name, value, domain)
        self._entries: Dict[Tuple[str, str], Tuple[str, str, str]] = {}

    def update(self, cookies: Iterable[Tuple[str, str, str]]) -> None:
        """把候选放行 Cookie 加入池中。cookies 为 (name, value, domain) 序列。"""
        for name, value, domain in cookies or []:
            name = str(name or "").strip()
            if not name or not domain:
                continue
            self._entries[(str(domain), name)] = (name, str(value or ""), str(domain))

    def items(self) -> List[Tuple[str, str, str]]:
        """返回当前池中的 (name, value, domain) 列表（复制，避免外部修改）。"""
        return list(self._entries.values())

    def __bool__(self) -> bool:
        return bool(self._entries)


def is_turnstile_challenge(text: str) -> bool:
    """判断响应文本是否为 GameMale 的 Cloudflare 人机验证页。

    验证页特征：引用 dev8133_cloudflare 插件资源并内嵌 Turnstile。
    """
    if not text:
        return False
    lowered = text.casefold()
    if "dev8133_cloudflare" in lowered:
        return True
    # 兜底：Turnstile 渲染卡片 + 挑战平台脚本
    return "verify-card" in lowered and "turnstile" in lowered


def extract_turnstile_sitekey(text: str) -> Optional[str]:
    """从验证页 HTML 中提取 Turnstile sitekey。"""
    if not text:
        return None
    match = re.search(r'sitekey["\']?\s*[:=]\s*["\']([0-9A-Za-z_-]{10,})["\']', text)
    return match.group(1) if match else None


def normalize_solver(solver: str) -> str:
    """规范化解算服务名，返回支持的名称；不支持时抛出 ValueError。"""
    name = str(solver or "").strip().casefold().replace("-", "").replace("_", "").replace(" ", "")
    aliases = {
        "2captcha": "2captcha",
        "twocaptcha": "2captcha",
        "capsolver": "capsolver",
        "capmonster": "capsolver",  # capmonster 已被 capsolver 收购合并
        "yescaptcha": "yescaptcha",
    }
    normalized = aliases.get(name)
    if normalized is None:
        raise ValueError(f"不支持的验证码解算服务: {solver}（可选: {' / '.join(SUPPORTED_SOLVERS)}）")
    return normalized


def solve_turnstile(
    solver: str,
    api_key: str,
    sitekey: str,
    page_url: str,
    timeout: int = DEFAULT_SOLVE_TIMEOUT,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    should_stop: Optional[Callable[[], bool]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """通过第三方平台解算 Turnstile，返回 token。

    Args:
        solver: 服务名（2captcha / capsolver / yescaptcha）
        api_key: 平台 API key
        sitekey: 验证页上的 Turnstile sitekey
        page_url: 验证页所在 URL
        timeout: 总超时秒数
        poll_interval: 轮询间隔秒数
        should_stop: 可选停止检查回调（返回 True 表示中断）

    Returns:
        解算出的 Turnstile token

    Raises:
        CloudflareSolverError: 平台错误、余额不足、超时等
        CloudflareInterrupted: 收到停止信号
    """
    solver = normalize_solver(solver)
    api_key = str(api_key or "").strip()
    if not api_key:
        raise CloudflareSolverError("未配置 API Key")

    def _check_stopped() -> None:
        if should_stop is not None and should_stop():
            raise CloudflareInterrupted("收到停止信号，中断人机验证解算")

    _check_stopped()

    if solver == "2captcha":
        task_id = _create_captcha2_task(api_key, sitekey, page_url)
        token = _poll_captcha2_task(api_key, task_id, timeout, poll_interval, _check_stopped, sleep)
    else:
        base = CAPSOLVER_BASE if solver == "capsolver" else YESCAPTCHA_BASE
        task_id = _create_task(base, api_key, sitekey, page_url)
        token = _poll_task(base, api_key, task_id, timeout, poll_interval, _check_stopped, sleep)

    if not token:
        raise CloudflareSolverError(f"解算服务({solver})未返回有效 token")
    return token


# ---------- 2captcha ----------

def _create_captcha2_task(api_key: str, sitekey: str, page_url: str) -> str:
    payload = {
        "key": api_key,
        "method": "turnstile",
        "sitekey": sitekey,
        "pageurl": page_url,
        "json": 1,
    }
    try:
        response = requests.post(f"{CAPTCHA2_BASE}/in.php", data=payload, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as e:
        raise CloudflareSolverError(f"无法连接 2captcha: {e}") from e

    if response.status_code >= 400:
        raise CloudflareSolverError(_error_from_http(CAPTCHA2_BASE, response))
    try:
        data = response.json()
    except ValueError as e:
        raise CloudflareSolverError(f"2captcha 响应解析失败: {response.text[:200]}") from e

    if data.get("status") != 1:
        raise CloudflareSolverError(f"2captcha 创建任务失败: {data.get('error_text') or data.get('request') or data}")
    return str(data.get("request"))


def _poll_captcha2_task(
    api_key: str,
    task_id: str,
    timeout: int,
    poll_interval: int,
    check_stopped: Callable[[], None],
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    deadline = time.time() + timeout
    while True:
        check_stopped()
        try:
            response = requests.get(
                f"{CAPTCHA2_BASE}/res.php",
                params={"key": api_key, "action": "get", "id": task_id, "json": 1},
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as e:
            raise CloudflareSolverError(f"2captcha 轮询出错: {e}") from e

        if response.status_code >= 400:
            raise CloudflareSolverError(_error_from_http(CAPTCHA2_BASE, response))
        try:
            data = response.json()
        except ValueError:
            raise CloudflareSolverError(f"2captcha 轮询响应解析失败: {response.text[:200]}") from None

        status = data.get("status")
        if status == 1:
            return str(data.get("request", ""))
        request_state = str(data.get("request", ""))
        if status != 0 and "CAPCHA_NOT_READY" not in request_state:
            raise CloudflareSolverError(f"2captcha 解算失败: {request_state or data}")

        if time.time() >= deadline:
            raise CloudflareSolverError(f"2captcha 解算超时（{timeout} 秒）")
        sleep(poll_interval)


# ---------- capsolver / yescaptcha（同构 API） ----------

def _create_task(base: str, api_key: str, sitekey: str, page_url: str) -> str:
    payload = {
        "clientKey": api_key,
        "task": {
            "type": "TurnstileTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": sitekey,
        },
    }
    try:
        response = requests.post(f"{base}/createTask", json=payload, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as e:
        raise CloudflareSolverError(f"无法连接解算服务 {base}: {e}") from e

    if response.status_code >= 400:
        raise CloudflareSolverError(_error_from_http(base, response))
    try:
        data = response.json()
    except ValueError as e:
        raise CloudflareSolverError(f"解算服务 {base} 响应解析失败: {response.text[:200]}") from e

    if data.get("errorId") not in (0, None):
        raise CloudflareSolverError(
            f"解算服务创建任务失败: {data.get('errorCode') or data.get('errorDescription') or data}"
        )
    task_id = data.get("taskId")
    if not task_id:
        raise CloudflareSolverError(f"解算服务未返回 taskId: {data}")
    return str(task_id)


def _poll_task(
    base: str,
    api_key: str,
    task_id: str,
    timeout: int,
    poll_interval: int,
    check_stopped: Callable[[], None],
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    deadline = time.time() + timeout
    while True:
        check_stopped()
        try:
            response = requests.post(
                f"{base}/getTaskResult",
                json={"clientKey": api_key, "taskId": task_id},
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as e:
            raise CloudflareSolverError(f"解算服务 {base} 轮询出错: {e}") from e

        if response.status_code >= 400:
            raise CloudflareSolverError(_error_from_http(base, response))
        try:
            data = response.json()
        except ValueError:
            raise CloudflareSolverError(f"解算服务 {base} 轮询响应解析失败: {response.text[:200]}") from None

        if data.get("errorId") not in (0, None):
            raise CloudflareSolverError(
                f"解算服务轮询失败: {data.get('errorCode') or data.get('errorDescription') or data}"
            )
        if data.get("status") == "ready":
            solution = data.get("solution") or {}
            token = solution.get("token") or solution.get("gRecaptchaResponse") or ""
            if token:
                return str(token)
            raise CloudflareSolverError(f"解算完成但未返回 token: {data}")

        if time.time() >= deadline:
            raise CloudflareSolverError(f"解算服务 {base} 超时（{timeout} 秒）")
        sleep(poll_interval)


def _error_from_http(base: str, response: requests.Response) -> str:
    """从打码平台的 HTTP 错误响应中提取可读错误信息。"""
    try:
        data = response.json()
        detail = data.get("errorCode") or data.get("errorDescription") or data.get("error_text")
    except ValueError:
        detail = None
    if detail:
        return f"解算服务 {base} HTTP {response.status_code}: {detail}"
    return f"解算服务 {base} HTTP {response.status_code}: {response.text[:200]}"


# ---------- 论坛侧提交 ----------

def submit_turnstile_token(
    session: requests.Session,
    token: str,
    challenge_url: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> bool:
    """把解算出的 token 提交给论坛验证接口。

    成功（code == 200）时插件会放行当前会话（通常是种下放行标记
    Cookie），此后同一 Session 的请求无需再次验证。

    注意：这里刻意直接使用传入的 session 而不是 client._send_request——
    本请求本身就是"放行 Cloudflare 验证页"的提交动作，若再走验证页
    自动重放逻辑会形成递归；该模块被允许作为独立的纯请求边界。

    Args:
        session: 论坛请求会话
        token: Turnstile token
        challenge_url: 触发验证页的 URL（作为 Referer）
        timeout: 请求超时

    Returns:
        True 表示验证通过、会话已被放行
    """
    verify_url = f"{BASE_URL}/{VERIFY_ENDPOINT}"
    headers = {"Referer": challenge_url}
    response = session.post(verify_url, data={"token": token}, headers=headers, timeout=timeout)
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError:
        raise CloudflareChallengeError(
            f"验证接口返回异常（非 JSON）: {response.text[:200]}"
        ) from None
    return data.get("code") == 200
