"""Small coordinate variations for automation flows that request human-like input."""

from __future__ import annotations

import random
from typing import Any

from .async_handler import AsyncActionHandler
from .types import ActionResult


class HumanizedAsyncActionHandler(AsyncActionHandler):
    """Apply bounded jitter to pointer actions without changing their targets."""

    def __init__(self, *args: Any, rng: random.Random | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._rng = rng or random.SystemRandom()

    def _convert_relative_to_absolute(
        self, element: list[int], screen_width: int, screen_height: int
    ) -> tuple[int, int]:
        x, y = super()._convert_relative_to_absolute(
            element, screen_width, screen_height
        )
        radius = max(3, min(12, round(min(screen_width, screen_height) * 0.004)))
        x = max(0, min(screen_width - 1, x + self._rng.randint(-radius, radius)))
        y = max(0, min(screen_height - 1, y + self._rng.randint(-radius, radius)))
        return x, y

    async def _handle_swipe(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        start = action.get("start")
        end = action.get("end")
        if not start or not end:
            return ActionResult(False, False, "Missing swipe coordinates")

        start_x, start_y = self._convert_relative_to_absolute(start, width, height)
        end_x, end_y = self._convert_relative_to_absolute(end, width, height)
        duration_ms = self._rng.randint(280, 520)
        await self.device.swipe(
            start_x,
            start_y,
            end_x,
            end_y,
            duration_ms=duration_ms,
        )
        return ActionResult(True, False)
