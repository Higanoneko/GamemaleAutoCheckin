"""Immutable site progression data and pure Reference-based estimates."""

from dataclasses import dataclass
from typing import Optional, Tuple


REFERENCE_LEVEL_THRESHOLDS = (0, 3, 10, 35, 70, 120, 200, 300, 450, 650, 900)
BLOOD_PER_POINT = 34


@dataclass(frozen=True)
class UsergroupProgress:
    points_needed: int
    current_group: Optional[str] = None
    target_group: Optional[str] = None


@dataclass(frozen=True)
class UpgradeEstimate:
    current_points: int
    current_level: int
    next_threshold: Optional[int]
    points_needed: int
    blood_needed: int
    current_blood: Optional[int]
    blood_shortfall: Optional[int]
    blood_per_point: int


def estimate_upgrade(
    points: Optional[int], blood: Optional[int],
    thresholds: Tuple[int, ...] = REFERENCE_LEVEL_THRESHOLDS,
    blood_per_point: int = BLOOD_PER_POINT,
) -> Optional[UpgradeEstimate]:
    """缺失/非法积分不可当零；等级与血液换算只表达参考规则下的估算。"""
    if type(points) is not int or points < 0:
        return None
    if (not thresholds or thresholds[0] != 0 or type(blood_per_point) is not int or blood_per_point <= 0
            or any(type(value) is not int for value in thresholds)
            or any(left >= right for left, right in zip(thresholds, thresholds[1:]))):
        raise ValueError('升级门槛必须从零严格递增，血液换算比例必须为正')
    level = max(index for index, threshold in enumerate(thresholds) if points >= threshold)
    next_threshold = thresholds[level + 1] if level + 1 < len(thresholds) else None
    needed = next_threshold - points if next_threshold is not None else 0
    needed_blood = needed * blood_per_point
    current_blood = blood if type(blood) is int and blood >= 0 else None
    shortfall = max(0, needed_blood - current_blood) if current_blood is not None else None
    return UpgradeEstimate(points, level, next_threshold, needed, needed_blood,
                           current_blood, shortfall, blood_per_point)
