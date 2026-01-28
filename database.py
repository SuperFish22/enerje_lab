import sqlite3
import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Any
from config import config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_name = config.DB_NAME
        self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()
        self.clean_old_messages()
    
    def create_tables(self):
        """Создание таблиц в БД"""
        cursor = self.conn.cursor()
        
        # ==================== ОСНОВНЫЕ ТАБЛИЦЫ ====================
        
        # Пользователи
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_banned BOOLEAN DEFAULT 0,
                ban_reason TEXT,
                ban_until TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Сообщения
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                status TEXT DEFAULT 'new',
                is_anonymous BOOLEAN DEFAULT 1,
                priority INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                replied_at TIMESTAMP,
                response_time INTEGER,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        ''')
        
        # Ответы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE
            )
        ''')
        
        # Администраторы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                role TEXT DEFAULT 'moderator',
                permissions TEXT DEFAULT 'read,reply',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_mentions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        telegram_id INTEGER NOT NULL,
        username TEXT,
        first_name TEXT,
        wants_mentions BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(chat_id, user_id)
        )
    ''')
        
        # Статистика
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE NOT NULL,
                total_messages INTEGER DEFAULT 0,
                new_messages INTEGER DEFAULT 0,
                replied_messages INTEGER DEFAULT 0,
                unique_users INTEGER DEFAULT 0
            )
        ''')
        
        # ==================== ТАБЛИЦЫ ДЛЯ ЗАДАЧ ====================
        
        # Таблица задач (tasks)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                created_by INTEGER NOT NULL,
                assigned_to INTEGER,
                priority TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'new',
                deadline TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES admins (id),
                FOREIGN KEY (assigned_to) REFERENCES admins (id)
            )
        ''')
        
        # Таблица команд (teams)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                leader_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (leader_id) REFERENCES admins (id)
            )
        ''')
        
        # Таблица членов команд (team_members)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                role TEXT DEFAULT 'member',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams (id) ON DELETE CASCADE,
                FOREIGN KEY (admin_id) REFERENCES admins (id) ON DELETE CASCADE,
                UNIQUE(team_id, admin_id)
            )
        ''')
        
        # Таблица мотивационных цитат (quotes)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                author TEXT,
                category TEXT DEFAULT 'general',
                used_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (created_by) REFERENCES admins (id)
            )
        ''')
        
        # Таблица уведомлений (notifications)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                data TEXT,  -- JSON данные
                is_read BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES admins (id)
            )
        ''')
        
        # ==================== ИНДЕКСЫ ====================
        
        # Индексы для основных таблиц
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id)')
        # Индекс для таблицы упоминания
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_group_mentions_chat ON group_mentions(chat_id)')
        # Индексы для таблиц задач
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_to)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_team_members_admin ON team_members(admin_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quotes_category ON quotes(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read)')
        
        self.conn.commit()
        logger.info("✅ Все таблицы БД созданы/проверены")
        
        # Добавляем администраторов из конфига
        self.add_admins_from_config()
    
    def add_admins_from_config(self):
        """Добавить администраторов из конфигурации"""
        cursor = self.conn.cursor()
        for admin_id in config.ADMIN_IDS:
            cursor.execute(
                'INSERT OR IGNORE INTO admins (telegram_id, role, permissions) VALUES (?, ?, ?)',
                (admin_id, 'admin', 'read,reply,delete,ban,stats,broadcast')
            )
        self.conn.commit()
        logger.info(f"✅ Добавлены администраторы из конфига: {config.ADMIN_IDS}")
    
    def add_user(self, telegram_id: int, username: str = None, 
                 first_name: str = None, last_name: str = None) -> int:
        """Добавить или обновить пользователя"""
        cursor = self.conn.cursor()
        
        # Проверяем, забанен ли пользователь
        cursor.execute(
            'SELECT is_banned, ban_until FROM users WHERE telegram_id = ?',
            (telegram_id,)
        )
        user = cursor.fetchone()
        
        if user and user['is_banned']:
            ban_until = None
            if user['ban_until']:
                try:
                    # Пробуем разные форматы даты
                    ban_until = datetime.strptime(user['ban_until'], '%Y-%m-%d %H:%M:%S')
                except:
                    try:
                        ban_until = datetime.fromisoformat(user['ban_until'].replace('Z', '+00:00'))
                    except:
                        pass
            
            if ban_until and ban_until > datetime.now():
                raise Exception("Пользователь забанен")
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (telegram_id, username, first_name, last_name, last_activity) 
            VALUES (?, ?, ?, ?, ?)
        ''', (telegram_id, username, first_name, last_name, datetime.now()))
        
        self.conn.commit()
        return cursor.lastrowid
    
    def add_message(self, telegram_id: int, text: str, 
                   category: str = 'general', is_anonymous: bool = True) -> Dict[str, Any]:
        """Добавить новое сообщение"""
        user_id = self.add_user(telegram_id)
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO messages (user_id, text, category, is_anonymous)
            VALUES (?, ?, ?, ?)
        ''', (user_id, text, category, is_anonymous))
        
        message_id = cursor.lastrowid
        
        # Обновляем статистику
        self.update_statistics()
        
        self.conn.commit()
        
        return {
            'message_id': message_id,
            'user_id': user_id,
            'telegram_id': telegram_id
        }
    
    def get_new_messages(self, limit: int = 50) -> List[Dict]:
        """Получить новые сообщения"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT m.*, u.telegram_id, u.username, u.first_name, u.last_name
            FROM messages m
            JOIN users u ON m.user_id = u.id
            WHERE m.status = 'new'
            ORDER BY m.created_at ASC
            LIMIT ?
        ''', (limit,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_user_messages(self, telegram_id: int, limit: int = 20) -> List[Dict]:
        """Получить сообщения пользователя"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT m.*, r.text as reply_text, r.created_at as reply_date,
                   a.telegram_id as admin_id
            FROM messages m
            LEFT JOIN replies r ON m.id = r.message_id
            LEFT JOIN admins a ON r.admin_id = a.id
            WHERE m.user_id = (SELECT id FROM users WHERE telegram_id = ?)
            ORDER BY m.created_at DESC
            LIMIT ?
        ''', (telegram_id, limit))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def add_reply(self, message_id: int, admin_telegram_id: int, text: str) -> bool:
        """Добавить ответ администратора"""
        cursor = self.conn.cursor()
        
        # Получаем admin_id
        cursor.execute(
            'SELECT id FROM admins WHERE telegram_id = ?',
            (admin_telegram_id,)
        )
        admin = cursor.fetchone()
        
        if not admin:
            logger.error(f"Администратор с Telegram ID {admin_telegram_id} не найден в БД")
            return False
        
        # Добавляем ответ
        cursor.execute('''
            INSERT INTO replies (message_id, admin_id, text)
            VALUES (?, ?, ?)
        ''', (message_id, admin['id'], text))
        
        # Обновляем статус сообщения
        cursor.execute('''
            UPDATE messages 
            SET status = 'replied', 
                replied_at = CURRENT_TIMESTAMP,
                response_time = CAST(
                    (julianday(CURRENT_TIMESTAMP) - julianday(created_at)) * 24 * 60 
                    AS INTEGER
                )
            WHERE id = ?
        ''', (message_id,))
        
        self.conn.commit()
        self.update_statistics()
        logger.info(f"✅ Ответ на сообщение #{message_id} добавлен")
        return True
    
    def get_stats(self, days: int = 30) -> Dict[str, Any]:
        """Получить статистику"""
        cursor = self.conn.cursor()
        
        # Общая статистика
        cursor.execute('''
            SELECT 
                COUNT(*) as total_messages,
                SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) as new_messages,
                SUM(CASE WHEN status = 'replied' THEN 1 ELSE 0 END) as replied_messages,
                AVG(response_time) as avg_response_time,
                COUNT(DISTINCT user_id) as unique_users
            FROM messages
            WHERE created_at >= date('now', ?)
        ''', (f'-{days} days',))
        
        row = cursor.fetchone()
        stats = dict(row) if row else {
            'total_messages': 0,
            'new_messages': 0,
            'replied_messages': 0,
            'avg_response_time': 0,
            'unique_users': 0
        }
        
        # Статистика по дням
        cursor.execute('''
            SELECT 
                date(created_at) as day,
                COUNT(*) as messages,
                SUM(CASE WHEN status = 'replied' THEN 1 ELSE 0 END) as replied
            FROM messages
            WHERE created_at >= date('now', ?)
            GROUP BY date(created_at)
            ORDER BY day DESC
        ''', (f'-{days} days',))
        
        stats['daily'] = [dict(row) for row in cursor.fetchall()]
        
        return stats
    
    def update_statistics(self):
        """Обновить дневную статистику"""
        cursor = self.conn.cursor()
        today = datetime.now().date().isoformat()
        
        cursor.execute(
            'SELECT id FROM statistics WHERE date = ?',
            (today,)
        )
        
        if cursor.fetchone():
            cursor.execute('''
                UPDATE statistics SET
                    total_messages = (SELECT COUNT(*) FROM messages WHERE date(created_at) = ?),
                    new_messages = (SELECT COUNT(*) FROM messages WHERE date(created_at) = ? AND status = 'new'),
                    replied_messages = (SELECT COUNT(*) FROM messages WHERE date(created_at) = ? AND status = 'replied'),
                    unique_users = (SELECT COUNT(DISTINCT user_id) FROM messages WHERE date(created_at) = ?)
                WHERE date = ?
            ''', (today, today, today, today, today))
        else:
            cursor.execute('''
                INSERT INTO statistics (date, total_messages, new_messages, replied_messages, unique_users)
                SELECT 
                    ?,
                    COUNT(*) as total_messages,
                    SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) as new_messages,
                    SUM(CASE WHEN status = 'replied' THEN 1 ELSE 0 END) as replied_messages,
                    COUNT(DISTINCT user_id) as unique_users
                FROM messages
                WHERE date(created_at) = ?
            ''', (today, today))
        
        self.conn.commit()
    
    def clean_old_messages(self):
        """Удалить старые сообщения"""
        if config.AUTO_DELETE_DAYS <= 0:
            return
        
        cursor = self.conn.cursor()
        delete_before = datetime.now() - timedelta(days=config.AUTO_DELETE_DAYS)
        
        cursor.execute(
            'DELETE FROM messages WHERE created_at < ? AND status = "replied"',
            (delete_before,)
        )
        
        deleted_count = cursor.rowcount
        self.conn.commit()
        
        if deleted_count > 0:
            logger.info(f"✅ Удалены {deleted_count} старых сообщений (старше {config.AUTO_DELETE_DAYS} дней)")
    
    # ==================== МЕТОДЫ ДЛЯ РАБОТЫ С ЗАДАЧАМИ ====================
    
    def create_task(self, title: str, description: str, created_by: int, 
                   assigned_to: Optional[int] = None, priority: str = 'medium',
                   deadline: Optional[datetime] = None) -> Optional[int]:
        """Создать новую задачу"""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO tasks 
                (title, description, created_by, assigned_to, priority, deadline)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (title, description, created_by, assigned_to, priority, deadline))
            
            task_id = cursor.lastrowid
            self.conn.commit()
            logger.info(f"✅ Создана задача #{task_id}: '{title}'")
            return task_id
        except Exception as e:
            logger.error(f"❌ Ошибка создания задачи: {e}")
            self.conn.rollback()
            return None
    
    def get_user_tasks(self, admin_id: int, status: Optional[str] = None) -> List[Dict]:
        """Получить задачи пользователя"""
        cursor = self.conn.cursor()
        
        # Получаем ID администратора по telegram_id
        cursor.execute('SELECT id FROM admins WHERE telegram_id = ?', (admin_id,))
        admin = cursor.fetchone()
        
        if not admin:
            return []
        
        admin_db_id = admin['id']
        
        if status:
            cursor.execute('''
                SELECT t.*, a1.telegram_id as created_by_telegram, 
                       a2.telegram_id as assigned_to_telegram
                FROM tasks t
                LEFT JOIN admins a1 ON t.created_by = a1.id
                LEFT JOIN admins a2 ON t.assigned_to = a2.id
                WHERE t.assigned_to = ? AND t.status = ?
                ORDER BY 
                    CASE t.priority 
                        WHEN 'critical' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3
                        WHEN 'low' THEN 4
                    END,
                    t.deadline ASC
            ''', (admin_db_id, status))
        else:
            cursor.execute('''
                SELECT t.*, a1.telegram_id as created_by_telegram, 
                       a2.telegram_id as assigned_to_telegram
                FROM tasks t
                LEFT JOIN admins a1 ON t.created_by = a1.id
                LEFT JOIN admins a2 ON t.assigned_to = a2.id
                WHERE t.assigned_to = ?
                ORDER BY 
                    CASE t.priority 
                        WHEN 'critical' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3
                        WHEN 'low' THEN 4
                    END,
                    t.deadline ASC
            ''', (admin_db_id,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_all_tasks(self) -> List[Dict]:
        """Получить все задачи"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT t.*, a1.telegram_id as created_by_telegram, 
                   a2.telegram_id as assigned_to_telegram,
                   a1.username as created_by_username,
                   a2.username as assigned_to_username
            FROM tasks t
            LEFT JOIN admins a1 ON t.created_by = a1.id
            LEFT JOIN admins a2 ON t.assigned_to = a2.id
            ORDER BY t.created_at DESC
        ''')
        
        return [dict(row) for row in cursor.fetchall()]
    
    def update_task_status(self, task_id: int, status: str, admin_id: int) -> bool:
        """Обновить статус задачи"""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE tasks 
                SET status = ?, updated_at = CURRENT_TIMESTAMP,
                    completed_at = CASE WHEN ? = 'completed' THEN CURRENT_TIMESTAMP ELSE completed_at END
                WHERE id = ? AND assigned_to = (SELECT id FROM admins WHERE telegram_id = ?)
            ''', (status, status, task_id, admin_id))
            
            self.conn.commit()
            success = cursor.rowcount > 0
            
            if success:
                logger.info(f"✅ Статус задачи #{task_id} обновлен на '{status}'")
            else:
                logger.warning(f"⚠️ Не удалось обновить статус задачи #{task_id}")
            
            return success
        except Exception as e:
            logger.error(f"❌ Ошибка обновления задачи: {e}")
            self.conn.rollback()
            return False
    
    # ==================== МЕТОДЫ ДЛЯ РАБОТЫ С КОМАНДАМИ ====================
    
    def create_team(self, name: str, description: str = "", 
                   leader_id: Optional[int] = None) -> Optional[int]:
        """Создать новую команду"""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO teams (name, description, leader_id)
                VALUES (?, ?, ?)
            ''', (name, description, leader_id))
            
            team_id = cursor.lastrowid
            
            # Если указан лидер, добавляем его в команду
            if leader_id:
                self.add_team_member(team_id, leader_id, 'leader')
            
            self.conn.commit()
            logger.info(f"✅ Создана команда #{team_id}: '{name}'")
            return team_id
        except Exception as e:
            logger.error(f"❌ Ошибка создания команды: {e}")
            self.conn.rollback()
            return None
    
    def add_team_member(self, team_id: int, admin_id: int, role: str = 'member') -> bool:
        """Добавить участника в команду"""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO team_members (team_id, admin_id, role)
                VALUES (?, ?, ?)
            ''', (team_id, admin_id, role))
            
            self.conn.commit()
            logger.info(f"✅ Участник {admin_id} добавлен в команду #{team_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления участника: {e}")
            self.conn.rollback()
            return False
    
    def get_team_members(self, team_id: int) -> List[Dict]:
        """Получить участников команды"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT a.telegram_id, a.username, tm.role
            FROM team_members tm
            JOIN admins a ON tm.admin_id = a.id
            WHERE tm.team_id = ?
            ORDER BY 
                CASE tm.role 
                    WHEN 'leader' THEN 1
                    WHEN 'deputy' THEN 2
                    ELSE 3
                END
        ''', (team_id,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_user_teams(self, admin_id: int) -> List[Dict]:
        """Получить команды пользователя"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT t.*, tm.role
            FROM teams t
            JOIN team_members tm ON t.id = tm.team_id
            WHERE tm.admin_id = ?
            ORDER BY t.created_at DESC
        ''', (admin_id,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    # ==================== МЕТОДЫ ДЛЯ РАБОТЫ С ЦИТАТАМИ ====================
    
    def get_random_quote(self, category: Optional[str] = None) -> Optional[Dict]:
        """Получить случайную цитату"""
        cursor = self.conn.cursor()
        
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
            self.conn.commit()
            
            return dict(row)
        return None
    
    def add_quote(self, text: str, author: str = "", category: str = "general", 
                 created_by: Optional[int] = None) -> bool:
        """Добавить новую цитату"""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO quotes (text, author, category, created_by)
                VALUES (?, ?, ?, ?)
            ''', (text, author, category, created_by))
            
            self.conn.commit()
            logger.info(f"✅ Добавлена новая цитата в категорию '{category}'")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления цитаты: {e}")
            self.conn.rollback()
            return False
    
    def close(self):
        """Закрыть соединение с БД"""
        self.conn.close()
        logger.info("✅ Соединение с БД закрыто")