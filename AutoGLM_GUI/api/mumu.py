"""Internal registration API for MuMu devices controlled by pymumu."""

from fastapi import APIRouter
from pydantic import BaseModel, Field, HttpUrl

from AutoGLM_GUI.mumu_registry import (
    get_mumu_registration,
    register_mumu_device,
    unregister_mumu_device,
)

router = APIRouter()


class MuMuRegistrationRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=255)
    index: int = Field(ge=0)
    base_url: HttpUrl


@router.put("/api/devices/mumu")
async def register_mumu(request: MuMuRegistrationRequest) -> dict[str, object]:
    registration = register_mumu_device(
        request.device_id, request.index, str(request.base_url)
    )
    return {
        "success": True,
        "device_id": registration.device_id,
        "index": registration.index,
        "base_url": registration.base_url,
    }


@router.delete("/api/devices/mumu/{device_id:path}")
async def unregister_mumu(device_id: str) -> dict[str, object]:
    return {"success": True, "removed": unregister_mumu_device(device_id)}


@router.get("/api/devices/mumu/{device_id:path}")
async def get_mumu(device_id: str) -> dict[str, object]:
    registration = get_mumu_registration(device_id)
    return {
        "success": True,
        "registered": registration is not None,
        "index": registration.index if registration else None,
        "base_url": registration.base_url if registration else None,
    }
