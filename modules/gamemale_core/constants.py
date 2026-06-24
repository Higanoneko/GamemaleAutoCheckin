# -*- coding: utf-8 -*-
"""Shared constants and optional OCR dependency detection."""

BASE_URL = "https://www.gamemale.com"
DEFAULT_TIMEOUT = 30
MAX_LOGIN_RETRIES = 8
BLOG_INTERACTION_TARGET = 10
BLOG_MAX_PAGES = 10
BLOOD_EXCHANGE_THRESHOLD = 34
POKE_TARGET_COUNT = 3
TASK_LIST_URL = f"{BASE_URL}/home.php?mod=task&item=new"
TASK_DOING_URL = f"{BASE_URL}/home.php?mod=task&item=doing"

try:
    import ddddocr as ddddocr
    DDDDOCR_AVAILABLE = True
except ImportError:
    ddddocr = None
    DDDDOCR_AVAILABLE = False
