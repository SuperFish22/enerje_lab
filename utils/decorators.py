# utils/decorators.py
import logging
from functools import wraps
import time

logger = logging.getLogger(__name__)

# Импортируем config
try:
    from config import config
    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False
    logger.warning("Config module not found, admin checks disabled")

def admin_required(func):
    """Декоратор для проверки прав администратора"""
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        if not HAS_CONFIG:
            return await func(update, context, *args, **kwargs)
        
        user_id = update.effective_user.id
        
        if user_id not in config.ADMIN_IDS:
            await update.message.reply_text("⛔ Доступ запрещен.")
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapper

def handle_errors(func):
    """Декоратор для обработки ошибок"""
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        try:
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка в {func.__name__}: {e}")
            try:
                await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")
            except:
                pass
    return wrapper