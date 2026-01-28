from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Task:
    id: Optional[int] = None
    title: str = ""
    description: str = ""
    created_by: int = 0
    assigned_to: Optional[int] = None
    priority: str = "medium"  # low, medium, high, critical
    status: str = "new"  # new, in_progress, review, completed, cancelled
    deadline: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'created_by': self.created_by,
            'assigned_to': self.assigned_to,
            'priority': self.priority,
            'status': self.status,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }