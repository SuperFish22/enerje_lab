import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class MentionService:
    def __init__(self, db):
        self.db = db
    
    def register_for_mentions(self, chat_id: int, user_id: int, 
                            telegram_id: int, username: str, first_name: str) -> bool:
        """Зарегистрировать пользователя для упоминаний"""
        cursor = self.db.conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO group_mentions 
                (chat_id, user_id, telegram_id, username, first_name)
                VALUES (?, ?, ?, ?, ?)
            ''', (chat_id, user_id, telegram_id, username, first_name))
            
            self.db.conn.commit()
            logger.info(f"Пользователь {user_id} зарегистрирован для упоминаний")
            return True
        except Exception as e:
            logger.error(f"Ошибка регистрации: {e}")
            return False
    
    def get_mention_users(self, chat_id: int) -> List[Dict]:
        """Получить пользователей для упоминания в чате"""
        cursor = self.db.conn.cursor()
        
        cursor.execute('''
            SELECT telegram_id, username, first_name
            FROM group_mentions
            WHERE chat_id = ?
        ''', (chat_id,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def is_user_registered(self, chat_id: int, user_id: int) -> bool:
        """Проверить регистрацию пользователя"""
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT 1 FROM group_mentions 
            WHERE chat_id = ? AND user_id = ? LIMIT 1
        ''', (chat_id, user_id))
        return cursor.fetchone() is not None