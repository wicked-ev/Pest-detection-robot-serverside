"""Detection history: groups a robot's detections into "sightings" with a photo each.

A sighting is one pest type seen by one robot. Frames of the same pest arriving within
SIGHTING_GAP of each other extend the current sighting (frame count, last seen, and the
photo of the most confident frame) instead of creating new rows. To keep disk writes low,
an active sighting changes in memory and is saved at most every persist_interval, plus
once when it ends and on flush() at shutdown.
"""

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy import func, inspect, text
from sqlmodel import Field, Session, SQLModel, create_engine, select

from .robot_store import UTCDateTime, utc_now

logger = logging.getLogger("pest_robot_server.sightings")

SIGHTING_GAP = timedelta(seconds=30)
PERSIST_INTERVAL = timedelta(seconds=5)


class SightingRecord(SQLModel, table=True):
    __tablename__ = "sighting"

    id: Optional[int] = Field(default=None, primary_key=True)
    robot_id: str = Field(index=True)
    label: str = Field(index=True)
    first_seen: datetime = Field(sa_type=UTCDateTime, index=True)
    last_seen: datetime = Field(sa_type=UTCDateTime)
    best_confidence: float
    frames: int = 1
    # Boxes of this pest in the photo, as JSON [[x1, y1, x2, y2], ...] in photo pixels.
    boxes: str = "[]"
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    has_snapshot: bool = False
    # Bumped each time a better photo replaces the old one. Photos are stored per version,
    # so details fetched just before a replacement still get the photo their boxes belong to.
    photo_version: int = 0


class SprayRecord(SQLModel, table=True):
    """One spray burst reported by a robot (manual or automatic)."""

    __tablename__ = "spray"

    id: Optional[int] = Field(default=None, primary_key=True)
    robot_id: str = Field(index=True)
    # Server time when the report arrived; the robot's clock may be unset without internet.
    time: datetime = Field(sa_type=UTCDateTime, index=True)
    trigger: str = "manual"  # "auto" or "manual"
    label: Optional[str] = None
    confidence: Optional[float] = None
    duration: float = 0.0


@dataclass
class _ActiveSighting:
    id: int
    last_seen: datetime
    last_persist: datetime
    best_confidence: float
    frames: int
    boxes: List[List[float]]
    image_size: Optional[List[int]]
    pending_photo: Optional[bytes] = None
    dirty: bool = False
    photo_version: int = 1


@dataclass
class _LabelHit:
    confidence: float
    boxes: List[List[float]] = field(default_factory=list)


class SightingStore:
    def __init__(
        self,
        db_url: str,
        snapshot_dir: Path,
        clock: Callable[[], datetime] = utc_now,
        gap: timedelta = SIGHTING_GAP,
        persist_interval: timedelta = PERSIST_INTERVAL,
    ) -> None:
        self._engine = create_engine(db_url, echo=False, connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(self._engine, tables=[SightingRecord.__table__, SprayRecord.__table__])
        self._add_missing_columns()
        self.snapshot_dir = snapshot_dir
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._gap = gap
        self._persist_interval = persist_interval
        self._active: Dict[Tuple[str, str], _ActiveSighting] = {}
        self._lock = threading.RLock()

    def _add_missing_columns(self) -> None:
        """Upgrade a database created by an older version (create_all does not add columns)."""
        existing = {column["name"] for column in inspect(self._engine).get_columns("sighting")}
        if "photo_version" not in existing:
            with self._engine.begin() as connection:
                connection.execute(text("ALTER TABLE sighting ADD COLUMN photo_version INTEGER NOT NULL DEFAULT 0"))
            logger.info("Upgraded the sighting table (added photo_version)")

    # --- recording ---------------------------------------------------------------

    def record(self, robot_id: str, result: dict, jpeg_bytes: bytes) -> None:
        """Fold one inference result into the history."""
        hits = self._group_by_label(result)
        if not hits:
            return
        now = self._clock()
        with self._lock:
            for label, hit in hits.items():
                key = (robot_id, label)
                active = self._active.get(key)
                if active is not None and now - active.last_seen > self._gap:
                    self._close(key)
                    active = None
                if active is None:
                    self._open(key, now, hit, result.get("image_size"), jpeg_bytes)
                    continue
                active.last_seen = now
                active.frames += 1
                active.dirty = True
                if hit.confidence > active.best_confidence:
                    active.best_confidence = hit.confidence
                    active.boxes = hit.boxes
                    active.image_size = result.get("image_size")
                    active.pending_photo = jpeg_bytes
                if now - active.last_persist >= self._persist_interval:
                    self._persist(active, now)

    def flush_due(self) -> None:
        """Save sightings that are due, and close those whose pest has not been seen for a while."""
        now = self._clock()
        with self._lock:
            for key, active in list(self._active.items()):
                if now - active.last_seen > self._gap:
                    self._close(key)
                elif active.dirty and now - active.last_persist >= self._persist_interval:
                    self._persist(active, now)

    def flush(self) -> None:
        """Save every active sighting (at shutdown)."""
        now = self._clock()
        with self._lock:
            for active in self._active.values():
                if active.dirty:
                    self._persist(active, now)

    def close(self) -> None:
        self._engine.dispose()

    @staticmethod
    def _group_by_label(result: dict) -> Dict[str, _LabelHit]:
        hits: Dict[str, _LabelHit] = {}
        for box, score, label in zip(result.get("boxes", []), result.get("scores", []), result.get("labels", [])):
            hit = hits.setdefault(label, _LabelHit(confidence=0.0))
            hit.confidence = max(hit.confidence, float(score))
            hit.boxes.append([float(v) for v in box])
        return hits

    def _open(self, key, now: datetime, hit: _LabelHit, image_size, jpeg_bytes: bytes) -> None:
        robot_id, label = key
        width, height = image_size if image_size else (None, None)
        record = SightingRecord(
            robot_id=robot_id,
            label=label,
            first_seen=now,
            last_seen=now,
            best_confidence=hit.confidence,
            boxes=json.dumps(hit.boxes),
            image_width=width,
            image_height=height,
        )
        with Session(self._engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        self._write_photo(record.id, 1, jpeg_bytes)
        with Session(self._engine) as session:
            stored = session.get(SightingRecord, record.id)
            stored.has_snapshot = True
            stored.photo_version = 1
            session.add(stored)
            session.commit()
        self._active[key] = _ActiveSighting(
            id=record.id,
            last_seen=now,
            last_persist=now,
            best_confidence=hit.confidence,
            frames=1,
            boxes=hit.boxes,
            image_size=image_size,
        )
        logger.info("New sighting %d: %s by %s (%.0f%%)", record.id, label, robot_id, hit.confidence * 100)

    def _close(self, key) -> None:
        active = self._active.pop(key)
        if active.dirty:
            self._persist(active, self._clock())

    def _persist(self, active: _ActiveSighting, now: datetime) -> None:
        new_version = None
        if active.pending_photo is not None:
            new_version = active.photo_version + 1
            self._write_photo(active.id, new_version, active.pending_photo)
            active.pending_photo = None
        with Session(self._engine) as session:
            record = session.get(SightingRecord, active.id)
            if record is None:
                return
            record.last_seen = active.last_seen
            record.frames = active.frames
            record.best_confidence = active.best_confidence
            record.boxes = json.dumps(active.boxes)
            if active.image_size:
                record.image_width, record.image_height = active.image_size
            if new_version is not None:
                record.photo_version = new_version
            session.add(record)
            session.commit()
        if new_version is not None:
            # Keep the previous photo for anyone who read the old details a moment ago.
            self.snapshot_path(active.id, new_version - 2).unlink(missing_ok=True)
            active.photo_version = new_version
        active.dirty = False
        active.last_persist = now

    def _write_photo(self, sighting_id: int, version: int, jpeg_bytes: bytes) -> None:
        # Write to a temporary name first so a reader never sees a half-written photo.
        path = self.snapshot_path(sighting_id, version)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(jpeg_bytes)
        os.replace(temporary, path)

    # --- reading -------------------------------------------------------------------

    def snapshot_path(self, sighting_id: int, version: int = 0) -> Path:
        # Version 0 is the single unversioned photo of sightings recorded before versioning.
        name = f"{sighting_id}.jpg" if version <= 0 else f"{sighting_id}_v{version}.jpg"
        return self.snapshot_dir / name

    def list(
        self,
        robot_id: Optional[str] = None,
        label: Optional[str] = None,
        since: Optional[datetime] = None,
        before_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[SightingRecord]:
        """Newest first. Pass the last id of a page as before_id to get the next page."""
        query = select(SightingRecord).order_by(SightingRecord.id.desc()).limit(limit)
        if robot_id:
            query = query.where(SightingRecord.robot_id == robot_id)
        if label:
            query = query.where(SightingRecord.label == label)
        if since:
            query = query.where(SightingRecord.last_seen >= since)
        if before_id:
            query = query.where(SightingRecord.id < before_id)
        with Session(self._engine) as session:
            return list(session.exec(query).all())

    def get(self, sighting_id: int) -> Optional[SightingRecord]:
        with Session(self._engine) as session:
            return session.get(SightingRecord, sighting_id)

    def record_spray(
        self,
        robot_id: str,
        trigger: str,
        duration: float,
        label: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> SprayRecord:
        record = SprayRecord(
            robot_id=robot_id,
            time=self._clock(),
            trigger=trigger,
            label=label,
            confidence=confidence,
            duration=duration,
        )
        with Session(self._engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        logger.info("Spray by %s (%s, %.1fs%s)", robot_id, trigger, duration, f", {label}" if label else "")
        return record

    def list_sprays(self, robot_id: Optional[str] = None, limit: int = 50) -> List[SprayRecord]:
        query = select(SprayRecord).order_by(SprayRecord.id.desc()).limit(limit)
        if robot_id:
            query = query.where(SprayRecord.robot_id == robot_id)
        with Session(self._engine) as session:
            return list(session.exec(query).all())

    def spray_counts(self, sightings: List[SightingRecord]) -> Dict[int, int]:
        """How many sprays targeted each sighting: same robot and pest, during it (or just after)."""
        if not sightings:
            return {}
        earliest = min(s.first_seen for s in sightings)
        latest = max(s.last_seen for s in sightings) + self._gap
        robot_ids = {s.robot_id for s in sightings}
        query = select(SprayRecord).where(
            SprayRecord.time >= earliest,
            SprayRecord.time <= latest,
            SprayRecord.robot_id.in_(robot_ids),
            SprayRecord.label.is_not(None),
        )
        with Session(self._engine) as session:
            sprays = list(session.exec(query).all())
        counts: Dict[int, int] = {}
        for sighting in sightings:
            counts[sighting.id] = sum(
                1
                for spray in sprays
                if spray.robot_id == sighting.robot_id
                and spray.label == sighting.label
                and sighting.first_seen <= spray.time <= sighting.last_seen + self._gap
            )
        return counts

    def summary(self, robot_id: Optional[str] = None, since: Optional[datetime] = None) -> List[dict]:
        """Sightings per pest type, most frequent first."""
        query = select(
            SightingRecord.label,
            func.count(SightingRecord.id),
            func.max(SightingRecord.last_seen),
        ).group_by(SightingRecord.label)
        if robot_id:
            query = query.where(SightingRecord.robot_id == robot_id)
        if since:
            query = query.where(SightingRecord.last_seen >= since)
        with Session(self._engine) as session:
            rows = session.exec(query).all()
        result = [
            {"label": label, "count": count, "last_seen": UTCDateTime().process_result_value(last, None)}
            for label, count, last in rows
        ]
        return sorted(result, key=lambda row: (-row["count"], row["label"]))
