import logging
import random
from typing import List, Dict, Optional
import json

logger = logging.getLogger(__name__)

class QuoteService:
    def __init__(self, db):
        self.db = db
        self._init_default_quotes()
    
    def _init_default_quotes(self):
        """Инициализация стандартных цитат при первом запуске"""
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM quotes')
        count = cursor.fetchone()[0]
        
        if count == 0:
            default_quotes = [
                ("Единственный способ сделать великую работу — любить то, что ты делаешь.", "Стив Джобс", "work"),
                ("Не ошибается тот, кто ничего не делает!", "Теодор Рузвельт", "motivation"),
                ("Успех — это способность идти от поражения к поражению, не теряя оптимизма.", "Уинстон Черчилль", "success"),
                ("Лучший способ предсказать будущее — создать его.", "Питер Друкер", "future"),
                ("Сложнее всего начать действовать, все остальное зависит только от упорства.", "Амелия Эрхарт", "action"),
                ("Ваше время ограничено, не тратьте его, живя чужой жизнью.", "Стив Джобс", "life"),
                ("Победа — это еще не все, все — это постоянное желание побеждать.", "Винс Ломбарди", "victory"),
                ("Либо вы управляете днем, либо день управляет вами.", "Джим Рон", "time"),
                ("Единственное ограничение для осуществления завтрашних планов — сегодняшние сомнения.", "Франклин Рузвельт", "doubt"),
                ("Мечты не работают, пока не работаешь ты.", "Аноним", "dreams"),
            ]
            
            for text, author, category in default_quotes:
                cursor.execute('''
                    INSERT INTO quotes (text, author, category)
                    VALUES (?, ?, ?)
                ''', (text, author, category))
            
            self.db.conn.commit()
            logger.info("Добавлены стандартные цитаты")
    
    def get_random_quote(self, category: Optional[str] = None) -> Optional[Dict]:
        """Получить случайную цитату"""
        cursor = self.db.conn.cursor()
        
        if category:
            cursor.execute('''
                SELECT * FROM quotes 
                WHERE category = ? 
                ORDER BY RANDOM() 
                LIMIT 1
            ''', (category,))
        else:
            cursor.execute('SELECT * FROM quotes ORDER BY RANDOM() LIMIT 1')
        
        row = cursor.fetchone()
        
        if row:
            # Увеличиваем счетчик использования
            cursor.execute('UPDATE quotes SET used_count = used_count + 1 WHERE id = ?', (row['id'],))
            self.db.conn.commit()
            
            return dict(row)
        return None
    
    def add_quote(self, text: str, author: str = "", category: str = "general", 
                 created_by: Optional[int] = None) -> bool:
        """Добавить новую цитату"""
        cursor = self.db.conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO quotes (text, author, category, created_by)
                VALUES (?, ?, ?, ?)
            ''', (text, author, category, created_by))
            
            self.db.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления цитаты: {e}")
            self.db.conn.rollback()
            return False
    
    def get_all_quotes(self, category: Optional[str] = None) -> List[Dict]:
        """Получить все цитаты"""
        cursor = self.db.conn.cursor()
        
        if category:
            cursor.execute('SELECT * FROM quotes WHERE category = ? ORDER BY used_count DESC', (category,))
        else:
            cursor.execute('SELECT * FROM quotes ORDER BY used_count DESC')
        
        return [dict(row) for row in cursor.fetchall()]
    
    def delete_quote(self, quote_id: int) -> bool:
        """Удалить цитату"""
        cursor = self.db.conn.cursor()
        
        try:
            cursor.execute('DELETE FROM quotes WHERE id = ?', (quote_id,))
            self.db.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка удаления цитаты: {e}")
            self.db.conn.rollback()
            return False
    
    def get_categories(self) -> List[str]:
        """Получить все категории цитат"""
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT DISTINCT category FROM quotes')
        
        return [row['category'] for row in cursor.fetchall()]