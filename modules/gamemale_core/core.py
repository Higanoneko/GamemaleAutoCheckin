#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility re-export for the split GameMale core modules."""

from .client import GamemaleAutomation
from .config_utils import _coerce_config_bool, _coerce_config_list
from .constants import (
    BASE_URL,
    BLOG_INTERACTION_TARGET,
    BLOG_MAX_PAGES,
    BLOOD_EXCHANGE_THRESHOLD,
    DDDDOCR_AVAILABLE,
    DEFAULT_TIMEOUT,
    MAX_LOGIN_RETRIES,
    POKE_TARGET_COUNT,
    TASK_DOING_URL,
    TASK_LIST_URL,
)
from .http import create_session
from .logging_utils import logger, log_error, log_info, log_section, log_success, log_warning
from .parsers import (
    _clean_captcha_text,
    _extract_ajax_content,
    _extract_seccode_image_url,
    _extract_seccodehash,
    _get_query_param,
    _parse_doing_task_list,
    _parse_new_task_list,
    _resolve_gamemale_url,
)
from .runner import run_all_accounts
from .social import interact_with_blogs
from .stop_controller import StopController, stop_controller

__all__ = [
    "BASE_URL", "DEFAULT_TIMEOUT", "MAX_LOGIN_RETRIES",
    "BLOG_INTERACTION_TARGET", "BLOG_MAX_PAGES",
    "BLOOD_EXCHANGE_THRESHOLD", "POKE_TARGET_COUNT", "TASK_LIST_URL", "TASK_DOING_URL",
    "DDDDOCR_AVAILABLE",
    "StopController", "stop_controller",
    "logger", "log_info", "log_success", "log_error", "log_warning", "log_section",
    "create_session",
    "interact_with_blogs", "GamemaleAutomation", "run_all_accounts",
]
