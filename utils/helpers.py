import re

def escape_markdown(text: str) -> str:
    """
    Экранировать специальные символы MarkdownV2
    """
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def format_for_markdown(text: str) -> str:
    """
    Подготовить текст для отправки с Markdown
    """
    # Экранируем все специальные символы
    text = escape_markdown(text)
    
    # Сохраняем эмодзи и базовое форматирование
    # Можно добавить звездочки для жирного текста
    # например: *текст* будет жирным
    return text