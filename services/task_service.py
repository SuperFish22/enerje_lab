import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from models.task import Task

logger = logging.getLogger(__name__)

class TaskService:
    def __init__(self, db):
        self.db = db
    
    def create_task(self, title: str, description: str, created_by: int, 
                   assigned_to: Optional[int] = None, priority: str = "medium",
                   deadline: Optional[datetime] = None) -> Optional[Task]:
        """Создать новую задачу"""
        cursor = self.db.conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO tasks 
                (title, description, created_by, assigned_to, priority, deadline)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (title, description, created_by, assigned_to, priority, deadline))
            
            task_id = cursor.lastrowid
            self.db.conn.commit()
            
            return self.get_task_by_id(task_id)
        except Exception as e:
            logger.error(f"Ошибка создания задачи: {e}")
            self.db.conn.rollback()
            return None
    
    def get_task_by_id(self, task_id: int) -> Optional[Task]:
        """Получить задачу по ID"""
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
        row = cursor.fetchone()
        
        if row:
            return self._row_to_task(row)
        return None
    
    def get_user_tasks(self, user_id: int, status: Optional[str] = None) -> List[Task]:
        """Получить задачи пользователя"""
        cursor = self.db.conn.cursor()
        
        if status:
            cursor.execute('''
                SELECT * FROM tasks 
                WHERE assigned_to = ? AND status = ?
                ORDER BY 
                    CASE priority 
                        WHEN 'critical' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3
                        WHEN 'low' THEN 4
                    END,
                    deadline ASC
            ''', (user_id, status))
        else:
            cursor.execute('''
                SELECT * FROM tasks 
                WHERE assigned_to = ?
                ORDER BY 
                    CASE priority 
                        WHEN 'critical' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3
                        WHEN 'low' THEN 4
                    END,
                    deadline ASC
            ''', (user_id,))
        
        return [self._row_to_task(row) for row in cursor.fetchall()]
    
    def get_all_tasks(self, filters: Optional[Dict] = None) -> List[Task]:
        """Получить все задачи с фильтрами"""
        cursor = self.db.conn.cursor()
        
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        
        if filters:
            if 'status' in filters:
                query += " AND status = ?"
                params.append(filters['status'])
            if 'priority' in filters:
                query += " AND priority = ?"
                params.append(filters['priority'])
            if 'assigned_to' in filters:
                query += " AND assigned_to = ?"
                params.append(filters['assigned_to'])
            if 'created_by' in filters:
                query += " AND created_by = ?"
                params.append(filters['created_by'])
        
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        
        return [self._row_to_task(row) for row in cursor.fetchall()]
    
    def update_task_status(self, task_id: int, status: str, user_id: int) -> bool:
        """Обновить статус задачи"""
        cursor = self.db.conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE tasks 
                SET status = ?, updated_at = CURRENT_TIMESTAMP,
                    completed_at = CASE WHEN ? = 'completed' THEN CURRENT_TIMESTAMP ELSE completed_at END
                WHERE id = ? AND assigned_to = ?
            ''', (status, status, task_id, user_id))
            
            self.db.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка обновления задачи: {e}")
            self.db.conn.rollback()
            return False
    
    def assign_task(self, task_id: int, assigned_to: int) -> bool:
        """Назначить задачу пользователю"""
        cursor = self.db.conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE tasks 
                SET assigned_to = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (assigned_to, task_id))
            
            self.db.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка назначения задачи: {e}")
            self.db.conn.rollback()
            return False
    
    def delete_task(self, task_id: int, user_id: int) -> bool:
        """Удалить задачу (только создатель)"""
        cursor = self.db.conn.cursor()
        
        try:
            cursor.execute('DELETE FROM tasks WHERE id = ? AND created_by = ?', 
                          (task_id, user_id))
            
            self.db.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка удаления задачи: {e}")
            self.db.conn.rollback()
            return False
    
    def get_overdue_tasks(self) -> List[Task]:
        """Получить просроченные задачи"""
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT * FROM tasks 
            WHERE status NOT IN ('completed', 'cancelled') 
            AND deadline IS NOT NULL 
            AND deadline < CURRENT_TIMESTAMP
            ORDER BY deadline ASC
        ''')
        
        return [self._row_to_task(row) for row in cursor.fetchall()]
    
    def _row_to_task(self, row) -> Task:
        """Преобразовать строку БД в объект Task"""
        return Task(
            id=row['id'],
            title=row['title'],
            description=row['description'],
            created_by=row['created_by'],
            assigned_to=row['assigned_to'],
            priority=row['priority'],
            status=row['status'],
            deadline=datetime.fromisoformat(row['deadline']) if row['deadline'] else None,
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
            updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
            completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
        )