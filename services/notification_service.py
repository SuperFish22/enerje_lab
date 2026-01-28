# services/notification_service.py
import asyncio
from datetime import datetime, timedelta

class NotificationService:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.task_service = TaskService(db)
    
    async def check_overdue_tasks(self):
        """Проверка просроченных задач"""
        overdue_tasks = self.task_service.get_overdue_tasks()
        
        for task in overdue_tasks:
            if task.assigned_to:
                try:
                    await self.bot.send_message(
                        chat_id=task.assigned_to,
                        text=f"🚨 *ЗАДАЧА ПРОСРОЧЕНА!*\n\n"
                             f"*{task.title}*\n"
                             f"ID: #{task.id}\n"
                             f"Дедлайн: {task.deadline.strftime('%d.%m.%Y %H:%M')}\n\n"
                             f"Срочно обновите статус!",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление: {e}")
    
    async def send_daily_digest(self):
        """Ежедневный дайджест задач"""
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT telegram_id FROM admins')
        admins = cursor.fetchall()
        
        for admin in admins:
            user_id = admin['telegram_id']
            tasks = self.task_service.get_user_tasks(user_id)
            
            if tasks:
                today_tasks = [t for t in tasks if t.deadline and t.deadline.date() == datetime.now().date()]
                
                if today_tasks:
                    message = "📋 *Задачи на сегодня:*\n\n"
                    
                    for task in today_tasks:
                        message += f"• {task.title} (ID: {task.id})\n"
                    
                    try:
                        await self.bot.send_message(
                            chat_id=user_id,
                            text=message,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"Не удалось отправить дайджест: {e}")