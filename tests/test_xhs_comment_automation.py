"""Focused tests for the Xiaohongshu comment automation helpers."""

from __future__ import annotations

import random
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import Headers
from tempfile import SpooledTemporaryFile
from fastapi import UploadFile

from AutoGLM_GUI.actions.humanized_async_handler import HumanizedAsyncActionHandler
import AutoGLM_GUI.api.xhs_comment_automation as xhs_api
from AutoGLM_GUI.api.xhs_comment_automation import (
    _build_task,
    _ensure_device,
    _model_config,
    _parse_device,
    _upload_image,
)


class DummyDevice:
    device_id = "device"


def test_parse_device_accepts_smm_mumu_fields() -> None:
    request = _parse_device(
        """{
          "ip": "192.168.31.44",
          "port": 5555,
          "emulator_provider": "mumu",
          "mumu_index": 61,
          "mumu_control_base_url": "http://192.168.31.44:8000/"
        }"""
    )

    assert request.ip == "192.168.31.44"
    assert request.mumu_index == 61
    assert request.mumu_control_base_url == "http://192.168.31.44:8000"


def test_model_config_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOGLM_XHS_COMMENT_API_KEY", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        _model_config()

    assert exc_info.value.status_code == 503


def test_model_config_uses_modern_completion_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOGLM_XHS_COMMENT_API_KEY", "test-key")

    config = _model_config()

    assert config.max_completion_tokens == 3000
    assert config.include_sampling_parameters is False


def test_mumu_device_registration_does_not_connect_adb(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import AutoGLM_GUI.device_manager as device_manager_module

    class FailIfUsed:
        @staticmethod
        def get_instance():
            raise AssertionError("MuMu automation must not use DeviceManager/ADB")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, timeout, trust_env):
            assert timeout == 10
            assert trust_env is False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url):
            assert url.endswith("/api/v1/emulators/45/current-app")
            return FakeResponse()

    monkeypatch.setattr(device_manager_module, "DeviceManager", FailIfUsed)
    monkeypatch.setattr(xhs_api.httpx, "Client", FakeClient)
    monkeypatch.setenv(
        "AUTOGLM_MUMU_REGISTRY_FILE", str(tmp_path / "mumu-registry.json")
    )
    request = _parse_device(
        '{"ip":"192.168.31.44","port":16805,'
        '"emulator_provider":"mumu","mumu_index":45,'
        '"mumu_control_base_url":"http://192.168.31.44:8000"}'
    )

    assert _ensure_device(request) == "192.168.31.44:16805"


def test_mumu_image_upload_uses_pymumu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import AutoGLM_GUI.api.xhs_comment_automation as module
    import AutoGLM_GUI.mumu_registry as registry_module

    monkeypatch.setattr(
        registry_module,
        "get_mumu_registration",
        lambda _device_id: SimpleNamespace(
            base_url="http://192.168.31.44:8000", index=45
        ),
    )

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"success": True, "path": "Download/AutoGLM/image.jpg"}

    class FakeClient:
        def __init__(self, timeout, trust_env):
            assert timeout == 300
            assert trust_env is False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, files):
            assert url.endswith("/api/v1/emulators/45/files")
            assert files["file"][0] == "image.jpg"
            return FakeResponse()

    monkeypatch.setattr(module.httpx, "Client", FakeClient)
    file_object = SpooledTemporaryFile()
    file_object.write(b"image")
    file_object.seek(0)
    image = UploadFile(
        file=file_object,
        filename="image.jpg",
        headers=Headers({"content-type": "image/jpeg"}),
    )

    result = _upload_image("192.168.31.44:16805", image)

    assert result["success"] is True


def test_task_contains_target_and_image_path() -> None:
    task = _build_task(
        red_id="red-1",
        user_name="小红薯",
        note_title="秋天",
        note_like_number="1.2万",
        comment_text="真好看",
        image_count=2,
    )

    assert '"red_id": "red-1"' in task
    assert '"comment_text": "真好看"' in task
    assert "点击右上角“多选”" in task
    assert "按顺序选择 2 张图片" in task


def test_humanized_coordinate_stays_inside_screen() -> None:
    handler = HumanizedAsyncActionHandler(
        device=DummyDevice(),  # type: ignore[arg-type]
        rng=random.Random(7),
    )

    for point in ([0, 0], [500, 500], [1000, 1000]):
        x, y = handler._convert_relative_to_absolute(point, 1440, 2560)
        assert 0 <= x < 1440
        assert 0 <= y < 2560


def test_comment_endpoint_returns_verified_toast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOGLM_XHS_COMMENT_API_KEY", "test-only-key")
    monkeypatch.setattr(xhs_api, "_ensure_device", lambda _request: "device-1")

    async def fake_prepare_images(device_id, images):
        assert device_id == "device-1"
        assert images == []
        return [], []

    async def fake_run_agent(device_id, task, references, model_config):
        assert device_id == "device-1"
        assert '"red_id": "red-1"' in task
        assert references == []
        assert model_config.api_key == "test-only-key"
        return True, "TOAST:评论成功", 12

    monkeypatch.setattr(xhs_api, "_prepare_images", fake_prepare_images)
    monkeypatch.setattr(xhs_api, "_run_agent", fake_run_agent)
    app = FastAPI()
    app.include_router(xhs_api.router)

    response = TestClient(app).post(
        "/api/automations/xhs/comments",
        data={
            "device": '{"ip":"192.168.31.44","port":5555}',
            "red_id": "red-1",
            "user_name": "小红薯",
            "note_title": "秋天",
            "note_like_number": "1.2万",
            "comment_text": "真好看",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "device_id": "device-1",
        "message": "评论成功",
        "toast": "评论成功",
        "steps": 12,
        "uploaded_images": [],
    }
