"""
Task service — backs the dashboard's "My Tasks" panel.

Tenant-scoped like CRMService: every read filtered by organization_id,
every write stamped with it. Deliberately simple (no recurrence, no
sub-tasks) — this is a to-do list, not a project-management system.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..database.db import get_db
from ..database.models import Task

VALID_PRIORITIES = ("low", "medium", "high")


class TaskService:
    def __init__(self, organization_id: int):
        if not organization_id:
            raise ValueError("TaskService requires organization_id.")
        self.organization_id = organization_id

    def list_open(self, assigned_to_id: Optional[int] = None, limit: int = 10) -> list[dict]:
        with get_db() as db:
            q = db.query(Task).filter(
                Task.organization_id == self.organization_id,
                Task.status == "open",
            )
            if assigned_to_id:
                q = q.filter(Task.assigned_to_id == assigned_to_id)
            rows = (
                q.order_by(Task.due_date.is_(None), Task.due_date.asc(), Task.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._dict(t) for t in rows]

    def create(self, data: dict) -> dict:
        with get_db() as db:
            priority = data.get("priority", "medium")
            t = Task(
                organization_id=self.organization_id,
                assigned_to_id=data.get("assigned_to_id"),
                created_by_id=data.get("created_by_id"),
                title=data["title"],
                description=data.get("description"),
                priority=priority if priority in VALID_PRIORITIES else "medium",
                due_date=data.get("due_date"),
                related_type=data.get("related_type"),
                related_id=data.get("related_id"),
            )
            db.add(t)
            db.flush()
            return self._dict(t)

    def complete(self, task_id: int) -> bool:
        with get_db() as db:
            t = (
                db.query(Task)
                .filter(Task.id == task_id, Task.organization_id == self.organization_id)
                .first()
            )
            if not t:
                return False
            t.status = "done"
            t.completed_at = datetime.utcnow()
            return True

    def _dict(self, t: Task) -> dict:
        return {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "priority": t.priority,
            "status": t.status,
            "due_date": t.due_date.strftime("%Y-%m-%d") if t.due_date else None,
            "related_type": t.related_type,
            "related_id": t.related_id,
            "assigned_to_id": t.assigned_to_id,
        }
