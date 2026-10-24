import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from core.sightings import SightingRecord, SightingStore

router = APIRouter()


def get_sightings(request: Request) -> SightingStore:
    return request.app.state.sightings


def sighting_json(record: SightingRecord) -> Dict[str, Any]:
    data = record.model_dump()
    data["boxes"] = json.loads(record.boxes)
    data["snapshot_url"] = f"/api/sightings/{record.id}/snapshot" if record.has_snapshot else None
    del data["has_snapshot"]
    return data


@router.get("/api/sightings")
async def list_sightings(
    request: Request,
    robot_id: Optional[str] = None,
    label: Optional[str] = None,
    since: Optional[datetime] = Query(None, description="Only sightings seen at or after this time (ISO 8601)"),
    before_id: Optional[int] = Query(None, description="For paging: the id of the last sighting already shown"),
    limit: int = Query(50, ge=1, le=200),
) -> List[Dict[str, Any]]:
    store = get_sightings(request)
    records = await asyncio.to_thread(store.list, robot_id, label, since, before_id, limit)
    return [sighting_json(record) for record in records]


@router.get("/api/sightings/summary")
async def sightings_summary(
    request: Request,
    robot_id: Optional[str] = None,
    since: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    store = get_sightings(request)
    return await asyncio.to_thread(store.summary, robot_id, since)


@router.get("/api/sightings/{sighting_id}")
async def get_sighting(sighting_id: int, request: Request) -> Dict[str, Any]:
    record = await asyncio.to_thread(get_sightings(request).get, sighting_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Sighting not found")
    return sighting_json(record)


@router.get("/api/sightings/{sighting_id}/snapshot")
async def get_snapshot(sighting_id: int, request: Request) -> FileResponse:
    path = get_sightings(request).snapshot_path(sighting_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Snapshot not found")
    # The photo can be replaced by a better frame while the sighting is active.
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
