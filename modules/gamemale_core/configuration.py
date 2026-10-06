"""Configuration IO shared by both entrypoints; validation lives in config_utils."""

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from .config_utils import normalize_config
from .assets import atomic_write_text

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


def load_runtime_config(
    yaml_path: Path,
    json_path: Optional[Path] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """来源优先级：YAML > APP_CONFIG_JSON > ACCOUNTS > COOKIE > JSON 文件。"""
    environment = os.environ if environ is None else environ
    if yaml_path.exists():
        if not YAML_AVAILABLE:
            raise ValueError("读取 YAML 配置需要安装 PyYAML")
        try:
            raw = yaml.safe_load(yaml_path.read_text(encoding='utf-8'))
        except yaml.YAMLError:
            raise ValueError("YAML 配置格式错误，请检查缩进") from None
        source = yaml_path.name
    else:
        raw = None
        source = ''
        for key in ('APP_CONFIG_JSON', 'GAMEMALE_ACCOUNTS', 'GAMEMALE_COOKIE'):
            value = environment.get(key, '').strip()
            if not value:
                continue
            source = key
            if key == 'GAMEMALE_COOKIE':
                # 与既有青龙格式兼容：每行一个账户；单账户多行 Cookie
                # 应使用 APP_CONFIG_JSON 或 GAMEMALE_ACCOUNTS 中的 cookie 字段。
                raw = {'accounts': [{'cookie': line.strip()} for line in value.splitlines() if line.strip()]}
            else:
                try:
                    raw = json.loads(value)
                except ValueError:
                    raise ValueError(f"{key} 必须是有效的 JSON") from None
                if key == 'GAMEMALE_ACCOUNTS':
                    raw = {'accounts': [raw] if isinstance(raw, dict) else raw}
            break
        if not source and json_path is not None and json_path.exists():
            try:
                raw = json.loads(json_path.read_text(encoding='utf-8'))
            except ValueError:
                raise ValueError("JSON 配置文件格式错误") from None
            source = json_path.name
        if not source:
            return {}
    config = normalize_config(raw)
    config['_source'] = source
    return config


def save_cookie_to_file(
    path: Path, index: int, cookie: str, expected_account: Mapping[str, Any],
) -> bool:
    """仅更新实际加载的账户文件，环境变量配置不回写到其它来源。"""
    if not path.exists() or not cookie:
        return False
    try:
        if path.suffix.lower() == '.json':
            raw = json.loads(path.read_text(encoding='utf-8'))
        elif YAML_AVAILABLE:
            try:
                raw = yaml.safe_load(path.read_text(encoding='utf-8'))
            except yaml.YAMLError:
                return False
        else:
            return False
        config = normalize_config(raw)
        accounts = config['accounts']
        if index < 0 or index >= len(accounts):
            return False
        current = accounts[index]
        identity_key = 'username' if expected_account.get('username') else 'cookie'
        if current.get(identity_key) != expected_account.get(identity_key):
            return False
        if 'accounts' in raw:
            raw['accounts'][index]['cookie'] = cookie
        elif 'gamemale' in raw and index == 0:
            raw['gamemale']['cookie'] = cookie
        else:
            return False
        content = json.dumps(raw, ensure_ascii=False, indent=2) + '\n' if path.suffix.lower() == '.json' else yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)
        atomic_write_text(path, content)
        return True
    except (OSError, ValueError):
        return False


def create_cookie_saver(
    config: Mapping[str, Any], yaml_path: Path, json_path: Path,
) -> Optional[Callable[[Any], bool]]:
    """捕获本次来源；不能把来自 Secrets 的 Cookie 写进本地模板。"""
    source = config.get('_source')
    path = yaml_path if source == yaml_path.name else json_path if source == json_path.name else None
    if path is None:
        return None
    accounts = config['accounts']

    def save(client: Any) -> bool:
        index = client.account_index
        if index < 0 or index >= len(accounts):
            return False
        return save_cookie_to_file(path, index, client.extract_cookies_string(), accounts[index])

    return save
