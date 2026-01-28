import logging
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters

from utils.decorators import admin_required, handle_errors
from services.task_service import TaskService
from services.team_service import TeamService
from services.quote_service import QuoteService

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
TASK_TITLE, TASK_DESCRIPTION, TASK_ASSIGNEE, TASK_PRIORITY, TASK_DEADLINE = range(5)

class TaskHandlers:
    def __init__(self, db):
        self.db = db
        self.task_service = TaskService(db)
        self.team_service = TeamService(db)
        self.quote_service = QuoteService(db)
    
    @admin_required
    @handle_errors
    async def task_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню управления задачами"""
        keyboard = [
            [InlineKeyboardButton("📝 Создать задачу", callback_data="task_create")],
            [InlineKeyboardButton("📋 Мои задачи", callback_data="task_my")],
            [InlineKeyboardButton("👥 Задачи команды", callback_data="task_team")],
            [InlineKeyboardButton("📊 Все задачи", callback_data="task_all")],
            [InlineKeyboardButton("⏰ Просроченные", callback_data="task_overdue")],
            [InlineKeyboardButton("💡 Мотивация", callback_data="task_motivate")],
        ]
        
        await update.message.reply_text(
            "📋 *Управление задачами*\n\n"
            "Выберите действие:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    @admin_required
    @handle_errors
    async def create_task_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало создания задачи"""
        context.user_data['creating_task'] = True
        await update.message.reply_text("📝 Введите название задачи:")
        return TASK_TITLE
    
    @admin_required
    @handle_errors
    async def task_title_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение названия задачи"""
        context.user_data['task_title'] = update.message.text
        await update.message.reply_text("📄 Введите описание задачи:")
        return TASK_DESCRIPTION
    
    @admin_required
    @handle_errors
    async def task_description_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение описания задачи"""
        context.user_data['task_description'] = update.message.text
        
        # Получаем список администраторов для назначения
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT telegram_id, username FROM admins')
        admins = cursor.fetchall()
        
        keyboard = []
        for admin in admins:
            username = admin['username'] or f"ID: {admin['telegram_id']}"
            keyboard.append([
                InlineKeyboardButton(
                    f"👤 {username}", 
                    callback_data=f"assign_{admin['telegram_id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("❌ Не назначать", callback_data="assign_none")])
        
        await update.message.reply_text(
            "👥 Выберите исполнителя:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return TASK_ASSIGNEE
    
    @admin_required
    @handle_errors
    async def task_assignee_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор приоритета задачи"""
        query = update.callback_query
        await query.answer()
        
        data = query.data.replace('assign_', '')
        
        if data == 'none':
            context.user_data['task_assignee'] = None
        else:
            context.user_data['task_assignee'] = int(data)
        
        keyboard = [
            [
                InlineKeyboardButton("🔴 Критический", callback_data="priority_critical"),
                InlineKeyboardButton("🟠 Высокий", callback_data="priority_high"),
            ],
            [
                InlineKeyboardButton("🟡 Средний", callback_data="priority_medium"),
                InlineKeyboardButton("🟢 Низкий", callback_data="priority_low"),
            ],
            [InlineKeyboardButton("⏭️ Пропустить", callback_data="priority_skip")],
        ]
        
        await query.edit_message_text(
            "🎯 Выберите приоритет задачи:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return TASK_PRIORITY
    
    @admin_required
    @handle_errors
    async def task_priority_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор дедлайна"""
        query = update.callback_query
        await query.answer()
        
        data = query.data.replace('priority_', '')
        
        if data == 'skip':
            context.user_data['task_priority'] = 'medium'
            context.user_data['task_deadline'] = None
            return await self.finish_task_creation(update, context)
        
        context.user_data['task_priority'] = data
        
        keyboard = [
            [InlineKeyboardButton("📅 Сегодня", callback_data="deadline_today")],
            [InlineKeyboardButton("📅 Завтра", callback_data="deadline_tomorrow")],
            [InlineKeyboardButton("📅 Через 3 дня", callback_data="deadline_3days")],
            [InlineKeyboardButton("📅 Через неделю", callback_data="deadline_week")],
            [InlineKeyboardButton("⏭️ Без дедлайна", callback_data="deadline_none")],
        ]
        
        await query.edit_message_text(
            "⏰ Установите дедлайн:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return TASK_DEADLINE
    
    @admin_required
    @handle_errors
    async def task_deadline_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Завершение создания задачи"""
        query = update.callback_query
        await query.answer()
        
        data = query.data.replace('deadline_', '')
        
        deadline = None
        today = datetime.now()
        
        if data == 'today':
            deadline = today.replace(hour=23, minute=59, second=59)
        elif data == 'tomorrow':
            deadline = today + timedelta(days=1)
            deadline = deadline.replace(hour=23, minute=59, second=59)
        elif data == '3days':
            deadline = today + timedelta(days=3)
            deadline = deadline.replace(hour=23, minute=59, second=59)
        elif data == 'week':
            deadline = today + timedelta(days=7)
            deadline = deadline.replace(hour=23, minute=59, second=59)
        
        context.user_data['task_deadline'] = deadline
        
        return await self.finish_task_creation(update, context)
    
    @admin_required
    @handle_errors
    async def finish_task_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Завершение создания задачи и сохранение"""
        query = update.callback_query if update.callback_query else None
        
        # Получаем данные из context
        title = context.user_data.get('task_title', '')
        description = context.user_data.get('task_description', '')
        assignee = context.user_data.get('task_assignee')
        priority = context.user_data.get('task_priority', 'medium')
        deadline = context.user_data.get('task_deadline')
        
        user_id = update.effective_user.id
        
        # Создаем задачу
        task = self.task_service.create_task(
            title=title,
            description=description,
            created_by=user_id,
            assigned_to=assignee,
            priority=priority,
            deadline=deadline
        )
        
        if task:
            # Отправляем уведомление исполнителю
            if assignee:
                try:
                    await context.bot.send_message(
                        chat_id=assignee,
                        text=f"📋 *Новая задача #{task.id}*\n\n"
                             f"*{title}*\n\n"
                             f"{description}\n\n"
                             f"🎯 Приоритет: {priority}\n"
                             f"⏰ Дедлайн: {deadline.strftime('%d.%m.%Y') if deadline else 'Нет'}\n\n"
                             f"Для просмотра: /mytasks",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление исполнителю: {e}")
            
            message = (
                f"✅ *Задача создана!*\n\n"
                f"*#{task.id} {title}*\n\n"
                f"Исполнитель: {'Назначен' if assignee else 'Не назначен'}\n"
                f"Приоритет: {priority}\n"
                f"Дедлайн: {deadline.strftime('%d.%m.%Y %H:%M') if deadline else 'Нет'}"
            )
        else:
            message = "❌ Ошибка при создании задачи"
        
        if query:
            await query.edit_message_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
        
        # Очищаем данные
        for key in ['creating_task', 'task_title', 'task_description', 
                   'task_assignee', 'task_priority', 'task_deadline']:
            context.user_data.pop(key, None)
        
        return ConversationHandler.END
    
    @admin_required
    @handle_errors
    async def my_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать мои задачи"""
        user_id = update.effective_user.id
        
        # Получаем задачи пользователя
        tasks = self.task_service.get_user_tasks(user_id)
        
        if not tasks:
            await update.message.reply_text("📭 У вас нет назначенных задач.")
            return
        
        response = "📋 *Ваши задачи:*\n\n"
        
        for task in tasks:
            status_icons = {
                'new': '🆕',
                'in_progress': '🔄',
                'review': '👀',
                'completed': '✅',
                'cancelled': '❌'
            }
            
            priority_icons = {
                'critical': '🔴',
                'high': '🟠',
                'medium': '🟡',
                'low': '🟢'
            }
            
            deadline_text = ""
            if task.deadline:
                days_left = (task.deadline - datetime.now()).days
                if days_left < 0:
                    deadline_text = f"⏰ *ПРОСРОЧЕНО!*"
                elif days_left == 0:
                    deadline_text = f"⏰ *Сегодня!*"
                elif days_left == 1:
                    deadline_text = f"⏰ *Завтра*"
                else:
                    deadline_text = f"⏰ {task.deadline.strftime('%d.%m')} ({days_left} дн.)"
            
            response += (
                f"{priority_icons.get(task.priority, '📌')} *{task.title}*\n"
                f"{status_icons.get(task.status, '📝')} Статус: {task.status}\n"
                f"{deadline_text}\n"
                f"📄 {task.description[:50]}...\n"
                f"🆔 ID: {task.id} | 👤 Исполнитель: Вы\n"
                f"────────────────────\n"
            )
        
        keyboard = [
            [
                InlineKeyboardButton("🔄 В работе", callback_data="status_in_progress"),
                InlineKeyboardButton("👀 На проверку", callback_data="status_review"),
            ],
            [
                InlineKeyboardButton("✅ Завершить", callback_data="status_completed"),
                InlineKeyboardButton("❌ Отменить", callback_data="status_cancelled"),
            ],
            [InlineKeyboardButton("📝 Изменить статус задачи", callback_data="change_status_prompt")],
        ]
        
        await update.message.reply_text(
            response,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    @admin_required
    @handle_errors
    async def team_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать задачи команды"""
        user_id = update.effective_user.id
        
        # Получаем команды пользователя
        teams = self.team_service.get_user_teams(user_id)
        
        if not teams:
            await update.message.reply_text("👥 Вы не состоите ни в одной команде.")
            return
        
        response = "👥 *Задачи команд:*\n\n"
        
        for team in teams:
            # Получаем участников команды
            members = self.team_service.get_team_members(team['id'])
            member_ids = [m['telegram_id'] for m in members]
            
            # Получаем задачи для всех участников команды
            team_tasks = []
            for member_id in member_ids:
                tasks = self.task_service.get_user_tasks(member_id)
                for task in tasks:
                    if task.status != 'completed':
                        team_tasks.append((task, member_id))
            
            if team_tasks:
                response += f"*{team['name']}* ({len(team_tasks)} задач)\n"
                
                for task, assignee_id in team_tasks[:3]:  # Показываем только 3 задачи
                    response += f"  • {task.title} (ID: {task.id})\n"
                
                if len(team_tasks) > 3:
                    response += f"  ... и еще {len(team_tasks) - 3} задач\n"
                
                response += "\n"
        
        await update.message.reply_text(response, parse_mode='Markdown')
    
    @admin_required
    @handle_errors
    async def all_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать все задачи"""
        tasks = self.task_service.get_all_tasks()
        
        if not tasks:
            await update.message.reply_text("📭 Нет активных задач.")
            return
        
        response = "📊 *Все задачи:*\n\n"
        
        # Группируем по статусу
        tasks_by_status = {}
        for task in tasks:
            if task.status not in tasks_by_status:
                tasks_by_status[task.status] = []
            tasks_by_status[task.status].append(task)
        
        for status, status_tasks in tasks_by_status.items():
            status_text = {
                'new': '🆕 Новые',
                'in_progress': '🔄 В работе',
                'review': '👀 На проверке',
                'completed': '✅ Завершены',
                'cancelled': '❌ Отменены'
            }.get(status, status)
            
            response += f"*{status_text}* ({len(status_tasks)})\n"
            
            for task in status_tasks[:5]:  # Показываем по 5 задач каждого статуса
                response += f"  • #{task.id} {task.title}\n"
            
            if len(status_tasks) > 5:
                response += f"  ... и еще {len(status_tasks) - 5}\n"
            
            response += "\n"
        
        await update.message.reply_text(response, parse_mode='Markdown')
    
    @admin_required
    @handle_errors
    async def motivate_team(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отправить мотивационную цитату команде"""
        user_id = update.effective_user.id
        
        # Получаем случайную цитату
        quote = self.quote_service.get_random_quote()
        
        if not quote:
            await update.message.reply_text("❌ Нет доступных цитат.")
            return
        
        # Получаем команды пользователя
        teams = self.team_service.get_user_teams(user_id)
        
        if not teams:
            await update.message.reply_text("👥 Вы не состоите ни в одной команде.")
            return
        
        # Выбираем первую команду (можно добавить выбор)
        team = teams[0]
        
        # Получаем участников команды
        members = self.team_service.get_team_members(team['id'])
        
        if not members:
            await update.message.reply_text("👥 В команде нет участников.")
            return
        
        # Отправляем цитату всем участникам
        sent_count = 0
        for member in members:
            try:
                await context.bot.send_message(
                    chat_id=member['telegram_id'],
                    text=f"💫 *Мотивация от {update.effective_user.first_name}!*\n\n"
                         f"*{quote['text']}*\n\n"
                         f"_{quote['author'] or 'Аноним'}_\n\n"
                         f"#мотивация #{team['name'].lower().replace(' ', '_')}",
                    parse_mode='Markdown'
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Не удалось отправить цитату пользователю {member['telegram_id']}: {e}")
        
        await update.message.reply_text(
            f"✅ Мотивационная цитата отправлена {sent_count} участникам команды *{team['name']}*!",
            parse_mode='Markdown'
        )
    
    @admin_required
    @handle_errors
    async def call_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Общий призыв всех администраторов"""
        if not context.args:
            await update.message.reply_text("Использование: /all <сообщение>")
            return
        
        message = ' '.join(context.args)
        user = update.effective_user
        
        # Получаем всех администраторов
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT telegram_id FROM admins WHERE telegram_id != ?', (user.id,))
        admins = cursor.fetchall()
        
        if not admins:
            await update.message.reply_text("❌ Нет других администраторов.")
            return
        
        sent_count = 0
        for admin in admins:
            try:
                await context.bot.send_message(
                    chat_id=admin['telegram_id'],
                    text=f"📣 *ВНИМАНИЕ!*\n\n"
                         f"@{user.username or user.first_name} вызывает всех:\n\n"
                         f"*{message}*\n\n"
                         f"#all #призыв",
                    parse_mode='Markdown'
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Не удалось отправить призыв администратору {admin['telegram_id']}: {e}")
        
        await update.message.reply_text(
            f"📣 Призыв отправлен {sent_count} администраторам!",
            parse_mode='Markdown'
        )
    
    @admin_required
    @handle_errors
    async def create_team(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Создать новую команду"""
        if len(context.args) < 1:
            await update.message.reply_text("Использование: /createteam <название> [описание]")
            return
        
        team_name = context.args[0]
        description = ' '.join(context.args[1:]) if len(context.args) > 1 else ""
        
        user_id = update.effective_user.id
        
        # Создаем команду
        team_id = self.team_service.create_team(
            name=team_name,
            description=description,
            leader_id=user_id
        )
        
        if team_id:
            await update.message.reply_text(
                f"✅ Команда *{team_name}* создана!\n\n"
                f"Вы назначены лидером команды.\n"
                f"Добавьте участников: /addmember {team_id} <user_id>",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Ошибка при создании команды. Возможно, такое название уже существует.")
    
    @admin_required
    @handle_errors
    async def add_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить участника в команду"""
        if len(context.args) < 2:
            await update.message.reply_text("Использование: /addmember <id_команды> <id_пользователя> [роль]")
            return
        
        try:
            team_id = int(context.args[0])
            member_id = int(context.args[1])
            role = context.args[2] if len(context.args) > 2 else 'member'
            
            # Проверяем, что пользователь - лидер команды
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT leader_id FROM teams WHERE id = ?', (team_id,))
            team = cursor.fetchone()
            
            if not team:
                await update.message.reply_text("❌ Команда не найдена.")
                return
            
            if team['leader_id'] != update.effective_user.id:
                await update.message.reply_text("❌ Только лидер команды может добавлять участников.")
                return
            
            # Добавляем участника
            success = self.team_service.add_team_member(team_id, member_id, role)
            
            if success:
                # Получаем название команды
                cursor.execute('SELECT name FROM teams WHERE id = ?', (team_id,))
                team_name = cursor.fetchone()['name']
                
                # Уведомляем нового участника
                try:
                    await context.bot.send_message(
                        chat_id=member_id,
                        text=f"👥 *Вас добавили в команду!*\n\n"
                             f"Команда: *{team_name}*\n"
                             f"Роль: {role}\n"
                             f"Лидер: @{update.effective_user.username or update.effective_user.first_name}\n\n"
                             f"Просмотреть задачи команды: /teamtasks",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Не удалось уведомить нового участника: {e}")
                
                await update.message.reply_text(f"✅ Участник добавлен в команду *{team_name}*!")
            else:
                await update.message.reply_text("❌ Ошибка при добавлении участника.")
                
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID.")
        except Exception as e:
            logger.error(f"Ошибка в add_member: {e}")
            await update.message.reply_text("❌ Произошла ошибка.")
    
    @admin_required
    @handle_errors
    async def my_teams(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать мои команды"""
        user_id = update.effective_user.id
        teams = self.team_service.get_user_teams(user_id)
        
        if not teams:
            await update.message.reply_text("👥 Вы не состоите ни в одной команде.")
            return
        
        response = "👥 *Ваши команды:*\n\n"
        
        for team in teams:
            members = self.team_service.get_team_members(team['id'])
            
            response += (
                f"*{team['name']}*\n"
                f"Роль: {team['role']}\n"
                f"Участников: {len(members)}\n"
                f"ID команды: {team['id']}\n"
            )
            
            if team['description']:
                response += f"Описание: {team['description']}\n"
            
            response += "────────────────────\n"
        
        keyboard = [
            [InlineKeyboardButton("📋 Задачи команды", callback_data="team_tasks")],
            [InlineKeyboardButton("💡 Мотивировать", callback_data="motivate_team")],
            [InlineKeyboardButton("👥 Участники", callback_data="team_members")],
        ]
        
        await update.message.reply_text(
            response,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    @admin_required
    @handle_errors
    async def daily_motivation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ежедневная мотивационная рассылка"""
        # Получаем случайную цитату
        quote = self.quote_service.get_random_quote()
        
        if not quote:
            await update.message.reply_text("❌ Нет доступных цитат.")
            return
        
        # Получаем всех администраторов
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT telegram_id FROM admins')
        admins = cursor.fetchall()
        
        sent_count = 0
        for admin in admins:
            try:
                await context.bot.send_message(
                    chat_id=admin['telegram_id'],
                    text=f"🌅 *Доброе утро!*\n\n"
                         f"*Мотивация на сегодня:*\n\n"
                         f"_{quote['text']}_\n\n"
                         f"— {quote['author'] or 'Аноним'}\n\n"
                         f"#утро #мотивация #день",
                    parse_mode='Markdown'
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Не удалось отправить мотивацию администратору {admin['telegram_id']}: {e}")
        
        await update.message.reply_text(
            f"✅ Ежедневная мотивация отправлена {sent_count} администраторам!",
            parse_mode='Markdown'
        )

def register(app, db):
    """Регистрация обработчиков задач и команд"""
    handlers = TaskHandlers(db)
    
    # Регистрируем команды
    app.add_handler(CommandHandler("tasks", handlers.task_menu))
    app.add_handler(CommandHandler("mytasks", handlers.my_tasks))
    app.add_handler(CommandHandler("teamtasks", handlers.team_tasks))
    app.add_handler(CommandHandler("alltasks", handlers.all_tasks))
    app.add_handler(CommandHandler("all", handlers.call_all))
    app.add_handler(CommandHandler("createteam", handlers.create_team))
    app.add_handler(CommandHandler("addmember", handlers.add_member))
    app.add_handler(CommandHandler("myteams", handlers.my_teams))
    app.add_handler(CommandHandler("motivate", handlers.daily_motivation))
    
    # Conversation для создания задачи
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("newtask", handlers.create_task_start)],
        states={
            TASK_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.task_title_received)
            ],
            TASK_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.task_description_received)
            ],
            TASK_ASSIGNEE: [
                CallbackQueryHandler(handlers.task_assignee_selected, pattern='^assign_')
            ],
            TASK_PRIORITY: [
                CallbackQueryHandler(handlers.task_priority_selected, pattern='^priority_')
            ],
            TASK_DEADLINE: [
                CallbackQueryHandler(handlers.task_deadline_selected, pattern='^deadline_')
            ],
        },
        fallbacks=[CommandHandler("cancel", handlers.finish_task_creation)]
    )
    
    app.add_handler(conv_handler)
    
    # Обработчики кнопок
    app.add_handler(CallbackQueryHandler(handlers.motivate_team, pattern='^task_motivate$'))
    app.add_handler(CallbackQueryHandler(handlers.my_tasks, pattern='^task_my$'))
    app.add_handler(CallbackQueryHandler(handlers.team_tasks, pattern='^task_team$'))
    app.add_handler(CallbackQueryHandler(handlers.all_tasks, pattern='^task_all$'))