"""Shared CLI and pure runtime overrides."""

import argparse
import hashlib
from copy import deepcopy
from typing import Any, Dict, List, Mapping, Tuple

from .parsers import parse_cookie_header
from .config_utils import _merge_cloudflare_configs


def add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    """两个入口使用同一组运行参数。"""
    parser.add_argument('--online-time-minutes', type=int, default=None, help='挂机总时长（分钟）')
    parser.add_argument('--online-time-seconds', type=int, default=None, help='挂机总时长（秒，优先于分钟）')
    parser.add_argument('--online-refresh-interval-seconds', type=int, default=None, help='挂机刷新间隔（秒）')
    parser.add_argument('--enable-online', action='store_true', help='本次运行启用挂机刷新')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--only-online', action='store_true', help='仅挂机刷新')
    modes.add_argument('--check', action='store_true', help='在线自检，不执行日常动作、不保存配置/资产、不通知')
    modes.add_argument('--status-only', action='store_true', help='只查询登录状态与资产，并生成报告')
    modes.add_argument('--check-config', action='store_true', help='离线检查配置，不发起网络请求')


def apply_runtime_overrides(
    accounts: List[Dict[str, Any]], args: argparse.Namespace,
) -> List[Dict[str, Any]]:
    """返回新配置，仅显式 CLI 参数启用挂机。"""
    updated = deepcopy(accounts)
    online_seconds = args.online_time_seconds
    if online_seconds is None and args.online_time_minutes is not None:
        online_seconds = args.online_time_minutes * 60
    query_mode = 'check' if getattr(args, 'check', False) else 'status' if getattr(args, 'status_only', False) else 'full'
    if query_mode != 'full' and (args.enable_online or args.only_online):
        raise ValueError("自检/资产查询模式不能同时启用挂机")
    for account in updated:
        account['run_mode'] = query_mode
        account['online_runtime_enabled'] = bool(args.enable_online or args.only_online)
        if query_mode != 'full':
            account['only_online'] = False
            account['only_online_time'] = False
        elif args.only_online:
            account['only_online'] = True
        if account['online_runtime_enabled'] and online_seconds is not None:
            account['online_time_seconds'] = max(0, online_seconds)
            account.pop('online_time_minutes', None)
        if account['online_runtime_enabled'] and args.online_refresh_interval_seconds is not None:
            account['online_refresh_interval_seconds'] = max(1, args.online_refresh_interval_seconds)
    return updated


def configuration_diagnostics(
    config: Mapping[str, Any], environ: Mapping[str, str],
) -> Tuple[bool, Tuple[str, ...]]:
    """离线诊断只显示来源、项数与指纹；不输出 Cookie/密码/API Key。"""
    accounts = config.get('accounts', [])
    lines = [f"配置来源: {config.get('_source', '未配置')}", f"账户数量: {len(accounts)}"]
    valid = bool(accounts)
    for index, account in enumerate(accounts):
        cookie = account.get('cookie', '')
        password_ready = bool(account.get('username') and account.get('password'))
        try:
            cookies = parse_cookie_header(cookie)
            fingerprint = hashlib.sha256(cookie.strip().encode('utf-8')).hexdigest()[:12] if cookies else '空'
            lines.append(f'账户 {index + 1}: Cookie {len(cookies)} 项 / 指纹 {fingerprint}；密码登录: {"已配置" if password_ready else "未配置"}')
            valid = valid and bool(cookies or password_ready)
        except ValueError:
            lines.append(f'账户 {index + 1}: Cookie 格式错误')
            valid = False
        cf = _merge_cloudflare_configs(account, config.get('cloudflare'))
        solver = cf.get('solver') or cf.get('provider') or environ.get('GAMEMALE_CF_SOLVER') or environ.get('CF_SOLVER')
        key = cf.get('api_key') or cf.get('key') or environ.get('GAMEMALE_CF_API_KEY') or environ.get('CF_API_KEY')
        lines.append(f'账户 {index + 1}: Cloudflare 解算兜底 {"已配置" if solver and key else "未配置（遇挑战时会明确报错）"}')
    return valid, tuple(lines)
