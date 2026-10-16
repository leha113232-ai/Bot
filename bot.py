import asyncio
import logging
import os
import time
import aiosqlite
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    FSInputFile,
    InputMediaPhoto,
    InputMediaVideo,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand,
    ChatMemberUpdated
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

dp = Dispatcher(storage=MemoryStorage())

DB_PATH = "subscriptions.db"
PRIVACY_POLICY_URL = "https://telegra.ph/Politika-konfidencialnosti-09-18-83"
USER_AGREEMENT_URL = "https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"
XROCKET_URL = getattr(config, "XROCKET_URL", "https://t.me/xrocket?start=sb_2Q3aHnZdGE5PoBV")
CRYPTO_URL = getattr(config, "CRYPTO_URL", "https://t.me/send?start=SBsUzHVcqIDCg2MWY6")

SUPPORT_PROFILE = f"https://t.me/{getattr(config, 'SUPPORT_USERNAME', 'drissg')}"
OWNER_PROFILE = f"https://t.me/{getattr(config, 'OWNER_USERNAME', 'm0ssveil')}"

# ID кастомных премиум-эмодзи
E_INVADER = "5337037846475720165"
E_ROCKET = "5372917041193828849"
E_CRYPTO = "5278544515072809442"
E_SBP = "5380011438108591402"
E_PROFILE = "5413656347889647017"
E_DOCS = "5436047047490815583"
E_CHECK = "5350819528945187024"
E_BELL = "5415880599783101138"
E_BACK = "5350474475567597579"
E_FLASH = "5436269857509229795"
E_WALLET = "5350504428669518983"
E_SKEPTIC = "5350313693466872934"

PLAN_ICONS = {
    "1m": "5350819528945187024",
    "3m": "5352827404681232272",
    "6m": "5436269857509229795",
    "1y": "5372917041193828849",
    "forever": "5337037846475720165"
}

SBP_PLANS = {}
for k, v in config.SBP_PLANS.items():
    plan_data = dict(v)
    plan_data["icon"] = PLAN_ICONS.get(k, E_FLASH)
    SBP_PLANS[k] = plan_data

reminder_messages = {}
reminder_tasks = {}
active_orders = {}


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                invite_link TEXT,
                expire_timestamp INTEGER,
                joined_via_bot INTEGER DEFAULT 0,
                warned_3d INTEGER DEFAULT 0,
                warned_1d INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
        """)
        await db.commit()


async def add_subscription(user_id: int, invite_link: str, days: int | None):
    expire_timestamp = int(time.time() + days * 86400) if days else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, invite_link, expire_timestamp, joined_via_bot, is_active)
            VALUES (?, ?, ?, 0, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                invite_link=excluded.invite_link,
                expire_timestamp=excluded.expire_timestamp,
                joined_via_bot=0,
                warned_3d=0,
                warned_1d=0,
                is_active=1
        """, (user_id, invite_link, expire_timestamp))
        await db.commit()


async def mark_user_joined(invite_link: str, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET joined_via_bot = 1 WHERE invite_link = ? OR user_id = ?
        """, (invite_link, user_id))
        await db.commit()


async def get_expiring_users():
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute("""
            SELECT user_id, expire_timestamp FROM users 
            WHERE is_active = 1 AND joined_via_bot = 1 AND expire_timestamp IS NOT NULL
            AND expire_timestamp - ? <= 259200 AND expire_timestamp - ? > 86400 AND warned_3d = 0
        """, (now, now))
        warn_3d = await cursor.fetchall()

        cursor = await db.execute("""
            SELECT user_id, expire_timestamp FROM users 
            WHERE is_active = 1 AND joined_via_bot = 1 AND expire_timestamp IS NOT NULL
            AND expire_timestamp - ? <= 86400 AND expire_timestamp - ? > 0 AND warned_1d = 0
        """, (now, now))
        warn_1d = await cursor.fetchall()

        cursor = await db.execute("""
            SELECT user_id FROM users 
            WHERE is_active = 1 AND joined_via_bot = 1 AND expire_timestamp IS NOT NULL
            AND expire_timestamp <= ?
        """, (now,))
        to_kick = await cursor.fetchall()

        return warn_3d, warn_1d, to_kick


async def set_warned(user_id: int, field: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {field} = 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def deactivate_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (user_id,))
        await db.commit()


async def create_platega_payment(amount: float, user_id: int, plan_key: str):
    headers = {
        "X-MerchantId": config.PLATEGA_MERCHANT_ID,
        "X-Secret": config.PLATEGA_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "paymentMethod": 2,
        "paymentDetails": {
            "amount": int(amount),
            "currency": "RUB"
        },
        "description": f"Подписка NetErrror Private {SBP_PLANS[plan_key]['label']} (ID: {user_id})",
        "return": "https://t.me/neterr0rer_bot",
        "failedUrl": "https://t.me/neterr0rer_bot"
    }

    url = f"{config.PLATEGA_API_URL}/transaction/process"
    fallback_url = f"{config.PLATEGA_API_URL}/v2/transaction/process"

    async with aiohttp.ClientSession() as session:
        for target_url in [url, fallback_url]:
            try:
                async with session.post(target_url, json=payload, headers=headers, timeout=8) as resp:
                    resp_text = await resp.text()
                    logger.info(f"Platega [{target_url}] Status: {resp.status} | Body: {resp_text}")

                    if resp.status in (200, 201):
                        data = await resp.json()
                        payment_url = (
                            data.get("redirect")
                            or data.get("redirectUrl")
                            or data.get("url")
                            or data.get("payment_url")
                            or (data.get("data") or {}).get("redirect")
                            or (data.get("data") or {}).get("url")
                        )
                        platega_id = (
                            data.get("transactionId")
                            or data.get("id")
                            or (data.get("data") or {}).get("id")
                        )
                        if payment_url:
                            return platega_id, payment_url, None

                    if resp.status != 404:
                        return None, None, f"{resp.status} - {resp_text[:140]}"
            except Exception as e:
                logger.error(f"Platega error {target_url}: {e}")
                return None, None, str(e)

    return None, None, "Не удалось сгенерировать ссылку"


async def check_platega_status(platega_id: str) -> bool:
    if not platega_id:
        return False
    url = f"{config.PLATEGA_API_URL}/transaction/{platega_id}"
    headers = {
        "X-MerchantId": config.PLATEGA_MERCHANT_ID,
        "X-Secret": config.PLATEGA_API_KEY
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=6) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    status = (
                        data.get("status")
                        or (data.get("data") or {}).get("status")
                        or ""
                    ).lower()
                    if status in ["paid", "success", "completed", "confirmed"]:
                        return True
    except Exception as e:
        logger.error(f"Ошибка проверки Platega {platega_id}: {e}")
    return False


class PaymentState(StatesGroup):
    waiting_for_payment = State()


START_TEXT = (
    f'<tg-emoji emoji-id="{E_INVADER}">👾</tg-emoji> <b>NetErrror Private</b> — нейросети на максимум без ограничений и цензуры\n\n'
    f'<tg-emoji emoji-id="{E_ROCKET}">🚀</tg-emoji> <b>Что внутри закрытого канала:</b>\n'
    f'├ <tg-emoji emoji-id="{E_CHECK}">✔️</tg-emoji> Готовые промпты для обхода цензуры и запретов\n'
    f'├ <tg-emoji emoji-id="{E_PROFILE}">👤</tg-emoji> Уютный закрытый чат для общения и помощи\n'
    f'├ <tg-emoji emoji-id="{E_INVADER}">💫</tg-emoji> Нейросети и сервисы без ограничений\n'
    f'├ <tg-emoji emoji-id="{E_BELL}">🔔</tg-emoji> Свежие обновления и новые способы обхода каждый день\n'
    f'├ <tg-emoji emoji-id="{E_DOCS}">📝</tg-emoji> Написание промптов лично под твои задачи\n'
    f'├ <tg-emoji emoji-id="{E_FLASH}">⚡️</tg-emoji> Доступ к приватной CPA-сети для заработка\n'
    f'└ <tg-emoji emoji-id="{E_CHECK}">▶️</tg-emoji> Шаблоны готовых команд под любые запросы\n\n'
    f'<tg-emoji emoji-id="{E_BELL}">❗️</tg-emoji> <b>Работает со всеми популярными моделями:</b>\n'
    '• Manus / Antigravity / Copilot\n'
    '• Cursor: Fable 5 / Opus 4.8 / Auto / Composer 2.5\n'
    '• Claude 4.7 Opus / 4.6 Sonnet и остальные / Claude Code\n'
    '• Gemini 3.5 Flash / 3.1 Pro / 3.1 Flash / Lite\n'
    '• DeepSeek Expert и остальные\n'
    '• Grok 4.3 Expert / Fast\n'
    '• Chat GPT 5.5 instant\n'
    '• Codex 5.3\n'
    '• GLM 5.2 Deep Think / 5.1 Agent + Thinking\n'
    '• Perplexity / Gemma / Kimi K2.6\n'
    '• Qwen Coder / Qwen 3.7 Plus / 3.7 Max и остальные\n\n'
    f'<tg-emoji emoji-id="{E_FLASH}">🔥</tg-emoji> <b>Жми на кнопку ниже, чтобы забрать доступ:</b>'
)

HELP_TEXT = (
    f'<tg-emoji emoji-id="{E_DOCS}">📝</tg-emoji> <b>Справочный центр и правовая информация</b>\n\n'
    f'<tg-emoji emoji-id="{E_PROFILE}">👤</tg-emoji> <b>Поддержка:</b> @{config.SUPPORT_USERNAME}\n\n'
    f'<tg-emoji emoji-id="{E_DOCS}">📄</tg-emoji> <b>Официальные документы:</b>\n'
    f'├ <a href="{USER_AGREEMENT_URL}">Пользовательское соглашение</a>\n'
    f'└ <a href="{PRIVACY_POLICY_URL}">Политика конфиденциальности</a>'
)


def get_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Активировать доступ", callback_data="get_access", icon_custom_emoji_id=E_FLASH)],
        [
            InlineKeyboardButton(text="Поддержка", url=SUPPORT_PROFILE, icon_custom_emoji_id=E_PROFILE),
            InlineKeyboardButton(text="Правовая информация", callback_data="legal_agreements", icon_custom_emoji_id=E_DOCS)
        ]
    ])


def get_legal_keyboard(back_target: str = "back_start") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пользовательское соглашение", url=USER_AGREEMENT_URL, icon_custom_emoji_id=E_CHECK)],
        [InlineKeyboardButton(text="Политика конфиденциальности", url=PRIVACY_POLICY_URL, icon_custom_emoji_id=E_BELL)],
        [InlineKeyboardButton(text="Написать в поддержку", url=SUPPORT_PROFILE, icon_custom_emoji_id=E_PROFILE)],
        [InlineKeyboardButton(text="Назад", callback_data=back_target, icon_custom_emoji_id=E_BACK)]
    ])


async def cleanup_reminder(chat_id: int, bot: Bot) -> None:
    task = reminder_tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()

    messages = reminder_messages.pop(chat_id, [])
    for msg_id in messages:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass


async def schedule_reminder_video(chat_id: int, bot: Bot) -> None:
    try:
        await asyncio.sleep(30)
        video_path = os.path.join(os.path.dirname(__file__), "money.MP4")
        if not os.path.exists(video_path):
            video_path = "money.MP4"

        msg = await bot.send_video(
            chat_id=chat_id,
            video=FSInputFile(video_path),
            caption=(
                f'<tg-emoji emoji-id="{E_SKEPTIC}">😒</tg-emoji> <b>Чего застыл?</b>\n\n'
                'Забирай доступ, пока действует актуальная цена!'
            )
        )
        if chat_id not in reminder_messages:
            reminder_messages[chat_id] = []
        reminder_messages[chat_id].append(msg.message_id)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Ошибка напоминания: {e}")


async def create_private_link(bot: Bot, user_id: int) -> str:
    invite = await bot.create_chat_invite_link(
        chat_id=config.CHANNEL_ID,
        name=f"Sub_{user_id}_{int(time.time())}",
        expire_date=int(time.time() + 86400),
        member_limit=1
    )
    return invite.invite_link


async def grant_user_access(bot: Bot, user_id: int, plan_key: str):
    plan = SBP_PLANS.get(plan_key)
    if not plan:
        return
    link = await create_private_link(bot, user_id)
    await add_subscription(user_id, link, plan["days"])

    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f'<tg-emoji emoji-id="{E_FLASH}">⚡️</tg-emoji> <b>Оплата подтверждена! Доступ выдан.</b>\n\n'
                f'├ <tg-emoji emoji-id="{E_CHECK}">✔️</tg-emoji> <b>Тариф:</b> {plan["label"]}\n'
                f'├ <tg-emoji emoji-id="{E_BELL}">🔔</tg-emoji> <b>Ссылка действует:</b> 24 часа (1 переход)\n'
                f'└ <tg-emoji emoji-id="{E_INVADER}">💫</tg-emoji> <a href="{link}"><b>ВСТУПИТЬ В ЗАКРЫТЫЙ КАНАЛ</b></a>\n\n'
                '<i>Перейдите по ссылке прямо сейчас, чтобы не потерять доступ.</i>'
            ),
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Не удалось отправить ссылку {user_id}: {e}")


async def poll_order_payment(bot: Bot, user_id: int, platega_id: str, plan_key: str):
    for _ in range(120):
        await asyncio.sleep(10)
        if user_id not in active_orders or active_orders[user_id].get("id") != platega_id:
            break
        is_paid = await check_platega_status(platega_id)
        if is_paid:
            active_orders.pop(user_id, None)
            await grant_user_access(bot, user_id, plan_key)
            break


@dp.chat_member(F.chat.id == config.CHANNEL_ID)
async def on_channel_join(event: ChatMemberUpdated):
    if event.new_chat_member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        invite_link = event.invite_link.invite_link if event.invite_link else ""
        await mark_user_joined(invite_link, event.new_chat_member.user.id)


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await cleanup_reminder(message.chat.id, message.bot)
    await state.clear()

    welcome_path = os.path.join(os.path.dirname(__file__), "welcome.jpg")
    if not os.path.exists(welcome_path):
        welcome_path = "welcome.jpg"

    try:
        await message.answer_photo(
            photo=FSInputFile(welcome_path),
            caption=START_TEXT,
            reply_markup=get_start_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка фото: {e}")
        await message.answer(START_TEXT, reply_markup=get_start_keyboard())


@dp.message(Command("help"))
async def cmd_help(message: Message, bot: Bot) -> None:
    await cleanup_reminder(message.chat.id, bot)
    await message.answer(
        HELP_TEXT,
        reply_markup=get_legal_keyboard("back_start"),
        disable_web_page_preview=True
    )


@dp.message(Command("give"))
async def cmd_give(message: Message, bot: Bot):
    await cleanup_reminder(message.chat.id, bot)
    if message.from_user.id not in getattr(config, "ADMIN_IDS", []):
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Формат: <code>/give &lt;user_id&gt; &lt;1m|3m|6m|1y|forever&gt;</code>")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("Неверный user_id")
        return

    plan_key = parts[2]
    if plan_key not in SBP_PLANS:
        await message.answer("Неверный тариф. Доступно: 1m, 3m, 6m, 1y, forever")
        return

    await grant_user_access(bot, target_id, plan_key)
    await message.answer(f"✅ Доступ успешно выдан {target_id} на {SBP_PLANS[plan_key]['label']}!")


@dp.callback_query(F.data == "get_access")
async def cb_get_access(call: CallbackQuery, state: FSMContext) -> None:
    await cleanup_reminder(call.message.chat.id, call.bot)
    await state.set_state(PaymentState.waiting_for_payment)

    min_sbp_price = SBP_PLANS.get("1m", {}).get("price_str", "600₽")

    text = (
        f'<tg-emoji emoji-id="{E_WALLET}">👛</tg-emoji> <b>Выбирай удобный способ оплаты:</b>\n\n'
        f'├ <tg-emoji emoji-id="{E_SBP}">💳</tg-emoji> <b>Карта / СБП — от {min_sbp_price}</b>\n'
        '└ Одноразовая ссылка на 24 часа с авто-выдачей\n\n'
        f'├ <tg-emoji emoji-id="{E_ROCKET}">🚀</tg-emoji> <b>xRocket</b>\n'
        '└ Оплата криптовалютой и чеками\n\n'
        f'└ <tg-emoji emoji-id="{E_CRYPTO}">💎</tg-emoji> <b>CryptoBot</b>\n'
        '└ Оплата через Send / Инвойс (USDT, TON, BTC)\n\n'
        f'<tg-emoji emoji-id="{E_BELL}">⏰</tg-emoji> <i>Доступ в приват выдаётся сразу после оплаты!</i>'
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить СБП / Картой", callback_data="pay_sbp_menu", icon_custom_emoji_id=E_SBP)],
        [InlineKeyboardButton(text="Оплатить через xRocket", url=XROCKET_URL, icon_custom_emoji_id=E_ROCKET)],
        [InlineKeyboardButton(text="Оплатить через CryptoBot", url=CRYPTO_URL, icon_custom_emoji_id=E_CRYPTO)],
        [InlineKeyboardButton(text="Назад в меню", callback_data="back_start", icon_custom_emoji_id=E_BACK)]
    ])

    try:
        await call.message.edit_caption(caption=text, reply_markup=keyboard)
    except Exception:
        await call.message.edit_text(text, reply_markup=keyboard)

    await call.answer()
    reminder_tasks[call.message.chat.id] = asyncio.create_task(
        schedule_reminder_video(call.message.chat.id, call.bot)
    )


@dp.callback_query(F.data == "pay_sbp_menu")
async def cb_pay_sbp_menu(call: CallbackQuery) -> None:
    await cleanup_reminder(call.message.chat.id, call.bot)

    text = (
        f'<tg-emoji emoji-id="{E_SBP}">💳</tg-emoji> <b>Оплата через СБП / Карту РФ:</b>\n\n'
        f'<tg-emoji emoji-id="{E_FLASH}">⚡️</tg-emoji> <b>Автоматическая выдача:</b> после транзакции бот выдает персональную одноразовую ссылку на 24 часа.\n'
        '└ Бот заранее напомнит о продлении за 3 дня и за 24 часа.\n\n'
        f'<tg-emoji emoji-id="{E_DOCS}">📄</tg-emoji> <i>Перед покупкой обязательно ознакомьтесь с <a href="{USER_AGREEMENT_URL}">пользовательским соглашением</a> и <a href="{PRIVACY_POLICY_URL}">политикой конфиденциальности</a>.</i>\n\n'
        f'<tg-emoji emoji-id="{E_INVADER}">👾</tg-emoji> <b>Выберите период подписки:</b>'
    )

    buttons = []
    for plan_id, plan in SBP_PLANS.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"{plan['label']} — {plan['price_str']}",
                callback_data=f"buy_plan_{plan_id}",
                icon_custom_emoji_id=plan['icon']
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="Назад к способам оплаты",
            callback_data="back_to_access",
            icon_custom_emoji_id=E_BACK
        )
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    video_path = os.path.join(os.path.dirname(__file__), "Privet.mp4")
    switched = False

    if os.path.exists(video_path):
        try:
            await call.message.edit_media(
                media=InputMediaVideo(
                    media=FSInputFile(video_path),
                    caption=text,
                    parse_mode=ParseMode.HTML
                ),
                reply_markup=kb
            )
            switched = True
        except Exception as e:
            logger.warning(f"Ошибка медиа Privet.mp4: {e}")

    if not switched:
        try:
            await call.message.edit_caption(caption=text, reply_markup=kb)
        except Exception:
            await call.message.edit_text(text, reply_markup=kb)

    await call.answer()


@dp.callback_query(F.data.startswith("buy_plan_"))
async def cb_buy_plan(call: CallbackQuery) -> None:
    await cleanup_reminder(call.message.chat.id, call.bot)
    plan_key = call.data.replace("buy_plan_", "")
    plan = SBP_PLANS.get(plan_key)

    if not plan:
        await call.answer("Тариф не найден.", show_alert=True)
        return

    await call.answer("Генерируем счет СБП...")

    platega_id, payment_url, err = await create_platega_payment(
        amount=plan["amount"],
        user_id=call.from_user.id,
        plan_key=plan_key
    )

    if not payment_url:
        detail_msg = f"\n<code>Ответ кассы: {err}</code>" if err else ""
        await call.message.answer(
            f"Не удалось связаться с платежной системой.{detail_msg}\nНапишите владельцу: @{config.OWNER_USERNAME}"
        )
        return

    active_orders[call.from_user.id] = {
        "id": platega_id,
        "plan_key": plan_key
    }

    asyncio.create_task(poll_order_payment(call.bot, call.from_user.id, platega_id, plan_key))

    text = (
        f'<tg-emoji emoji-id="{E_SBP}">💳</tg-emoji> <b>Счёт на оплату готов:</b>\n\n'
        f'├ <b>Тариф:</b> {plan["label"]}\n'
        f'├ <b>Сумма к оплате:</b> {plan["price_str"]}\n'
        f'└ <b>Способ:</b> СБП / Банковская карта РФ\n\n'
        f'<tg-emoji emoji-id="{E_BELL}">⏰</tg-emoji> <i>После оплаты доступ активируется автоматически!</i>'
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Оплатить {plan['price_str']}", url=payment_url, icon_custom_emoji_id=E_FLASH)],
        [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_pay_{platega_id}_{plan_key}", icon_custom_emoji_id=E_CHECK)],
        [InlineKeyboardButton(text="Назад к тарифам", callback_data="pay_sbp_menu", icon_custom_emoji_id=E_BACK)]
    ])

    try:
        await call.message.edit_caption(caption=text, reply_markup=kb)
    except Exception:
        await call.message.edit_text(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("check_pay_"))
async def cb_check_pay(call: CallbackQuery):
    await cleanup_reminder(call.message.chat.id, call.bot)
    parts = call.data.split("_")
    platega_id = parts[2]
    plan_key = parts[3]

    is_paid = await check_platega_status(platega_id)
    if is_paid:
        active_orders.pop(call.from_user.id, None)
        await call.answer("Оплата подтверждена!", show_alert=True)
        await grant_user_access(call.bot, call.from_user.id, plan_key)
        try:
            await call.message.delete()
        except Exception:
            pass
    else:
        await call.answer("Оплата пока не поступила. Попробуйте через пару секунд.", show_alert=True)


@dp.callback_query(F.data == "back_to_access")
async def cb_back_to_access(call: CallbackQuery, state: FSMContext) -> None:
    await cleanup_reminder(call.message.chat.id, call.bot)

    min_sbp_price = SBP_PLANS.get("1m", {}).get("price_str", "600₽")

    text = (
        f'<tg-emoji emoji-id="{E_WALLET}">👛</tg-emoji> <b>Выбирай удобный способ оплаты:</b>\n\n'
        f'├ <tg-emoji emoji-id="{E_SBP}">💳</tg-emoji> <b>Карта / СБП — от {min_sbp_price}</b>\n'
        '└ Одноразовая ссылка на 24 часа с авто-выдачей\n\n'
        f'├ <tg-emoji emoji-id="{E_ROCKET}">🚀</tg-emoji> <b>xRocket</b>\n'
        '└ Оплата криптовалютой и чеками\n\n'
        f'└ <tg-emoji emoji-id="{E_CRYPTO}">💎</tg-emoji> <b>CryptoBot</b>\n'
        '└ Оплата через Send / Инвойс (USDT, TON, BTC)\n\n'
        f'<tg-emoji emoji-id="{E_BELL}">⏰</tg-emoji> <i>Ссылка на вход выдаётся сразу после оплаты!</i>'
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить СБП / Картой", callback_data="pay_sbp_menu", icon_custom_emoji_id=E_SBP)],
        [InlineKeyboardButton(text="Оплатить через xRocket", url=XROCKET_URL, icon_custom_emoji_id=E_ROCKET)],
        [InlineKeyboardButton(text="Оплатить через CryptoBot", url=CRYPTO_URL, icon_custom_emoji_id=E_CRYPTO)],
        [InlineKeyboardButton(text="Назад в меню", callback_data="back_start", icon_custom_emoji_id=E_BACK)]
    ])

    welcome_path = os.path.join(os.path.dirname(__file__), "welcome.jpg")
    switched = False

    if os.path.exists(welcome_path):
        try:
            await call.message.edit_media(
                media=InputMediaPhoto(
                    media=FSInputFile(welcome_path),
                    caption=text,
                    parse_mode=ParseMode.HTML
                ),
                reply_markup=keyboard
            )
            switched = True
        except Exception as e:
            logger.warning(f"Ошибка медиа: {e}")

    if not switched:
        try:
            await call.message.edit_caption(caption=text, reply_markup=keyboard)
        except Exception:
            await call.message.edit_text(text, reply_markup=keyboard)

    await call.answer()
    reminder_tasks[call.message.chat.id] = asyncio.create_task(
        schedule_reminder_video(call.message.chat.id, call.bot)
    )


@dp.callback_query(F.data == "legal_agreements")
async def cb_legal_agreements(call: CallbackQuery, state: FSMContext) -> None:
    await cleanup_reminder(call.message.chat.id, call.bot)
    await state.clear()
    try:
        await call.message.edit_caption(caption=HELP_TEXT, reply_markup=get_legal_keyboard("back_start"))
    except Exception:
        await call.message.edit_text(HELP_TEXT, reply_markup=get_legal_keyboard("back_start"), disable_web_page_preview=True)
    await call.answer()


@dp.callback_query(F.data == "back_start")
async def cb_back_start(call: CallbackQuery, state: FSMContext) -> None:
    await cleanup_reminder(call.message.chat.id, call.bot)
    await state.clear()

    welcome_path = os.path.join(os.path.dirname(__file__), "welcome.jpg")
    switched = False

    if os.path.exists(welcome_path):
        try:
            await call.message.edit_media(
                media=InputMediaPhoto(
                    media=FSInputFile(welcome_path),
                    caption=START_TEXT,
                    parse_mode=ParseMode.HTML
                ),
                reply_markup=get_start_keyboard()
            )
            switched = True
        except Exception:
            pass

    if not switched:
        try:
            await call.message.edit_caption(caption=START_TEXT, reply_markup=get_start_keyboard())
        except Exception:
            await call.message.edit_text(START_TEXT, reply_markup=get_start_keyboard())

    await call.answer()


async def subscription_watcher(bot: Bot):
    while True:
        try:
            warn_3d, warn_1d, to_kick = await get_expiring_users()

            for row in warn_3d:
                uid = row["user_id"]
                msg_text = (
                    f'<tg-emoji emoji-id="{E_BELL}">🔔</tg-emoji> <b>Важная информация по подписке!</b>\n\n'
                    'До окончания доступа в закрытый канал <b>NetErrror Private</b> осталось <b>3 дня</b>.\n\n'
                    f'<tg-emoji emoji-id="{E_FLASH}">⚡️</tg-emoji> Продлите доступ заранее, чтобы не потерять приватные промпты и чат!'
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Продлить подписку", callback_data="get_access", icon_custom_emoji_id=E_FLASH)]
                ])
                try:
                    await bot.send_message(chat_id=uid, text=msg_text, reply_markup=kb)
                except Exception:
                    pass
                await set_warned(uid, "warned_3d")

            for row in warn_1d:
                uid = row["user_id"]
                msg_text = (
                    f'<tg-emoji emoji-id="{E_BELL}">❗️</tg-emoji> <b>Внимание: остался 1 день!</b>\n\n'
                    'Ваша подписка на <b>NetErrror Private</b> истекает менее чем через <b>24 часа</b>.\n\n'
                    '<i>После истечения срока бот автоматически исключит вас из канала.</i>'
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Продлить сейчас", callback_data="get_access", icon_custom_emoji_id=E_FLASH)]
                ])
                try:
                    await bot.send_message(chat_id=uid, text=msg_text, reply_markup=kb)
                except Exception:
                    pass
                await set_warned(uid, "warned_1d")

            for row in to_kick:
                uid = row["user_id"]
                try:
                    await bot.ban_chat_member(chat_id=config.CHANNEL_ID, user_id=uid)
                    await bot.unban_chat_member(chat_id=config.CHANNEL_ID, user_id=uid)

                    msg_text = (
                        f'<tg-emoji emoji-id="{E_SKEPTIC}">😒</tg-emoji> <b>Срок вашей подписки истек</b>\n\n'
                        'Вы были исключены из приватного канала <b>NetErrror Private</b>.\n\n'
                        'Чтобы восстановить доступ, выберите тариф в меню бота:'
                    )
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Вернуть доступ", callback_data="get_access", icon_custom_emoji_id=E_FLASH)]
                    ])
                    await bot.send_message(chat_id=uid, text=msg_text, reply_markup=kb)
                except Exception as e:
                    logger.error(f"Ошибка исключения пользователя {uid}: {e}")

                await deactivate_user(uid)

        except Exception as e:
            logger.error(f"Ошибка watcher: {e}")

        await asyncio.sleep(600)


async def main():
    await init_db()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="help", description="Поддержка и правила")
    ])

    asyncio.create_task(subscription_watcher(bot))

    logger.info("🚀 Бот NetErrror Private запущен с официальным API Platega!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
