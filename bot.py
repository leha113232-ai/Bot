"""
NetErrror — точка входа.

Запуск:  python bot.py
Перед запуском заполните config.py (или переменные окружения):
  BOT_TOKEN, ADMIN_IDS, PRIVATE_CHAT_ID, SUPPORT_USERNAME
Бот должен быть АДМИНИСТРАТОРОМ приватного чата (право приглашать + банить).
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from database import init_db
from handlers import admin_router, payments_router, user_router
from utils import start_subscription_watcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("neterror.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("neterror")


async def main() -> None:
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        logger.error("Укажите BOT_TOKEN в config.py перед запуском.")
        return

    await init_db()
    logger.info("База данных инициализирована.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # порядок: пользовательские → платежи → админ
    dp.include_router(user_router)
    dp.include_router(payments_router)
    dp.include_router(admin_router)

    # фоновый контроль подписок
    start_subscription_watcher(bot)

    logger.info("NetErrror запущен. Polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger("neterror").info("Остановлено.")
