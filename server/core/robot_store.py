import json
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select

logger = logging.getLogger("pest_robot_server.robot_store")


class RobotRecord(SQLModel, table=True):
    robot_id: str = Field(primary_key=True)
    name: str
    status: str = Field(default="offline")
    last_seen: Optional[datetime] = None
    ip_address: Optional[str] = None
    streaming: bool = Field(default=False)
    last_detection: Optional[str] = None


class RobotStore:
    """Stores robot metadata in memory and persists records to SQLite."""

    def __init__(self, db_url: str = "sqlite:///./robot_store.db") -> None:
        self._engine = create_engine(db_url, echo=False, connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(self._engine)
        self._robots: Dict[str, RobotRecord] = {}
        self._lock = threading.RLock()
        self._load_from_db()

    def _load_from_db(self) -> None:
        with Session(self._engine) as session:
            records = session.exec(select(RobotRecord)).all()
            for record in records:
                self._robots[record.robot_id] = record
        logger.info("Loaded %d robot records from persistent store.", len(self._robots))

    def register_robot(self, robot_id: str, name: str, ip_address: str) -> RobotRecord:
        now = datetime.utcnow()
        with self._lock, Session(self._engine) as session:
            record = session.get(RobotRecord, robot_id)
            if record is None:
                record = RobotRecord(robot_id=robot_id, name=name)
            record.name = name
            record.ip_address = ip_address
            record.status = "offline"
            record.last_seen = now
            session.add(record)
            session.commit()
            session.refresh(record)
            self._robots[robot_id] = record
        logger.info("Registered robot %s (%s).", robot_id, ip_address)
        return record

    def update_status(
        self,
        robot_id: str,
        status: str,
        ip_address: Optional[str] = None,
        last_seen: Optional[datetime] = None,
    ) -> Optional[RobotRecord]:
        now = last_seen or datetime.utcnow()
        with self._lock, Session(self._engine) as session:
            record = session.get(RobotRecord, robot_id)
            if record is None:
                return None
            record.status = status
            record.last_seen = now
            if ip_address is not None:
                record.ip_address = ip_address
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
            session.add(record)
            session.commit()
            session.refresh(record)
            self._robots[robot_id] = record
        logger.info("Robot %s streaming=%s.", robot_id, streaming)
        return record

    def set_last_detection(self, robot_id: str, detection: dict) -> Optional[RobotRecord]:
        with self._lock, Session(self._engine) as session:
            record = session.get(RobotRecord, robot_id)
            if record is None:
                return None
            record.last_detection = json.dumps(detection)
            record.last_seen = datetime.utcnow()
            session.add(record)
            session.commit()
            session.refresh(record)
            self._robots[robot_id] = record
        return record

    def get_robot(self, robot_id: str) -> Optional[RobotRecord]:
        with self._lock:
            return self._robots.get(robot_id)

    def get_all_robots(self) -> List[RobotRecord]:
        with self._lock:
            return list(self._robots.values())
