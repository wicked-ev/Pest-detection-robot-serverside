import json
import logging
import threading
import time
from datetime import UTC, datetime
from typing import Dict, List, Optional

from sqlalchemy import DateTime, TypeDecorator
from sqlmodel import Field, Session, SQLModel, create_engine, select

logger = logging.getLogger("pest_robot_server.robot_store")


def utc_now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """A datetime column that always returns timezone-aware UTC values.

    SQLite has no timezone support: it stores the time without its offset and returns
    a "naive" datetime, which browsers then misread as local time. This stores UTC and
    marks values as UTC when reading them back, including rows written before this change.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime needs a timezone-aware datetime; use utc_now()")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        return value.replace(tzinfo=UTC) if value is not None else None


class RobotRecord(SQLModel, table=True):
    robot_id: str = Field(primary_key=True)
    name: str
    status: str = Field(default="offline")
    last_seen: Optional[datetime] = Field(default=None, sa_type=UTCDateTime)
    ip_address: Optional[str] = None
    streaming: bool = Field(default=False)
    last_detection: Optional[str] = None


class RobotStore:
    """Stores robot metadata in memory and persists records to SQLite.

    Reads always come from memory. Detections arrive several times a second, so they
    update memory immediately but reach the database at most once per
    detection_persist_interval per robot; a newer one waiting for its turn is "pending"
    and is saved by the next write of that robot's record, or by flush() at shutdown.
    """

    def __init__(self, db_url: str = "sqlite:///./robot_store.db", detection_persist_interval: float = 5.0) -> None:
        self._engine = create_engine(db_url, echo=False, connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(self._engine)
        self._robots: Dict[str, RobotRecord] = {}
        self._lock = threading.RLock()
        self._detection_persist_interval = detection_persist_interval
        self._pending_detections: Dict[str, str] = {}
        self._last_detection_write: Dict[str, float] = {}
        self._load_from_db()

    def _load_from_db(self) -> None:
        with Session(self._engine) as session:
            records = session.exec(select(RobotRecord)).all()
            for record in records:
                self._robots[record.robot_id] = record
        logger.info("Loaded %d robot records from persistent store.", len(self._robots))

    def mark_all_disconnected(self) -> None:
        """Reset status left over from a previous run: at startup no robot is connected yet."""
        with self._lock, Session(self._engine) as session:
            for record in session.exec(select(RobotRecord)).all():
                record.status = "offline"
                record.streaming = False
                session.add(record)
            session.commit()
        self._robots.clear()
        self._load_from_db()

    def delete_robot(self, robot_id: str) -> bool:
        with self._lock, Session(self._engine) as session:
            record = session.get(RobotRecord, robot_id)
            if record is not None:
                session.delete(record)
                session.commit()
            self._pending_detections.pop(robot_id, None)
            return self._robots.pop(robot_id, None) is not None

    def register_robot(self, robot_id: str, name: str, ip_address: Optional[str] = None) -> RobotRecord:
        now = utc_now()
        with self._lock, Session(self._engine) as session:
            record = session.get(RobotRecord, robot_id)
            if record is None:
                # Only new records start offline; re-registering must not hide a connected robot.
                record = RobotRecord(robot_id=robot_id, name=name, status="offline", last_seen=now)
            record.name = name
            if ip_address:
                record.ip_address = ip_address
            self._apply_pending_detection(record)
            session.add(record)
            session.commit()
            session.refresh(record)
            self._robots[robot_id] = record
        logger.info("Registered robot %s (%s).", robot_id, ip_address)
        return record

    def ensure_robot(self, robot_id: str, ip_address: Optional[str] = None) -> RobotRecord:
        """Create a record for a robot that connected before anyone added it in the dashboard."""
        with self._lock:
            existing = self._robots.get(robot_id)
        if existing is not None:
            return existing
        with self._lock, Session(self._engine) as session:
            record = session.get(RobotRecord, robot_id)
            if record is None:
                record = RobotRecord(robot_id=robot_id, name=robot_id, ip_address=ip_address)
                session.add(record)
                session.commit()
                session.refresh(record)
                logger.info("Auto-registered robot %s (%s).", robot_id, ip_address)
            self._robots[robot_id] = record
        return record

    def update_status(
        self,
        robot_id: str,
        status: str,
        ip_address: Optional[str] = None,
        last_seen: Optional[datetime] = None,
    ) -> Optional[RobotRecord]:
        now = last_seen or utc_now()
        with self._lock, Session(self._engine) as session:
            record = session.get(RobotRecord, robot_id)
            if record is None:
                return None
            record.status = status
            record.last_seen = now
            if ip_address is not None:
                record.ip_address = ip_address
            self._apply_pending_detection(record)
            session.add(record)
            session.commit()
            session.refresh(record)
            self._robots[robot_id] = record
        logger.info("Updated status for %s to %s.", robot_id, status)
        return record

    def set_streaming(self, robot_id: str, streaming: bool) -> Optional[RobotRecord]:
        with self._lock, Session(self._engine) as session:
            record = session.get(RobotRecord, robot_id)
            if record is None:
                return None
            record.streaming = streaming
            self._apply_pending_detection(record)
            session.add(record)
            session.commit()
            session.refresh(record)
            self._robots[robot_id] = record
        logger.info("Robot %s streaming=%s.", robot_id, streaming)
        return record

    def set_last_detection(self, robot_id: str, detection: dict) -> Optional[RobotRecord]:
        """Remember the latest result that found something; empty results are ignored."""
        if not detection.get("boxes"):
            return self.get_robot(robot_id)
        encoded = json.dumps(detection)
        with self._lock:
            cached = self._robots.get(robot_id)
            if cached is None:
                return None
            cached.last_detection = encoded
            self._pending_detections[robot_id] = encoded
            last_write = self._last_detection_write.get(robot_id)
            if last_write is not None and time.monotonic() - last_write < self._detection_persist_interval:
                return cached
            return self._persist_pending_detection(robot_id)

    def close(self) -> None:
        """Release the database connections; the store is not usable afterwards."""
        self._engine.dispose()

    def flush(self) -> None:
        """Write every pending detection; called at shutdown so none are lost."""
        with self._lock:
            for robot_id in list(self._pending_detections):
                self._persist_pending_detection(robot_id)

    def _persist_pending_detection(self, robot_id: str) -> Optional[RobotRecord]:
        with self._lock, Session(self._engine) as session:
            record = session.get(RobotRecord, robot_id)
            if record is None:
                self._pending_detections.pop(robot_id, None)
                return None
            self._apply_pending_detection(record)
            session.add(record)
            session.commit()
            session.refresh(record)
            self._robots[robot_id] = record
        return record

    def _apply_pending_detection(self, record: RobotRecord) -> None:
        """Copy a not-yet-saved detection onto a record that is about to be written."""
        pending = self._pending_detections.pop(record.robot_id, None)
        if pending is not None:
            record.last_detection = pending
            self._last_detection_write[record.robot_id] = time.monotonic()

    def get_robot(self, robot_id: str) -> Optional[RobotRecord]:
        with self._lock:
            return self._robots.get(robot_id)

    def get_all_robots(self) -> List[RobotRecord]:
        with self._lock:
            return list(self._robots.values())
