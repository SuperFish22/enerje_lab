#!/usr/bin/env python3
"""
Telegram бот для анонимной обратной связи
"""

import logging
import sys
import os
from datetime import datetime
from typing import Optional

# Добавляем путь для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from telegram.error import NetworkError

from config import config
from database import Database

# ==================== ИМПОРТЫ ДЛЯ МОДУЛЕЙ ====================

# Пытаемся импортировать модуль задач
try:
    from handlers.task_handlers import register as register_task_handlers
    TASKS_AVAILABLE = True
except ImportError:
    register_task_handlers = None
    TASKS_AVAILABLE = False
    print("⚠️ Модуль задач не найден. Команды /tasks, /all и другие будут недоступны.")

# Пытаемся импортировать модуль упоминаний
try:
    from services.mention_service import MentionService
    MENTION_SERVICE_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Модуль упоминаний не найден: {e}")
    MENTION_SERVICE_AVAILABLE = False
    # Создаем заглушку
    class MentionServiceStub:
        def __init__(self, db):
            pass
        def register_for_mentions(self, *args, **kwargs):
            return False
        def get_mention_users(self, *args, **kwargs):
            return []
        def is_user_registered(self, *args, **kwargs):
            return False
    
    MentionService = MentionServiceStub

# ==================== КОНЕЦ ИМПОРТОВ ====================

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, config.LOG_LEVEL),
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация БД
db = Database()

# Состояния для ConversationHandler
SELECTING_CATEGORY, WAITING_MESSAGE = range(2)

class FeedbackBot:
    def __init__(self):
        self.application = Application.builder().token(config.BOT_TOKEN).build()
        
        # Инициализируем сервис упоминаний
        if MENTION_SERVICE_AVAILABLE:
            self.mention_service = MentionService(db)
            logger.info("✅ Сервис упоминаний загружен")
        else:
            self.mention_service = MentionService(db)  # Заглушка
            logger.warning("⚠️ Сервис упоминаний недоступен, используется заглушка")
        
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        
        # ОСНОВНЫЕ КОМАНДЫ (работают везде)
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CommandHandler("id", self.get_my_id))
        
        # КОМАНДЫ ТОЛЬКО ДЛЯ ЛИЧНЫХ СООБЩЕНИЙ
        self.application.add_handler(
            CommandHandler("send", self.send_start, filters.ChatType.PRIVATE)
        )
        self.application.add_handler(
            CommandHandler("my", self.my_messages, filters.ChatType.PRIVATE)
        )
        self.application.add_handler(
            CommandHandler("rules", self.rules, filters.ChatType.PRIVATE)
        )
        self.application.add_handler(
            CommandHandler("cancel", self.cancel, filters.ChatType.PRIVATE)
        )
        
        # АДМИНИСТРАТОРСКИЕ КОМАНДЫ
        self.application.add_handler(
            CommandHandler("admin", self.admin_panel, filters.ChatType.PRIVATE)
        )
        self.application.add_handler(
            CommandHandler("stats", self.stats, filters.ChatType.PRIVATE)
        )
        self.application.add_handler(
            CommandHandler("broadcast", self.broadcast, filters.ChatType.PRIVATE)
        )
        self.application.add_handler(
            CommandHandler("reply", self.admin_reply, filters.ChatType.PRIVATE)
        )
        
        # КОМАНДЫ ДЛЯ ГРУПП
        self.application.add_handler(
            CommandHandler("all", self.call_all_group, 
                          filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)
        )
        
        # ==================== КОМАНДЫ ДЛЯ УПОМИНАНИЙ ====================
        if MENTION_SERVICE_AVAILABLE:
            self.application.add_handler(
                CommandHandler("reg", self.register_for_mentions,
                              filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)
            )
            self.application.add_handler(
                CommandHandler("mention_list", self.mention_list,
                              filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)
            )
            logger.info("✅ Обработчики упоминаний зарегистрированы")
        else:
            # Заглушки для команд упоминаний
            async def mention_stub(update: Update, context: ContextTypes.DEFAULT_TYPE):
                await update.message.reply_text(
                    "⚠️ Модуль упоминаний недоступен.\n"
                    "Убедитесь, что создан файл services/mention_service.py"
                )
            
            self.application.add_handler(
                CommandHandler("reg", mention_stub,
                              filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)
            )
            self.application.add_handler(
                CommandHandler("mention_list", mention_stub,
                              filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)
            )
        
        # Регистрируем обработчики задач (если доступны)
        if TASKS_AVAILABLE and register_task_handlers:
            try:
                register_task_handlers(self.application, db)
                logger.info("✅ Обработчики задач зарегистрированы")
            except Exception as e:
                logger.error(f"❌ Ошибка регистрации обработчиков задач: {e}")
        else:
            # Заглушки для команд задач
            async def tasks_stub(update: Update, context: ContextTypes.DEFAULT_TYPE):
                await update.message.reply_text(
                    "📋 Модуль задач недоступен. Убедитесь, что созданы файлы:\n"
                    "• handlers/task_handlers.py\n"
                    "• services/task_service.py\n"
                    "• services/team_service.py\n"
                    "• services/quote_service.py\n"
                    "• utils/decorators.py"
                )
            
            self.application.add_handler(
                CommandHandler("tasks", tasks_stub, filters.ChatType.PRIVATE)
            )
            self.application.add_handler(
                CommandHandler("mytasks", tasks_stub, filters.ChatType.PRIVATE)
            )
        
        # Обработчики кнопок
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        # Conversation для отправки сообщения
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("send", self.send_start, filters.ChatType.PRIVATE)],
            states={
                SELECTING_CATEGORY: [
                    CallbackQueryHandler(self.category_selected, pattern='^cat_')
                ],
                WAITING_MESSAGE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_received),
                    CommandHandler("cancel", self.cancel)
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            per_message=True
        )
        self.application.add_handler(conv_handler)
        
        # Обработка обычных сообщений (только в ЛС)
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, 
                self.handle_message
            )
        )
    
    # ==================== МЕТОДЫ ДЛЯ УПОМИНАНИЙ ====================
    
    async def register_for_mentions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Зарегистрироваться для упоминаний (команда /reg)"""
        if not MENTION_SERVICE_AVAILABLE:
            await update.message.reply_text("❌ Модуль упоминаний недоступен")
            return
        
        chat = update.effective_chat
        user = update.effective_user
        
        # Проверяем, не зарегистрирован ли уже
        if self.mention_service.is_user_registered(chat.id, user.id):
            await update.message.reply_text(
                f"✅ @{user.username or user.first_name}, вы уже зарегистрированы!\n\n"
                f"Теперь вас будут упоминать в команде /all"
            )
            return
        
        success = self.mention_service.register_for_mentions(
            chat_id=chat.id,
            user_id=user.id,
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
        
        if success:
            await update.message.reply_text(
                f"✅ @{user.username or user.first_name}, вы зарегистрированы!\n\n"
                f"Теперь вас будут упоминать в команде /all"
            )
        else:
            await update.message.reply_text("❌ Ошибка регистрации")
    
    async def mention_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список зарегистрированных пользователей"""
        if not MENTION_SERVICE_AVAILABLE:
            await update.message.reply_text("❌ Модуль упоминаний недоступен")
            return
        
        chat = update.effective_chat
        users = self.mention_service.get_mention_users(chat.id)
        
        if not users:
            await update.message.reply_text(
                "📭 Пока никто не зарегистрирован для упоминаний.\n\n"
                "Чтобы зарегистрироваться: /reg"
            )
            return
        
        response = "📋 Зарегистрированные пользователи:\n\n"
        
        for i, user in enumerate(users[:50], 1):
            if user['username']:
                response += f"{i}. @{user['username']}\n"
            else:
                response += f"{i}. {user['first_name']}\n"
        
        if len(users) > 50:
            response += f"\n... и еще {len(users) - 50} пользователей"
        
        response += f"\n\nВсего: {len(users)} пользователей"
        response += "\n\nℹ️ Эти пользователи будут упомянуты в /all"
        
        await update.message.reply_text(response)
    
    async def call_all_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /all с упоминанием зарегистрированных пользователей"""
        if not MENTION_SERVICE_AVAILABLE:
            # Безопасная версия без упоминаний
            chat = update.effective_chat
            
            if not context.args:
                await update.message.reply_text("Использование: /all <сообщение>")
                return
            
            message = ' '.join(context.args)
            user = update.effective_user
            
            response = f"📢 {message}\n\n👤 @{user.username or user.first_name}"
            await update.message.reply_text(response)
            return
        
        # Полная версия с упоминаниями
        chat = update.effective_chat
        
        if chat.type not in ['group', 'supergroup']:
            return
        
        if not context.args:
            await update.message.reply_text(
                "📢 Использование: /all <сообщение>\n\n"
                "Зарегистрируйтесь для упоминаний: /reg\n"
                "Список зарегистрированных: /mention_list"
            )
            return
        
        message = ' '.join(context.args)
        user = update.effective_user
        
        # Автоматически регистрируем пользователя, если он не зарегистрирован
        if not self.mention_service.is_user_registered(chat.id, user.id):
            self.mention_service.register_for_mentions(
                chat_id=chat.id,
                user_id=user.id,
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name
            )
        
        # Получаем пользователей для упоминания
        mention_users = self.mention_service.get_mention_users(chat.id)
        
        # Всегда включаем того, кто вызвал команду
        caller_included = any(u['telegram_id'] == user.id for u in mention_users)
        if not caller_included:
            mention_users.append({
                'telegram_id': user.id,
                'username': user.username,
                'first_name': user.first_name
            })
        
        if len(mention_users) == 1:
            # Только тот, кто вызвал команду
            response = f"📢 {message}\n\n👤 @{user.username or user.first_name}"
            await update.message.reply_text(response)
            return
        
        # Формируем упоминания (ограничим 15 пользователями)
        mentions = []
        for u in mention_users[:15]:
            if u['username']:
                mentions.append(f"@{u['username']}")
            else:
                mentions.append(f"[{u['first_name']}](tg://user?id={u['telegram_id']})")
        
        # Основное сообщение
        response = f"📢 ВНИМАНИЕ!\n\n"
        
        # Добавляем упоминания
        if mentions:
            response += " ".join(mentions) + "\n\n"
        
        response += f"💬 {message}\n\n👤 Сообщение от: @{user.username or user.first_name}"
        
        # Если много пользователей, добавляем информацию
        if len(mention_users) > 15:
            response += f"\n\n🔔 Упомянуто: {len(mentions)} из {len(mention_users)} пользователей"
        
        # Определяем parse_mode
        parse_mode = 'Markdown' if any('tg://user' in m for m in mentions) else None
        
        await update.message.reply_text(response, parse_mode=parse_mode)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        chat = update.effective_chat
        user = update.effective_user
        
        # Проверяем тип чата
        if chat.type in ['group', 'supergroup']:
            welcome_text = f"👋 Привет, участники {chat.title or 'группы'}!\n\n" \
                   f"Я бот для обратной связи и управления задачами.\n\n" \
                   f"📋 Доступные команды в группе:\n" \
                   f"/all <сообщение> - Призвать всех участников\n" \
                   f"/help - Помощь по командам\n" \
                   f"/id - Узнать ID группы\n\n" \
                   f"💬 Для полного функционала:\n" \
                   f"Напишите мне в личные сообщения: @{context.bot.username}"
            await update.message.reply_text(welcome_text)
            return
        
        # Код для личных сообщений
        try:
            db.add_user(
                user.id,
                user.username,
                user.first_name,
                user.last_name
            )
        except Exception as e:
            if "забанен" in str(e):
                await update.message.reply_text(
                    "🚫 Вы забанены и не можете использовать бота."
                )
                return
        
        # Добавляем кнопку для быстрого получения ID
        keyboard = [
            [InlineKeyboardButton("🆔 Узнать мой ID", callback_data="get_my_id")]
        ]
        
        await update.message.reply_text(
            config.WELCOME_MESSAGE + "\n\n"
            "📋 Доступные команды:\n"
            "/send - Отправить обращение\n"
            "/my - Мои обращения\n"
            "/id - Узнать свой ID\n"
            "/rules - Правила\n"
            "/help - Помощь\n\n"
            "💬 Просто напишите сообщение, и оно будет отправлено анонимно!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def call_all_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /all с упоминанием зарегистрированных пользователей"""
        if not MENTION_SERVICE_AVAILABLE:
            # Безопасная версия без упоминаний
            chat = update.effective_chat
            
            if not context.args:
                await update.message.reply_text("Использование: /all <сообщение>")
                return
            
            message = ' '.join(context.args)
            user = update.effective_user
            
            response = f"📢 {message}\n\n👤 @{user.username or user.first_name}"
            await update.message.reply_text(response)
            return
        
        # Полная версия с упоминаниями
        chat = update.effective_chat
        
        if chat.type not in ['group', 'supergroup']:
            return
        
        if not context.args:
            await update.message.reply_text(
                "📢 Использование: /all <сообщение>\n\n"
                "Зарегистрируйтесь для упоминаний: /reg\n"
                "Список зарегистрированных: /mention_list"
            )
            return
        
        message = ' '.join(context.args)
        user = update.effective_user
        
        # Используем метод из mention_service, а не из FeedbackBot
        if not self.mention_service.is_user_registered(chat.id, user.id):
            self.mention_service.register_for_mentions(
                chat_id=chat.id,
                user_id=user.id,
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name
            )
        
        # Получаем пользователей для упоминания
        mention_users = self.mention_service.get_mention_users(chat.id)
        
        # Всегда включаем того, кто вызвал команду
        caller_included = any(u['telegram_id'] == user.id for u in mention_users)
        if not caller_included:
            mention_users.append({
                'telegram_id': user.id,
                'username': user.username,
                'first_name': user.first_name
            })
        
        if len(mention_users) == 1:
            # Только тот, кто вызвал команду
            response = f"📢 {message}\n\n👤 @{user.username or user.first_name}"
            await update.message.reply_text(response)
            return
        
        # Формируем упоминания (ограничим 15 пользователями)
        mentions = []
        for u in mention_users[:15]:
            if u['username']:
                mentions.append(f"@{u['username']}")
            else:
                mentions.append(f"[{u['first_name']}](tg://user?id={u['telegram_id']})")
        
        # Основное сообщение
        response = f"📢 ВНИМАНИЕ!\n\n"
        
        # Добавляем упоминания
        if mentions:
            response += " ".join(mentions) + "\n\n"
        
        response += f"💬 {message}\n\n👤 Сообщение от: @{user.username or user.first_name}"
        
        # Если много пользователей, добавляем информацию
        if len(mention_users) > 15:
            response += f"\n\n🔔 Упомянуто: {len(mentions)} из {len(mention_users)} пользователей"
        
        # Определяем parse_mode
        parse_mode = 'Markdown' if any('tg://user' in m for m in mentions) else None
        
        await update.message.reply_text(response, parse_mode=parse_mode)

    
        
    async def mention_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Упомянуть всех зарегистрированных (только для админов)"""
        user = update.effective_user
        
        if user.id not in config.ADMIN_IDS:
            await update.message.reply_text("⛔ Только для администраторов")
            return
        
        chat = update.effective_chat
        
        if not context.args:
            await update.message.reply_text("Использование: /mention_all <сообщение>")
            return
        
        message = ' '.join(context.args)
        users = self.mention_service.get_mention_users(chat.id)
        
        if not users:
            await update.message.reply_text("❌ Нет зарегистрированных пользователей")
            return
    
    async def get_my_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать ID пользователя или группы"""
        chat = update.effective_chat
        user = update.effective_user
        
        if chat.type in ['group', 'supergroup']:
            # Информация о группе
            response = (
                f"📊 Информация о чате:\n\n"
                f"📛 Название: {chat.title}\n"
                f"🆔 ID группы: {chat.id}\n"
                f"👥 Тип: {chat.type}\n"
                f"👤 Ваш ID: {user.id}\n\n"
                f"💡 Использование:\n"
                f"ID группы может понадобиться для технической поддержки."
            )
        else:
            # Информация о пользователе
            response = (
                f"👤 Ваши данные:\n\n"
                f"🆔 ID: {user.id}\n"
                f"👤 Имя: {user.first_name or 'Не указано'}\n"
                f"📛 Фамилия: {user.last_name or 'Не указана'}\n"
                f"📱 Username: @{user.username or 'Не указан'}\n"
                f"🌐 Язык: {user.language_code or 'Не указан'}\n\n"
                f"💡 Ваш ID нужен для:\n"
                f"• Добавления вас как администратора\n"
                f"• Технической поддержки\n"
                f"• Идентификации в системе\n\n"
                f"📋 Как использовать:\n"
                f"1. Скопируйте ваш ID: {user.id}\n"
                f"2. Добавьте в файл .env как ADMIN_ID\n"
                f"3. Перезапустите бота"
            )
            
            # Добавляем кнопку для копирования (только в ЛС)
            keyboard = [
                [InlineKeyboardButton("📋 Скопировать ID", callback_data=f"copy_id_{user.id}")],
                [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_id")]
            ]
            
            await update.message.reply_text(
                response, 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        await update.message.reply_text(response)
    
    async def send_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало отправки сообщения с выбором категории"""
        if not config.ENABLE_CATEGORIES:
            context.user_data['category'] = 'general'
            await update.message.reply_text("✍️ Напишите ваше сообщение:")
            return WAITING_MESSAGE
        
        keyboard = [
            [
                InlineKeyboardButton("📝 Общее", callback_data="cat_general"),
                InlineKeyboardButton("🐛 Ошибка", callback_data="cat_bug"),
            ],
            [
                InlineKeyboardButton("💡 Предложение", callback_data="cat_suggestion"),
                InlineKeyboardButton("❓ Вопрос", callback_data="cat_question"),
            ],
            [
                InlineKeyboardButton("⚠️ Проблема", callback_data="cat_problem"),
                InlineKeyboardButton("⭐ Благодарность", callback_data="cat_thanks"),
            ]
        ]
        
        await update.message.reply_text(
            "📁 Выберите категорию обращения:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_CATEGORY
    
    async def category_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора категории"""
        query = update.callback_query
        await query.answer()
        
        category = query.data.replace('cat_', '')
        context.user_data['category'] = category
        
        category_names = {
            'general': 'Общее обращение',
            'bug': 'Сообщение об ошибке',
            'suggestion': 'Предложение',
            'question': 'Вопрос',
            'problem': 'Проблема',
            'thanks': 'Благодарность'
        }
        
        await query.edit_message_text(
            f"📁 Категория: {category_names.get(category, 'Общее')}\n\n"
            f"✍️ Теперь напишите ваше сообщение:"
        )
        return WAITING_MESSAGE
    
    async def message_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка полученного сообщения"""
        user = update.effective_user
        message_text = update.message.text
        category = context.user_data.get('category', 'general')
        
        # Проверка длины сообщения
        if len(message_text) > config.MAX_MESSAGE_LENGTH:
            await update.message.reply_text(
                f"❌ Сообщение слишком длинное. "
                f"Максимум {config.MAX_MESSAGE_LENGTH} символов."
            )
            return WAITING_MESSAGE
        
        # Сохранение в БД
        try:
            result = db.add_message(
                user.id,
                message_text,
                category,
                config.ENABLE_ANONYMITY
            )
            message_id = result['message_id']
        except Exception as e:
            logger.error(f"Ошибка сохранения сообщения: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при сохранении сообщения. "
                "Пожалуйста, попробуйте позже."
            )
            return ConversationHandler.END
        
        # Уведомление администраторов
        if config.ENABLE_ADMIN_NOTIFICATIONS:
            await self.notify_admins(context, message_id, user, message_text, category)
        
        # Ответ пользователю
        await update.message.reply_text(
            config.THANK_YOU_MESSAGE + f"\n\n"
            f"📝 Номер обращения: #{message_id}\n"
            f"📁 Категория: {self.get_category_name(category)}\n"
            f"⏳ Среднее время ответа: {config.RESPONSE_TIME_LIMIT} часов\n\n"
            f"Проверить статус: /my"
        )
        
        return ConversationHandler.END
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка обычных сообщений (без команды)"""
        user = update.effective_user
        
        # Проверяем, не является ли это ответом админа
        if context.user_data.get('waiting_admin_reply'):
            return
        
        # Проверка антиспама
        if config.ANTI_SPAM_ENABLED:
            if not self.check_spam_protection(user.id):
                await update.message.reply_text(
                    "⏳ Вы отправляете сообщения слишком часто. "
                    "Пожалуйста, подождите."
                )
                return
        
        # Сохраняем как общее обращение
        try:
            result = db.add_message(
                user.id,
                update.message.text,
                'general',
                config.ENABLE_ANONYMITY
            )
            message_id = result['message_id']
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            return
        
        # Уведомляем админов
        if config.ENABLE_ADMIN_NOTIFICATIONS:
            await self.notify_admins(
                context, 
                message_id, 
                user, 
                update.message.text, 
                'general'
            )
        
        await update.message.reply_text(
            f"✅ Сообщение отправлено! Номер: #{message_id}\n"
            f"Используйте /my для отслеживания статуса."
        )
    
    async def notify_admins(self, context, message_id, user, text, category):
        """Уведомить администраторов о новом сообщении"""
        category_name = self.get_category_name(category)
        
        message = (
            f"📨 Новое обращение #{message_id}\n"
            f"📁 Категория: {category_name}\n"
            f"👤 От: {user.first_name or 'Пользователь'}"
            f"{' (@' + user.username + ')' if user.username else ''}\n"
            f"🆔 ID: {user.id}\n"
            f"🕒 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"💬 Сообщение:\n{text[:500]}"
            f"{'...' if len(text) > 500 else ''}\n\n"
            f"📎 Для ответа используйте: /reply {message_id} ваш ответ"
        )
        
        for admin_id in config.ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=message
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")
    
    async def admin_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ответ администратора на сообщение"""
        user = update.effective_user
        
        if user.id not in config.ADMIN_IDS:
            await update.message.reply_text("⛔ Доступ запрещен.")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "Использование: /reply <номер_сообщения> <текст ответа>\n\n"
                "Пример: /reply 15 Спасибо за обращение!"
            )
            return
        
        try:
            message_id = int(context.args[0])
            reply_text = ' '.join(context.args[1:])
            
            # Получаем информацию о сообщении
            cursor = db.conn.cursor()
            cursor.execute('''
                SELECT user_id FROM messages WHERE id = ?
            ''', (message_id,))
            result = cursor.fetchone()
            
            if not result:
                await update.message.reply_text("❌ Сообщение не найдено!")
                return
            
            # Добавляем ответ в БД
            success = db.add_reply(message_id, user.id, reply_text)
            
            if not success:
                await update.message.reply_text("❌ Ошибка при сохранении ответа!")
                return
            
            # Получаем ID пользователя для отправки ответа
            cursor.execute('''
                SELECT telegram_id FROM users WHERE id = ?
            ''', (result['user_id'],))
            user_result = cursor.fetchone()
            
            if user_result:
                # Отправляем ответ пользователю
                await context.bot.send_message(
                    chat_id=user_result['telegram_id'],
                    text=f"📬 Ответ на ваше обращение #{message_id}\n\n"
                         f"{reply_text}\n\n"
                         f"💬 Чтобы ответить, просто напишите новое сообщение."
                )
            
            await update.message.reply_text(f"✅ Ответ на обращение #{message_id} отправлен!")
            
        except ValueError:
            await update.message.reply_text("❌ Неверный формат номера сообщения!")
        except Exception as e:
            logger.error(f"Ошибка при отправке ответа: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def my_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать сообщения пользователя"""
        user = update.effective_user
        messages = db.get_user_messages(user.id)
        
        if not messages:
            await update.message.reply_text(
                "📭 У вас пока нет отправленных обращений.\n"
                "Используйте /send чтобы отправить первое сообщение."
            )
            return
        
        response = "📋 Ваши обращения\n\n"
        
        for msg in messages[:10]:  # Показываем последние 10
            status_icon = "🆕" if msg['status'] == 'new' else "✅"
            status_text = "Новое" if msg['status'] == 'new' else "Отвечено"
            
            response += (
                f"#{msg['id']} {status_icon} {status_text}\n"
                f"📁 {self.get_category_name(msg['category'])}\n"
                f"📅 {msg['created_at'][:10]}\n"
                f"💬 {msg['text'][:50]}...\n"
            )
            
            if msg['reply_text']:
                response += f"📬 Ответ: {msg['reply_text'][:50]}...\n"
            
            response += "─" * 30 + "\n"
        
        if len(messages) > 10:
            response += f"\nПоказано 10 из {len(messages)} обращений"
        
        await update.message.reply_text(response)
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Панель администратора"""
        user = update.effective_user
        
        if user.id not in config.ADMIN_IDS:
            await update.message.reply_text("⛔ Доступ запрещен.")
            return
        
        stats = db.get_stats(7)
        new_messages = len(db.get_new_messages())
        
        keyboard = [
            [
                InlineKeyboardButton("📨 Новые", callback_data="admin_new"),
                InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
            ],
            [
                InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings"),
            ]
        ]
        
        response = (
            f"👑 Панель администратора\n\n"
            f"📈 За 7 дней:\n"
            f"• Сообщений: {stats.get('total_messages', 0)}\n"
            f"• Новых: {stats.get('new_messages', 0)}\n"
            f"• Отвечено: {stats.get('replied_messages', 0)}\n"
            f"• Среднее время ответа: {stats.get('avg_response_time', 0):.1f} мин\n\n"
            f"🆕 Сейчас:\n"
            f"• Ожидают ответа: {new_messages}\n\n"
            f"Выберите действие:"
        )
        
        await update.message.reply_text(
            response,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику"""
        user = update.effective_user
        
        if user.id not in config.ADMIN_IDS:
            await update.message.reply_text("⛔ Доступ запрещен.")
            return
        
        stats = db.get_stats(30)
        
        response = (
            f"📊 Статистика за 30 дней\n\n"
            f"📨 Всего сообщений: {stats.get('total_messages', 0)}\n"
            f"🆕 Новых: {stats.get('new_messages', 0)}\n"
            f"✅ Отвечено: {stats.get('replied_messages', 0)}\n"
            f"👥 Уникальных пользователей: {stats.get('unique_users', 0)}\n"
            f"⏱️ Среднее время ответа: {stats.get('avg_response_time', 0):.1f} мин\n\n"
            f"📈 График активности:\n"
        )
        
        # Добавляем последние 7 дней
        for day in stats.get('daily', [])[:7]:
            response += (
                f"{day['day']}: {day['messages']} сообщ., "
                f"{day['replied']} ответов\n"
            )
        
        await update.message.reply_text(response)
    
    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Рассылка сообщения"""
        user = update.effective_user
        
        if user.id not in config.ADMIN_IDS:
            await update.message.reply_text("⛔ Доступ запрещен.")
            return
        
        if not context.args:
            await update.message.reply_text("Использование: /broadcast <текст рассылки>")
            return
        
        broadcast_text = ' '.join(context.args)
        await update.message.reply_text(
            f"Рассылка начата...\n\nТекст: {broadcast_text[:100]}..."
        )
        
        # Здесь должна быть реализация рассылки
        # Для этого нужно хранить всех пользователей в БД
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь"""
        chat = update.effective_chat
        
        if chat.type in ['group', 'supergroup']:
            help_text = (
                "📋 Помощь по использованию бота в группе:\n\n"
                "👥 Доступные команды:\n"
                "/all <сообщение> - Призвать всех участников\n"
                "/help - Эта справка\n"
                "/id - Узнать ID группы\n\n"
                "💬 Для полного функционала:\n"
                f"Напишите мне в личные сообщения: @{context.bot.username}"
            )
        else:
            help_text = (
                "❓ Помощь по использованию бота:\n\n"
                "📨 Отправка сообщений:\n"
                "• Используйте /send для отправки с выбором категории\n"
                "• Или просто напишите сообщение - оно отправится как общее\n\n"
                "📋 Мои сообщения:\n"
                "• /my - история ваших обращений и статусы\n"
                "• /id - узнать свой Telegram ID\n\n"
                "👑 Для администраторов:\n"
                "• /admin - панель управления\n"
                "• /stats - статистика\n"
                "• /broadcast - рассылка\n"
                "• /reply - ответить на обращение\n\n"
                "📜 Правила:\n"
                "• /rules - правила использования бота\n\n"
                f"⚙️ Настройки бота:\n"
                f"• Анонимность: {'Включена' if config.ENABLE_ANONYMITY else 'Выключена'}\n"
                f"• Категории: {'Включены' if config.ENABLE_CATEGORIES else 'Выключены'}\n"
                f"• Время ответа: до {config.RESPONSE_TIME_LIMIT} часов"
            )
        
        await update.message.reply_text(help_text)
    
    async def rules(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Правила использования"""
        await update.message.reply_text(config.RULES_MESSAGE)
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == 'admin_new':
            await self.show_new_messages(query)
        elif data == 'admin_stats':
            await self.show_admin_stats(query)
        elif data == 'get_my_id':
            # Вызываем команду /id через callback
            user = query.from_user
            await query.message.reply_text(
                f"🆔 Ваш Telegram ID: {user.id}\n\n"
                f"📋 Для администратора:\n"
                f"Добавьте этот ID в файл .env:\n"
                f"ADMIN_IDS={user.id}"
            )
        elif data.startswith('copy_id_'):
            user_id = data.replace('copy_id_', '')
            await query.edit_message_text(
                f"✅ ID {user_id} скопирован!\n\n"
                f"Вставьте его в файл .env:\n"
                f"ADMIN_IDS={user_id}\n"
                f"и перезапустите бота."
            )
        elif data == 'refresh_id':
            user = query.from_user
            await query.edit_message_text(
                f"🆔 Ваш ID: {user.id}\n"
                f"👤 Имя: {user.first_name or 'Не указано'}"
            )
        elif data in ['task_create', 'task_my', 'task_team', 'task_all', 'task_overdue', 'task_motivate']:
            # Обработка кнопок задач (если модуль не загружен)
            if not TASKS_AVAILABLE:
                await query.answer("⚠️ Модуль задач не загружен", show_alert=True)
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена текущего действия"""
        await update.message.reply_text("❌ Действие отменено.")
        return ConversationHandler.END
    
    def get_category_name(self, category):
        """Получить название категории"""
        categories = {
            'general': 'Общее',
            'bug': 'Ошибка',
            'suggestion': 'Предложение',
            'question': 'Вопрос',
            'problem': 'Проблема',
            'thanks': 'Благодарность'
        }
        return categories.get(category, 'Общее')
    
    def check_spam_protection(self, user_id):
        """Проверка защиты от спама"""
        # Здесь можно реализовать проверку частоты сообщений
        # Пока возвращаем True для простоты
        return True
    
    async def show_new_messages(self, query):
        """Показать новые сообщения админу"""
        messages = db.get_new_messages(10)
        
        if not messages:
            await query.edit_message_text("📭 Новых сообщений нет!")
            return
        
        response = "📨 Новые сообщения\n\n"
        
        for msg in messages:
            response += (
                f"#{msg['id']} - {self.get_category_name(msg['category'])}\n"
                f"👤 {msg['first_name'] or 'Пользователь'}\n"
                f"🕒 {msg['created_at'][:16]}\n"
                f"💬 {msg['text'][:100]}...\n"
                f"📎 Для ответа: /reply {msg['id']} ваш текст\n"
                f"─" * 30 + "\n"
            )
        
        await query.edit_message_text(response)
    
    async def show_admin_stats(self, query):
        """Показать статистику админу"""
        stats = db.get_stats(7)
        
        response = (
            f"📊 Статистика за 7 дней\n\n"
            f"📨 Сообщений: {stats.get('total_messages', 0)}\n"
            f"🆕 Новых: {stats.get('new_messages', 0)}\n"
            f"✅ Отвечено: {stats.get('replied_messages', 0)}\n"
            f"⏱️ Среднее время: {stats.get('avg_response_time', 0):.1f} мин"
        )
        
        await query.edit_message_text(response)
    
    def run(self):
        """Запустить бота"""
        if not config.validate():
            logger.error("Неверная конфигурация. Завершение работы.")
            return
        
        logger.info(f"Запуск бота {config.BOT_NAME}...")
        logger.info(f"Админы: {config.ADMIN_IDS}")
        
        try:
            self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
        except KeyboardInterrupt:
            logger.info("Бот остановлен пользователем")
        except NetworkError as e:
            logger.error(f"Сетевая ошибка: {e}")
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)

def main():
    """Основная функция"""
    bot = FeedbackBot()
    bot.run()
    db.close()

if __name__ == '__main__':
    main()