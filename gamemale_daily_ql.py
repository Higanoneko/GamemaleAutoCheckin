#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 青龙面板任务配置
# new Env('GameMale 自动签到')
# cron 0 8 * * * gamemale_daily_ql.py
"""
Gamemale 每日任务自动化脚本 - 青龙面板适配版
"""

import json
import logging
import os
import argparse
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.gamemale_core.configuration import load_runtime_config, create_cookie_saver
from modules.gamemale_core.runtime import add_runtime_arguments, apply_runtime_overrides, configuration_diagnostics

from modules.gamemale_core import (
    GamemaleAutomation,
    run_all_accounts,
    stop_controller,
)

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("警告: PyYAML 未安装，请在青龙面板依赖管理中添加 pyyaml")

try:
    from notify import send as ql_send
    QL_NOTIFY_AVAILABLE = True
except ImportError:
    try:
        from sendNotify import send as ql_send
        QL_NOTIFY_AVAILABLE = True
    except ImportError:
        QL_NOTIFY_AVAILABLE = False


# ============== 信号处理 ==============
def signal_handler(signum: int, frame: Any) -> None:
    """处理停止信号 — 仅设标志，不调 sys.exit"""
    stop_controller.request_stop()
    print("\n⚠️ 收到停止信号，正在优雅退出...")


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# ============== 配置 ==============
CONFIG_FILE_NAME = "GameMale_Config.yaml"
QL_CONFIG_PATHS = ["/ql/data/config", "/ql/config", Path(__file__).parent]

CONFIG_TEMPLATE = """# GameMale 自动签到配置文件
# Cloudflare Turnstile 人机验证，支持 全局 + 账户局部 两档：
#   全局：下面顶层的 cloudflare 块（与 accounts 同级），对所有账户生效；
#   局部（可选）：把顶层 cloudflare 块复制到某个账户内、改缩进即可，
#   该账户非空字段优先于全局（只覆盖想改的字段，其余回落到全局）。
# 两处都未配置时，回落到环境变量 GAMEMALE_CF_SOLVER / GAMEMALE_CF_API_KEY。
# solver: 2captcha / capsolver / yescaptcha；留空则该层不使用。
cloudflare:
  solver: ""
  api_key: ""
  max_solves: 2    # 单次运行最多解算次数（控制成本）

accounts:
  - cookie: ""
    username: ""
    password: ""
    notify_enabled: true
    auto_exchange: true
    auto_accept_tasks: true
    auto_complete_tasks: true
    captcha_max_retries: 3
    captcha_precheck: true
    asset_history_enabled: true
    online_time_minutes: 0
    online_refresh_interval_seconds: 900
    task_exclude_ids: []
    task_exclude_names: []
    task_exclude_keywords: []
    # 可选：账户局部 cloudflare（与顶层同结构，局部优先）
    # cloudflare:
    #   solver: ""
    #   api_key: ""
    #   max_solves: 2
"""


def get_config_file_path() -> Path:
    """获取配置文件完整路径"""
    for path in QL_CONFIG_PATHS:
        path = Path(path)
        if path.exists() and path.is_dir():
            return path / CONFIG_FILE_NAME
    return Path(__file__).parent / CONFIG_FILE_NAME


def load_config() -> Dict[str, Any]:
    """账户与全局设置始终从同一配置来源加载。"""
    return load_runtime_config(get_config_file_path(), Path(__file__).parent / "config.json")


def load_accounts() -> List[Dict[str, Any]]:
    """兼容旧调用接口，主流程统一使用 load_config。"""
    return load_config().get("accounts", [])


def parse_args() -> argparse.Namespace:
    """解析本次运行的参数。"""
    parser = argparse.ArgumentParser(description="Gamemale 每日任务自动化脚本")
    add_runtime_arguments(parser)
    return parser.parse_args()


def load_cloudflare_settings() -> Optional[Dict[str, Any]]:
    """兼容旧调用接口，包括环境 JSON 中的顶层设置。"""
    return load_config().get("cloudflare")


def save_cookie_to_config(client: GamemaleAutomation) -> bool:
    """兼容旧接口，新主流程捕获配置来源后使用共享写入器。"""
    config = load_config()
    saver = create_cookie_saver(config, get_config_file_path(), Path(__file__).parent / "config.json")
    return saver(client) if saver else False


def send_notification(title: str, content: str) -> None:
    """发送通知"""
    if QL_NOTIFY_AVAILABLE:
        try:
            ql_send(title, content)
        except Exception as e:
            print(f"通知发送失败: {e}")
    else:
        print(f"\n{'='*50}\n【{title}】\n{content}\n{'='*50}")


# ============== 主程序 ==============
def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args()
    try:
        config = load_config()
        accounts = config.get("accounts", [])
        if args.check_config:
            valid, lines = configuration_diagnostics(config, os.environ)
            print("\n".join(lines))
            if not valid:
                sys.exit(1)
            return
        if not accounts:
            config_path = get_config_file_path()
            if not config_path.exists() and not args.check:
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
                print(f"已创建配置模板: {config_path}")
            raise ValueError("未找到账户配置，请填写配置文件或环境变量")
        accounts = apply_runtime_overrides(accounts, args)
    except (ValueError, OSError) as error:
        print(f"配置错误: {error}")
        sys.exit(1)

    failed = run_all_accounts(
        accounts,
        controller=stop_controller,
        save_cookie_callback=create_cookie_saver(config, get_config_file_path(), Path(__file__).parent / "config.json"),
        send_notification=None if args.check else send_notification,
        cloudflare_config=config.get("cloudflare"),
        asset_state_path=Path(__file__).parent / ".gamemale-state" / "assets.json",
        script_title="Gamemale 每日任务自动化脚本 - 青龙面板版",
    )
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
