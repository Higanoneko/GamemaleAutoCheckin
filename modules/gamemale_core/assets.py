"""Pure asset calculations and isolated, account-owned history storage."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .parsers import _parse_credit_value_int


def parse_asset_snapshot(credits: Mapping[str, str]) -> Dict[str, int]:
    """无法解析的项目保持缺失，真实的零值仍然有效。"""
    snapshot: Dict[str, int] = {}
    for name, text in credits.items():
        try:
            snapshot[name] = _parse_credit_value_int(text)
        except (ValueError, IndexError):
            continue
    return snapshot


def asset_deltas(before: Mapping[str, int], after: Mapping[str, int]) -> Dict[str, int]:
    """仅比较两次都成功解析的字段，不将缺失余额解释为零。"""
    return {name: value - before[name] for name, value in after.items() if name in before}


def atomic_write_text(path: Path, content: str) -> None:
    """在目标目录写临时文件再替换，保留原文件直到完整写入成功。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=str(path.parent), delete=False) as stream:
            temporary = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def load_asset_records(path: Path) -> Dict[str, Any]:
    """损坏或不存在的历史按首次记录处理，不能用于计算虚假增长。"""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('accounts'), dict):
        return {}
    return data['accounts']


def previous_snapshot(records: Mapping[str, Any], uid: int) -> Dict[str, int]:
    """只读取经登录验证的 UID 所属记录，严格过滤非法值。"""
    record = records.get(str(uid), {})
    credits = record.get('credits', {}) if isinstance(record, dict) else {}
    if not isinstance(credits, dict):
        return {}
    return {key: value for key, value in credits.items() if isinstance(key, str) and type(value) is int and value >= 0}


def merge_asset_record(
    records: Mapping[str, Any], uid: int, snapshot: Mapping[str, int], sampled_at: str,
) -> Dict[str, Any]:
    """字段各自保存采集时间；缺失项保留，但不会冒充本次采集值。"""
    updated = dict(records)
    if uid <= 0 or not snapshot:
        return updated
    old = records.get(str(uid), {})
    old_times = old.get('sampled_at', {}) if isinstance(old, dict) else {}
    times = dict(old_times) if isinstance(old_times, dict) else {}
    credits = previous_snapshot(records, uid)
    credits.update(snapshot)
    times.update({name: sampled_at for name in snapshot})
    updated[str(uid)] = {'credits': credits, 'sampled_at': times}
    return updated


def save_asset_records(path: Path, records: Mapping[str, Any]) -> None:
    atomic_write_text(path, json.dumps({'version': 1, 'accounts': records}, ensure_ascii=False, indent=2) + '\n')
