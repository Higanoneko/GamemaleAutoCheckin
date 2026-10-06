"""Immutable task outcomes; report text never determines execution success."""

from dataclasses import dataclass
from typing import Literal, Tuple

TaskStatus = Literal['success', 'already_done', 'skipped', 'failed', 'stopped', 'unknown']


@dataclass(frozen=True)
class TaskResult:
    name: str
    status: TaskStatus
    message: str = ''
    required: bool = True

    @property
    def succeeded(self) -> bool:
        return self.status in ('success', 'already_done', 'skipped')


@dataclass(frozen=True)
class AccountRunResult:
    account_name: str
    tasks: Tuple[TaskResult, ...]
    report: str
    stopped: bool = False
    assets_before: Tuple[Tuple[str, int], ...] = ()
    assets_after: Tuple[Tuple[str, int], ...] = ()

    @property
    def succeeded(self) -> bool:
        return bool(self.tasks) and not self.stopped and all(
            result.succeeded for result in self.tasks if result.required
        )
