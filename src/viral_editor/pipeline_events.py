"""Pipeline stage events for CLI, API, and SSE consumers."""

from __future__ import annotations

import time
from typing import Literal

from viral_editor.models import DomainModel

StageAction = Literal["start", "complete", "skip", "info", "error"]


class PipelineEvent(DomainModel):
    """Serializable stage boundary emitted during a pipeline run."""

    stage: str
    action: StageAction
    message: str | None = None
    timestamp: float = 0.0

    @classmethod
    def now(
        cls,
        stage: str,
        action: StageAction,
        *,
        message: str | None = None,
    ) -> PipelineEvent:
        return cls(
            stage=stage,
            action=action,
            message=message,
            timestamp=time.time(),
        )
