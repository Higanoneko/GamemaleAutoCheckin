# -*- coding: utf-8 -*-
"""Small configuration coercion helpers."""

import re
from copy import deepcopy
from typing import Any, Dict, List, Optional


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


def _merge_cloudflare_configs(
    account_config: Dict[str, Any],
    global_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """合并 Cloudflare 配置：账户内局部块的非空字段优先于顶层全局块。

    全局（顶层 cloudflare，与 accounts 同级）与局部（账户内 cloudflare）使用
    同一结构 {solver, api_key, max_solves}，方便从顶层复制改缩进即可作为局部。

    合并规则（逐字段）：
      - 局部有非空值 → 用局部（用户可只为单个账户覆盖某个字段）；
      - 局部缺省/为空 → 回落全局；
      - 两处皆无 → 返回 {}，由调用方再回落环境变量/默认值。
    """
    merged = dict(global_config or {})
    local = account_config.get("cloudflare")
    if isinstance(local, dict):
        for key, value in local.items():
            if value is not None and str(value).strip() != "":
                merged[key] = value
    return merged


def normalize_config(raw: Any) -> Dict[str, Any]:
    """验证配置结构并迁移旧单账户结构，返回独立副本。"""
    if not isinstance(raw, dict):
        raise ValueError("配置根节点必须是对象，不能是空文件或列表")
    config = deepcopy(raw)
    if 'accounts' not in config and 'gamemale' in config:
        config['accounts'] = [config['gamemale']]
    accounts = config.get('accounts', [])
    if not isinstance(accounts, list) or any(not isinstance(a, dict) for a in accounts):
        raise ValueError("accounts 必须是账户对象列表")
    for index, account in enumerate(accounts):
        for key in ('cookie', 'username', 'password'):
            if key in account and not isinstance(account[key], str):
                raise ValueError(f"账户 {index + 1} 的 {key} 必须是字符串")
        if 'cloudflare' in account and not isinstance(account['cloudflare'], dict):
            raise ValueError(f"账户 {index + 1} 的 cloudflare 必须是对象")
    for key in ('cloudflare', 'notification'):
        if key in config and not isinstance(config[key], dict):
            raise ValueError(f"{key} 必须是对象")
    config['accounts'] = accounts
    return config
