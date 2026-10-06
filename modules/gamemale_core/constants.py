# -*- coding: utf-8 -*-
"""Shared constants and optional OCR dependency detection."""

from importlib.util import find_spec
from typing import Any

BASE_URL = "https://www.gamemale.com"
DEFAULT_TIMEOUT = 30
MAX_LOGIN_RETRIES = 8
BLOG_INTERACTION_TARGET = 10
BLOG_MAX_PAGES = 10
BLOOD_EXCHANGE_THRESHOLD = 34
POKE_TARGET_COUNT = 3
TASK_LIST_URL = f"{BASE_URL}/home.php?mod=task&item=new"
TASK_DOING_URL = f"{BASE_URL}/home.php?mod=task&item=doing"

DDDDOCR_AVAILABLE = find_spec('ddddocr') is not None
# 保留兼容名称；只在需要验证码时加载模型和原生依赖。
ddddocr: Any = None
