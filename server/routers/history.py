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


def sighting_json(record: SightingRecord, sprays: int = 0) -> Dict[str, Any]:
    data = record.model_dump()
    data["sprays"] = sprays
    data["boxes"] = json.loads(record.boxes)
    # The version in the URL pins the photo that matches these boxes.
    data["snapshot_url"] = (
        f"/api/sightings/{record.id}/snapshot?v={record.photo_version}" if record.has_snapshot else None
    )
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
    counts = await asyncio.to_thread(store.spray_counts, records)
    return [sighting_json(record, counts.get(record.id, 0)) for record in records]


@router.get("/api/sightings/summary")
async def sightings_summary(
    request: Request,
    robot_id: Optional[str] = None,
    since: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    store = get_sightings(request)
    return await asyncio.to_thread(store.summary, robot_id, since)


@router.get("/api/sprays")
async def list_sprays(
    request: Request,
    robot_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
) -> List[Dict[str, Any]]:
    records = await asyncio.to_thread(get_sightings(request).list_sprays, robot_id, limit)
    return [record.model_dump() for record in records]


@router.get("/api/sightings/{sighting_id}")
async def get_sighting(sighting_id: int, request: Request) -> Dict[str, Any]:
    store = get_sightings(request)
    record = await asyncio.to_thread(store.get, sighting_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Sighting not found")
    counts = await asyncio.to_thread(store.spray_counts, [record])
    return sighting_json(record, counts.get(record.id, 0))


@router.get("/api/sightings/{sighting_id}/snapshot")
async def get_snapshot(sighting_id: int, request: Request, v: Optional[int] = None) -> FileResponse:
    store = get_sightings(request)
    path = store.snapshot_path(sighting_id, v) if v is not None else None
    if path is None or not path.exists():
        # No (or an expired) version requested: serve the current photo.
        record = await asyncio.to_thread(store.get, sighting_id)
        if record is None or not record.has_snapshot:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        path = store.snapshot_path(sighting_id, record.photo_version)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Snapshot not found")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
    # A given version never changes, so the browser may keep it.
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400, immutable"})
