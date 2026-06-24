# -*- coding: utf-8 -*-
"""Small configuration coercion helpers."""

import re
from typing import Any, List


def _coerce_config_list(value: Any) -> List[str]:
    """把配置中的列表/字符串值规整为字符串列表。"""
    if value is None or value is False:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = re.split(r'[,\n;，；]+', str(value))
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _coerce_config_bool(value: Any, default: bool = False) -> bool:
    """把配置中的布尔/字符串值规整为 bool。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "y", "on", "启用", "开启"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", "禁用", "关闭"}:
        return False
    return default
