"""
Конфигурация бота из переменных окружения
"""

import os
from dotenv import load_dotenv
from typing import List, Optional

# Загружаем переменные окружения
load_dotenv()

class Config:
    """Класс конфигурации приложения"""
    
    # Telegram Bot
    BOT_TOKEN: str = os.getenv('BOT_TOKEN', '')
    BOT_NAME: str = os.getenv('BOT_NAME', 'Feedback Bot')
    
    # Администраторы
    ADMIN_IDS: List[int] = [
        int(admin_id.strip()) 
        for admin_id in os.getenv('ADMIN_IDS', '').split(',') 
        if admin_id.strip().isdigit()
    ]
    
    # База данных
    DB_TYPE: str = os.getenv('DB_TYPE', 'sqlite').lower()
    DB_NAME: str = os.getenv('DB_NAME', 'feedback_bot.db')
    
    # Для других БД (опционально)
    DB_HOST: Optional[str] = os.getenv('DB_HOST')
    DB_PORT: Optional[int] = int(os.getenv('DB_PORT', '5432')) if os.getenv('DB_PORT') else None
    DB_USER: Optional[str] = os.getenv('DB_USER')
    DB_PASSWORD: Optional[str] = os.getenv('DB_PASSWORD')
    
    # Настройки бота
    RESPONSE_TIME_LIMIT: int = int(os.getenv('RESPONSE_TIME_LIMIT', '72'))
    MAX_MESSAGE_LENGTH: int = int(os.getenv('MAX_MESSAGE_LENGTH', '4000'))
    AUTO_DELETE_DAYS: int = int(os.getenv('AUTO_DELETE_DAYS', '90'))
    
    # Логирование
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO').upper()
    ENABLE_ADMIN_NOTIFICATIONS: bool = os.getenv('ENABLE_ADMIN_NOTIFICATIONS', 'true').lower() == 'true'
    CHECK_INTERVAL: int = int(os.getenv('CHECK_INTERVAL', '300'))
    
    # Безопасность
    ENCRYPTION_KEY: str = os.getenv('ENCRYPTION_KEY', 'default-encryption-key-32-chars')
    ANTI_SPAM_ENABLED: bool = os.getenv('ANTI_SPAM_ENABLED', 'true').lower() == 'true'
    MESSAGES_PER_MINUTE: int = int(os.getenv('MESSAGES_PER_MINUTE', '5'))
    
    # Сообщения
    WELCOME_MESSAGE: str = os.getenv(
        'WELCOME_MESSAGE', 
        '👋 Добро пожаловать в бот анонимной обратной связи!'
    )
    THANK_YOU_MESSAGE: str = os.getenv(
        'THANK_YOU_MESSAGE', 
        '✅ Ваше сообщение отправлено анонимно!'
    )
    RULES_MESSAGE: str = os.getenv(
        'RULES_MESSAGE', 
        '📜 Правила использования бота...'
    )
    
    # Флаги функций
    ENABLE_ANONYMITY: bool = os.getenv('ENABLE_ANONYMITY', 'true').lower() == 'true'
    ENABLE_CATEGORIES: bool = os.getenv('ENABLE_CATEGORIES', 'true').lower() == 'true'
    ENABLE_ATTACHMENTS: bool = os.getenv('ENABLE_ATTACHMENTS', 'false').lower() == 'true'
    ENABLE_RATING: bool = os.getenv('ENABLE_RATING', 'false').lower() == 'true'
    ENABLE_AUTO_REPLIES: bool = os.getenv('ENABLE_AUTO_REPLIES', 'false').lower() == 'true'
    
    # URL для веб-панели (если есть)
    WEBHOOK_URL: Optional[str] = os.getenv('WEBHOOK_URL')
    WEBHOOK_PORT: int = int(os.getenv('WEBHOOK_PORT', '8443'))
    
    @classmethod
    def validate(cls) -> bool:
        """Проверка обязательных настроек"""
        errors = []
        
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN не установлен")
        
        if not cls.ADMIN_IDS:
            errors.append("ADMIN_IDS не установлены")
        
        if not cls.ENCRYPTION_KEY or len(cls.ENCRYPTION_KEY) < 32:
            errors.append("ENCRYPTION_KEY должен быть не менее 32 символов")
        
        if errors:
            print("❌ Ошибки конфигурации:")
            for error in errors:
                print(f"   - {error}")
            return False
        
        print("✅ Конфигурация загружена успешно")
        print(f"   Бот: {cls.BOT_NAME}")
        print(f"   Админов: {len(cls.ADMIN_IDS)}")
        print(f"   БД: {cls.DB_TYPE}://{cls.DB_NAME}")
        
        return True
    
    @classmethod
    def get_database_url(cls) -> str:
        """Получить URL подключения к БД"""
        if cls.DB_TYPE == 'sqlite':
            return f"sqlite:///{cls.DB_NAME}"
        elif cls.DB_TYPE == 'postgresql':
            return f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
        elif cls.DB_TYPE == 'mysql':
            return f"mysql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
        else:
            raise ValueError(f"Неизвестный тип БД: {cls.DB_TYPE}")

# Создаем экземпляр конфигурации
config = Config()