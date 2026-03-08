# -*- coding: utf-8 -*-
"""
Gamemale 核心模块 — 共享业务逻辑
"""

from .core import (
    # 常量
    BASE_URL,
    DEFAULT_TIMEOUT,
    MAX_LOGIN_RETRIES,
    BLOG_INTERACTION_TARGET,
    BLOG_MAX_PAGES,
    BLOOD_EXCHANGE_THRESHOLD,
    POKE_TARGET_COUNT,
    DDDDOCR_AVAILABLE,
    # 停止控制器
    StopController,
    stop_controller,
    # 日志
    logger,
    log_info,
    log_success,
    log_error,
    log_warning,
    log_section,
    # HTTP
    create_session,
    # 业务逻辑
    interact_with_blogs,
    GamemaleAutomation,
    run_all_accounts,
)

__all__ = [
    "BASE_URL", "DEFAULT_TIMEOUT", "MAX_LOGIN_RETRIES",
    "BLOG_INTERACTION_TARGET", "BLOG_MAX_PAGES",
    "BLOOD_EXCHANGE_THRESHOLD", "POKE_TARGET_COUNT",
    "DDDDOCR_AVAILABLE",
    "StopController", "stop_controller",
    "logger", "log_info", "log_success", "log_error", "log_warning", "log_section",
    "create_session",
    "interact_with_blogs", "GamemaleAutomation", "run_all_accounts",
]
