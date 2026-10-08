"""Device control routes (tap/swipe/touch/keys/text)."""

import asyncio
import os

from fastapi import APIRouter

from AutoGLM_GUI.devices.adb_device import ADBDevice
from AutoGLM_GUI.schemas import (
    ControlResponse,
    KeyEventRequest,
    SwipeRequest,
    SwipeResponse,
    TapRequest,
    TapResponse,
    TextInputRequest,
    TouchDownRequest,
    TouchDownResponse,
    TouchMoveRequest,
    TouchMoveResponse,
    TouchUpRequest,
    TouchUpResponse,
)

router = APIRouter()

_KEY_CODES = {
    "back": "KEYCODE_BACK",
    "home": "KEYCODE_HOME",
    "recents": "KEYCODE_APP_SWITCH",
    "volume_up": "KEYCODE_VOLUME_UP",
    "volume_down": "KEYCODE_VOLUME_DOWN",
    "power": "KEYCODE_POWER",
    "delete": "KEYCODE_DEL",
}


@router.post("/api/control/tap", response_model=TapResponse)
async def control_tap(request: TapRequest) -> TapResponse:
    """Execute tap at specified device coordinates."""
    try:
        if not request.device_id:
            return TapResponse(success=False, error="device_id is required")

        device = ADBDevice(request.device_id)
        await asyncio.to_thread(
            device.tap,
            x=request.x,
            y=request.y,
            delay=request.delay,
        )

        return TapResponse(success=True)
    except Exception as e:
        return TapResponse(success=False, error=str(e))


@router.post("/api/control/swipe", response_model=SwipeResponse)
async def control_swipe(request: SwipeRequest) -> SwipeResponse:
    """Execute swipe from start to end coordinates."""
    try:
        if not request.device_id:
            return SwipeResponse(success=False, error="device_id is required")

        device = ADBDevice(request.device_id)
        await asyncio.to_thread(
            device.swipe,
            start_x=request.start_x,
            start_y=request.start_y,
            end_x=request.end_x,
            end_y=request.end_y,
            duration_ms=request.duration_ms,
            delay=request.delay,
        )

        return SwipeResponse(success=True)
    except Exception as e:
        return SwipeResponse(success=False, error=str(e))


@router.post("/api/control/keyevent", response_model=ControlResponse)
async def control_keyevent(request: KeyEventRequest) -> ControlResponse:
    """Send a supported Android hardware/navigation key."""
    try:
        from AutoGLM_GUI.platform_utils import run_cmd_silently

        adb_path = os.getenv("AUTOGLM_ADB_PATH", "adb")
        result = await run_cmd_silently(
            [
                adb_path,
                "-s",
                request.device_id,
                "shell",
                "input",
                "keyevent",
                _KEY_CODES[request.key],
            ],
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "ADB keyevent failed")
        return ControlResponse(success=True)
    except Exception as e:
        return ControlResponse(success=False, error=str(e))


@router.post("/api/control/text", response_model=ControlResponse)
async def control_text(request: TextInputRequest) -> ControlResponse:
    """Paste UTF-8 text through scrcpy without replacing the device IME."""
    try:
        from AutoGLM_GUI.socketio_server import paste_text

        await paste_text(request.device_id, request.text)
        return ControlResponse(success=True)
    except Exception as e:
        return ControlResponse(success=False, error=str(e))


@router.post("/api/control/touch/down", response_model=TouchDownResponse)
async def control_touch_down(request: TouchDownRequest) -> TouchDownResponse:
    """Send touch DOWN event at specified device coordinates."""
    try:
        from AutoGLM_GUI.adb_plus import touch_down_async

        await touch_down_async(
            x=request.x,
            y=request.y,
            device_id=request.device_id,
            delay=request.delay,
        )

        return TouchDownResponse(success=True)
    except Exception as e:
        return TouchDownResponse(success=False, error=str(e))


@router.post("/api/control/touch/move", response_model=TouchMoveResponse)
async def control_touch_move(request: TouchMoveRequest) -> TouchMoveResponse:
    """Send touch MOVE event at specified device coordinates."""
    try:
        from AutoGLM_GUI.adb_plus import touch_move_async

        await touch_move_async(
            x=request.x,
            y=request.y,
            device_id=request.device_id,
            delay=request.delay,
        )

        return TouchMoveResponse(success=True)
    except Exception as e:
        return TouchMoveResponse(success=False, error=str(e))


@router.post("/api/control/touch/up", response_model=TouchUpResponse)
async def control_touch_up(request: TouchUpRequest) -> TouchUpResponse:
    """Send touch UP event at specified device coordinates."""
    try:
        from AutoGLM_GUI.adb_plus import touch_up_async

        await touch_up_async(
            x=request.x,
            y=request.y,
            device_id=request.device_id,
            delay=request.delay,
        )

        return TouchUpResponse(success=True)
    except Exception as e:
        return TouchUpResponse(success=False, error=str(e))
