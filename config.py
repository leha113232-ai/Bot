"""
NetErrror — конфигурация проекта.

Все значения можно задавать через переменные окружения (.env / export),
либо менять напрямую здесь. Не храните боевой токен в репозитории.
"""
import os


def _get_int_list(value: str) -> list[int]:
    return [int(x.strip()) for x in value.split(",") if x.strip()]


# ────────────────────────────── ОСНОВНОЕ ──────────────────────────────
# Токен бота от @BotFather
BOT_TOKEN = "8665885053:AAEJx5vbiyiXa0YfTupCA5vK4cnL1pXE_4I"

ADMIN_IDS = [5561036312]

PRIVATE_CHAT_ID = -1003760376758

ANNOUNCE_CHAT_IDS = [PRIVATE_CHAT_ID]

CRYPTO_BOT_TOKEN = "579872:AA7Tk9nXTA5iFfVEEiEuOxIJwtoq4FujM7Q"

SUPPORT_USERNAME = "drissg"
# Приветственное изображение: URL (https://...) ИЛИ локальный путь (welcome.jpg).
# Оставьте пустым, чтобы отправлять только текст.
WELCOME_IMAGE = "welcome.jpg"

# Путь к базе данных SQLite
DB_PATH = os.getenv("DB_PATH", "neterror.db")

# Как часто фоновый воркер проверяет подписки (в секундах). 86400 = раз в сутки.
SUB_CHECK_INTERVAL = int(os.getenv("SUB_CHECK_INTERVAL", "86400"))


# ────────────────────────────── ТАРИФЫ ──────────────────────────────
# days = None означает тариф "Навсегда".
TARIFFS: dict[str, dict] = {
    "1m": {"title": "1 месяц", "price": 5, "days": 30},
    "3m": {"title": "3 месяца", "price": 10, "days": 90},
    "6m": {"title": "6 месяцев", "price": 18, "days": 180},
    "forever": {"title": "Навсегда", "price": 150, "days": None},
}
