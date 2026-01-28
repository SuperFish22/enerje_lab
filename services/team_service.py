# services/team_service.py
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class TeamService:
    def __init__(self, db):
        self.db = db
        self.setup_tables()
    
    def setup_tables(self):
        """Создание таблиц для команд"""
        cursor = self.db.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                leader_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                role TEXT DEFAULT 'member',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(team_id, admin_id)
            )
        ''')
        
        self.db.conn.commit()
        logger.info("Таблицы teams и team_members созданы/проверены")
    
    def create_team(self, name, description="", leader_id=None):
        """Создать команду"""
        cursor = self.db.conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO teams (name, description, leader_id)
                VALUES (?, ?, ?)
            ''', (name, description, leader_id))
            
            team_id = cursor.lastrowid
            
            # Добавляем лидера в команду
            if leader_id:
                self.add_team_member(team_id, leader_id, 'leader')
            
            self.db.conn.commit()
            return team_id
        except Exception as e:
            logger.error(f"Ошибка создания команды: {e}")
            self.db.conn.rollback()
            return None
    
    def add_team_member(self, team_id, admin_id, role='member'):
        """Добавить участника в команду"""
        cursor = self.db.conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO team_members (team_id, admin_id, role)
                VALUES (?, ?, ?)
            ''', (team_id, admin_id, role))
            
            self.db.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления участника: {e}")
            self.db.conn.rollback()
            return False
    
    def get_user_teams(self, admin_id):
        """Получить команды пользователя"""
        cursor = self.db.conn.cursor()
        
        cursor.execute('''
            SELECT t.*, tm.role
            FROM teams t
            JOIN team_members tm ON t.id = tm.team_id
            WHERE tm.admin_id = ?
            ORDER BY t.created_at DESC
        ''', (admin_id,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_team_members(self, team_id):
        """Получить участников команды"""
        cursor = self.db.conn.cursor()
        
        cursor.execute('''
            SELECT admin_id as telegram_id, role
            FROM team_members 
            WHERE team_id = ?
        ''', (team_id,))
        
        return [dict(row) for row in cursor.fetchall()]