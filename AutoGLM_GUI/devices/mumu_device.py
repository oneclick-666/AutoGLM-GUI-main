"""MuMu device controls backed exclusively by the pymumu HTTP service."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from AutoGLM_GUI.adb.apps import APP_PACKAGES
from AutoGLM_GUI.device_protocol import AsyncDeviceProtocol, DeviceProtocol, Screenshot
from AutoGLM_GUI.mumu_registry import MuMuRegistration
from AutoGLM_GUI.trace import trace_sleep, trace_span


class MuMuServiceError(RuntimeError):
    pass


class MuMuDevice(DeviceProtocol):
    """Synchronous device implementation using MumuManager through pymumu."""

    def __init__(self, registration: MuMuRegistration, timeout: float = 30):
        self.registration = registration
        self._device_id = registration.device_id
        self._timeout = timeout

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def _instance_url(self) -> str:
        return (
            f"{self.registration.base_url}/api/v1/emulators/{self.registration.index}"
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        # MuMu is a LAN service. System HTTP proxy settings can route private
        # addresses through a proxy and turn a millisecond request into a timeout.
        with httpx.Client(timeout=self._timeout, trust_env=False) as client:
            response = client.request(method, f"{self._instance_url}{path}", **kwargs)
        if response.is_error:
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError):
                detail = None
            raise MuMuServiceError(
                detail or f"pymumu request failed ({response.status_code})"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise MuMuServiceError("pymumu returned an invalid response")
        return payload

    def _control(self, action: str, **payload: Any) -> dict[str, Any]:
        with trace_span(
            f"device.{action}",
            attrs={
                "device_id": self.device_id,
                "device_impl": "pymumu",
                "mumu_index": self.registration.index,
            },
        ):
            result = self._request(
                "POST", "/control", json={"action": action, **payload}
            )
            if result.get("success") is not True:
                raise MuMuServiceError(
                    str(
                        result.get("detail")
                        or result.get("error")
                        or "pymumu control failed"
                    )
                )
            return result

    def get_screenshot(self, timeout: int = 10) -> Screenshot:
        payload = self._request("GET", "/screenshot", timeout=timeout)
        return Screenshot(
            base64_data=str(payload["image"]),
            width=int(payload["width"]),
            height=int(payload["height"]),
            is_sensitive=bool(payload.get("is_sensitive", False)),
        )

    def tap(self, x: int, y: int, delay: float | None = None) -> None:
        self._control("tap", x=x, y=y)
        if delay:
            trace_sleep(delay, name="sleep.device_tap_delay")

    def double_tap(self, x: int, y: int, delay: float | None = None) -> None:
        self._control("double_tap", x=x, y=y)
        if delay:
            trace_sleep(delay, name="sleep.device_double_tap_delay")

    def long_press(
        self, x: int, y: int, duration_ms: int = 3000, delay: float | None = None
    ) -> None:
        self._control("long_press", x=x, y=y, duration_ms=duration_ms)
        if delay:
            trace_sleep(delay, name="sleep.device_long_press_delay")

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        delay: float | None = None,
    ) -> None:
        self._control(
            "swipe",
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            duration_ms=duration_ms or 300,
        )
        if delay:
            trace_sleep(delay, name="sleep.device_swipe_delay")

    def type_text(self, text: str) -> None:
        self._control("text", text=text)

    def clear_text(self) -> None:
        self._control("clear_text")

    def key_event(self, key: str) -> None:
        self._control("key", key=key)

    def touch_down(self, x: int, y: int, delay: float | None = None) -> None:
        self._control("touch_down", x=x, y=y)
        if delay:
            trace_sleep(delay, name="sleep.device_touch_delay")

    def touch_move(self, x: int, y: int, delay: float | None = None) -> None:
        self._control("touch_move", x=x, y=y)
        if delay:
            trace_sleep(delay, name="sleep.device_touch_delay")

    def touch_up(self, x: int, y: int, delay: float | None = None) -> None:
        self._control("touch_up", x=x, y=y)
        if delay:
            trace_sleep(delay, name="sleep.device_touch_delay")

    def back(self, delay: float | None = None) -> None:
        self.key_event("back")
        if delay:
            trace_sleep(delay, name="sleep.device_back_delay")

    def home(self, delay: float | None = None) -> None:
        self.key_event("home")
        if delay:
            trace_sleep(delay, name="sleep.device_home_delay")

    def launch_app(self, app_name: str, delay: float | None = None) -> bool:
        package = APP_PACKAGES.get(app_name)
        if not package:
            return False
        self._control("launch_app", package=package)
        if delay:
            trace_sleep(delay, name="sleep.device_launch_delay")
        return True

    def get_current_app(self) -> str:
        payload = self._request("GET", "/current-app")
        package = str(payload.get("package") or "")
        return next(
            (name for name, candidate in APP_PACKAGES.items() if candidate == package),
            "System Home",
        )

    def detect_and_set_adb_keyboard(self) -> str:
        # pymumu sends Unicode directly; changing the Android IME is unnecessary.
        return ""

    def restore_keyboard(self, ime: str) -> None:
        return None


class AsyncMuMuDevice(AsyncDeviceProtocol):
    """Async facade around :class:`MuMuDevice`."""

    def __init__(self, registration: MuMuRegistration):
        self._sync = MuMuDevice(registration)

    @property
    def device_id(self) -> str:
        return self._sync.device_id

    async def get_screenshot(self, timeout: int = 10) -> Screenshot:
        return await asyncio.to_thread(self._sync.get_screenshot, timeout)

    async def tap(self, x: int, y: int, delay: float | None = None) -> None:
        await asyncio.to_thread(self._sync.tap, x, y, delay)

    async def double_tap(self, x: int, y: int, delay: float | None = None) -> None:
        await asyncio.to_thread(self._sync.double_tap, x, y, delay)

    async def long_press(
        self, x: int, y: int, duration_ms: int = 3000, delay: float | None = None
    ) -> None:
        await asyncio.to_thread(self._sync.long_press, x, y, duration_ms, delay)

    async def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        delay: float | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._sync.swipe, start_x, start_y, end_x, end_y, duration_ms, delay
        )

    async def type_text(self, text: str) -> None:
        await asyncio.to_thread(self._sync.type_text, text)

    async def clear_text(self) -> None:
        await asyncio.to_thread(self._sync.clear_text)

    async def key_event(self, key: str) -> None:
        await asyncio.to_thread(self._sync.key_event, key)

    async def touch_down(self, x: int, y: int, delay: float | None = None) -> None:
        await asyncio.to_thread(self._sync.touch_down, x, y, delay)

    async def touch_move(self, x: int, y: int, delay: float | None = None) -> None:
        await asyncio.to_thread(self._sync.touch_move, x, y, delay)

    async def touch_up(self, x: int, y: int, delay: float | None = None) -> None:
        await asyncio.to_thread(self._sync.touch_up, x, y, delay)

    async def back(self, delay: float | None = None) -> None:
        await asyncio.to_thread(self._sync.back, delay)

    async def home(self, delay: float | None = None) -> None:
        await asyncio.to_thread(self._sync.home, delay)

    async def launch_app(self, app_name: str, delay: float | None = None) -> bool:
        return await asyncio.to_thread(self._sync.launch_app, app_name, delay)

    async def get_current_app(self) -> str:
        return await asyncio.to_thread(self._sync.get_current_app)

    async def detect_and_set_adb_keyboard(self) -> str:
        return ""

    async def restore_keyboard(self, ime: str) -> None:
        return None
