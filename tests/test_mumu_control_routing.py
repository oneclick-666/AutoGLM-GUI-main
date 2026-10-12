from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.control as control_api
from AutoGLM_GUI.api import app
from AutoGLM_GUI.device_manager import DeviceConnection, DeviceManager, ManagedDevice
from AutoGLM_GUI.devices.mumu_device import (
    AsyncMuMuDevice,
    MuMuDevice,
    MuMuServiceError,
)
from AutoGLM_GUI.mumu_registry import (
    clear_mumu_registrations,
    get_mumu_registration,
    register_mumu_device,
)
from AutoGLM_GUI.types import DeviceConnectionType


def _manager_with_device(monkeypatch, device_id: str = "127.0.0.1:7555"):
    manager = DeviceManager.__new__(DeviceManager)
    manager._devices_lock = threading.RLock()
    managed = ManagedDevice(
        serial="mumu-serial",
        connections=[
            DeviceConnection(
                device_id=device_id,
                connection_type=DeviceConnectionType.WIFI,
                status="device",
            )
        ],
    )
    monkeypatch.setattr(
        manager,
        "get_device_by_device_id",
        lambda value: managed if value == device_id else None,
    )
    return manager


def test_device_manager_routes_registered_mumu_without_adb_keyboard(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AUTOGLM_MUMU_REGISTRY_FILE", str(tmp_path / "mumu.json"))
    clear_mumu_registrations()
    register_mumu_device("127.0.0.1:7555", 4, "http://windows-host:8765")
    manager = _manager_with_device(monkeypatch)
    monkeypatch.setattr(
        manager,
        "_ensure_adb_keyboard_once",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("ADB keyboard must not run")
        ),
    )

    sync_device = manager.get_device_protocol("127.0.0.1:7555")
    async_device = manager.get_async_device_protocol("127.0.0.1:7555")

    assert isinstance(sync_device, MuMuDevice)
    assert isinstance(async_device, AsyncMuMuDevice)
    assert sync_device.registration.index == 4


def test_mumu_registration_api_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOGLM_MUMU_REGISTRY_FILE", str(tmp_path / "mumu.json"))
    clear_mumu_registrations()
    client = TestClient(app)

    response = client.put(
        "/api/devices/mumu",
        json={
            "device_id": "127.0.0.1:7555",
            "index": 2,
            "base_url": "http://windows-host:8765",
        },
    )
    assert response.status_code == 200
    assert (tmp_path / "mumu.json").is_file()
    assert get_mumu_registration("127.0.0.1:7555") is not None
    assert client.get("/api/devices/mumu/127.0.0.1:7555").json()["registered"] is True
    assert client.delete("/api/devices/mumu/127.0.0.1:7555").json()["removed"] is True


def test_registered_mumu_control_api_never_uses_adb(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOGLM_MUMU_REGISTRY_FILE", str(tmp_path / "mumu.json"))
    clear_mumu_registrations()
    register_mumu_device("127.0.0.1:7555", 1, "http://windows-host:8765")
    calls: list[str] = []

    class FakeMuMuDevice:
        async def tap(self, *args, **kwargs):
            calls.append("tap")

        async def swipe(self, *args, **kwargs):
            calls.append("swipe")

        async def key_event(self, *args):
            calls.append("key")

        async def type_text(self, *args):
            calls.append("text")

        async def touch_down(self, *args):
            calls.append("touch_down")

    manager = type(
        "Manager",
        (),
        {"get_async_device_protocol": lambda self, device_id: FakeMuMuDevice()},
    )()
    monkeypatch.setattr(
        control_api.DeviceManager,
        "get_instance",
        staticmethod(lambda: manager),
    )
    monkeypatch.setattr(
        control_api,
        "ADBDevice",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("MuMu control must not instantiate ADBDevice")
        ),
    )

    client = TestClient(app)
    device_id = "127.0.0.1:7555"
    responses = [
        client.post("/api/control/tap", json={"device_id": device_id, "x": 1, "y": 2}),
        client.post(
            "/api/control/swipe",
            json={
                "device_id": device_id,
                "start_x": 1,
                "start_y": 2,
                "end_x": 3,
                "end_y": 4,
            },
        ),
        client.post(
            "/api/control/keyevent", json={"device_id": device_id, "key": "home"}
        ),
        client.post("/api/control/text", json={"device_id": device_id, "text": "中文"}),
        client.post(
            "/api/control/touch/down",
            json={"device_id": device_id, "x": 5, "y": 6},
        ),
    ]

    assert all(response.status_code == 200 for response in responses)
    assert all(response.json()["success"] is True for response in responses)
    assert calls == ["tap", "swipe", "key", "text", "touch_down"]


def test_mumu_device_rejects_unsuccessful_control_response(monkeypatch):
    registration = type(
        "Registration",
        (),
        {"device_id": "device", "base_url": "http://mumu", "index": 61},
    )()
    device = MuMuDevice(registration)  # type: ignore[arg-type]
    monkeypatch.setattr(
        device,
        "_request",
        lambda *args, **kwargs: {"success": False, "error": "input failed"},
    )

    with pytest.raises(MuMuServiceError, match="input failed"):
        device.type_text("1")
