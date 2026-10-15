"""Device refreshes must stay bounded as offline transports accumulate."""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from AutoGLM_GUI.adb.connection import ConnectionType, DeviceInfo
from AutoGLM_GUI.device_manager import DeviceManager


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.setattr(
        "AutoGLM_GUI.device_metadata_manager.DeviceMetadataManager.get_instance",
        lambda: Mock(get_display_name=lambda _: None),
    )
    manager = DeviceManager()
    manager._enable_mdns_discovery = False
    return manager


def test_concurrent_refreshes_share_existing_poll(manager, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def list_devices():
        entered.set()
        assert release.wait(2)
        return []

    listing = Mock(side_effect=list_devices)
    monkeypatch.setattr(manager._adb_conn, "list_devices", listing)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(manager._poll_devices)
        try:
            assert entered.wait(2)
            pool.submit(manager.force_refresh).result(timeout=1)
            assert listing.call_count == 1
        finally:
            release.set()
        first.result(timeout=2)

    # The guard is released after completion (and after failures).
    manager._poll_devices()
    assert listing.call_count == 2


def test_offline_devices_skip_probes_but_reconnect_resolves_serial(
    manager, monkeypatch
):
    devices = [
        DeviceInfo(f"10.0.0.1:{5000 + i}", "offline", ConnectionType.WIFI)
        for i in range(100)
    ]
    monkeypatch.setattr(manager._adb_conn, "list_devices", lambda: devices)
    resolve = Mock(return_value="SERIAL-1")
    monkeypatch.setattr("AutoGLM_GUI.adb_plus.get_device_serial", resolve)
    manager._poll_devices()
    resolve.assert_not_called()

    devices[0].status = "device"
    manager._poll_devices()
    assert manager._device_id_to_serial[devices[0].device_id] == "SERIAL-1"
    manager._poll_devices()
    assert resolve.call_count == 1

    devices[0].status = "offline"
    manager._poll_devices()
    assert manager._device_id_to_serial[devices[0].device_id] == "SERIAL-1"
    assert resolve.call_count == 1


def test_poll_failure_does_not_keep_guard_locked(manager, monkeypatch):
    poll = Mock(side_effect=[RuntimeError("offline"), None])
    monkeypatch.setattr(manager, "_poll_devices_once", poll)
    with pytest.raises(RuntimeError):
        manager._poll_devices()
    manager._poll_devices()
    assert poll.call_count == 2
