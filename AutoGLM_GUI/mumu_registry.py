"""Runtime mapping from an ADB-visible MuMu device to its pymumu service."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MuMuRegistration:
    device_id: str
    index: int
    base_url: str


_lock = threading.RLock()
_registrations: dict[str, MuMuRegistration] = {}


def _registry_path() -> Path:
    configured = os.getenv("AUTOGLM_MUMU_REGISTRY_FILE", "").strip()
    return Path(configured) if configured else Path("data/mumu_registry.json")


def _load() -> None:
    path = _registry_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(payload, list):
        return
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            registration = MuMuRegistration(
                device_id=str(item["device_id"]),
                index=int(item["index"]),
                base_url=str(item["base_url"]).rstrip("/"),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if registration.device_id and registration.index >= 0:
            _registrations[registration.device_id] = registration


def _save() -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = [
        {
            "device_id": item.device_id,
            "index": item.index,
            "base_url": item.base_url,
        }
        for item in _registrations.values()
    ]
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def register_mumu_device(device_id: str, index: int, base_url: str) -> MuMuRegistration:
    registration = MuMuRegistration(
        device_id=device_id.strip(),
        index=index,
        base_url=base_url.rstrip("/"),
    )
    if not registration.device_id:
        raise ValueError("device_id is required")
    if registration.index < 0:
        raise ValueError("MuMu index must be non-negative")
    if not registration.base_url.startswith(("http://", "https://")):
        raise ValueError("pymumu base_url must use http or https")
    with _lock:
        _registrations[registration.device_id] = registration
        _save()
    return registration


def unregister_mumu_device(device_id: str) -> bool:
    with _lock:
        removed = _registrations.pop(device_id, None) is not None
        if removed:
            _save()
        return removed


def get_mumu_registration(device_id: str) -> MuMuRegistration | None:
    with _lock:
        return _registrations.get(device_id)


def clear_mumu_registrations(*, persist: bool = False) -> None:
    with _lock:
        _registrations.clear()
        if persist:
            _save()


_load()
