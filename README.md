# ▓▒░ NetErrror ░▒▓ — бот продажи доступа в приватную группу

Telegram-бот на **aiogram 3.x** для автоматической продажи подписок на доступ
в приватную группу/канал. Тёмный киберпанк-стиль, SQLite, авто-контроль подписок,
админ-панель.

## Возможности
- `/start` — приветствие с картинкой и меню: Профиль / Купить / Поддержка
- Тарифы: 1 мес ($5), 3 мес ($10), 6 мес ($18), Навсегда ($150)
- Симуляция оплаты (готовая точка под CryptoPay / Telegram Stars)
- Автогенерация одноразовой инвайт-ссылки после оплаты
- Фоновый воркер: раз в сутки кикает истёкших + уведомляет в ЛС
- Админ-панель `/admin`: управление подпиской, кик, объявления, рассылка

## Структура
```
neterror_bot/
├── bot.py                # точка входа
├── config.py             # настройки (токен, админы, тарифы)
├── requirements.txt
├── database/
│   └── db.py             # SQLite (users / subscriptions / payments)
├── handlers/
│   ├── user.py           # /start, профиль, выбор тарифа
│   ├── payments.py       # подтверждение оплаты + инвайт
│   └── admin.py          # админ-панель (FSM)
├── keyboards/
│   └── keyboards.py      # инлайн-клавиатуры
└── utils/
    ├── texts.py          # оформление / стартовое меню
    └── scheduler.py      # фоновый контроль подписок
```

## Установка
```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка
Заполните `config.py` или переменные окружения:

| Параметр           | Что это                                                        |
|--------------------|---------------------------------------------------------------|
| `BOT_TOKEN`        | токен от @BotFather                                            |
| `ADMIN_IDS`        | ваши ID через запятую (узнать у @userinfobot)                  |
| `PRIVATE_CHAT_ID`  | ID приватного чата (для супергрупп начинается с `-100…`)       |
| `SUPPORT_USERNAME` | username поддержки без @                                       |
| `WELCOME_IMAGE`    | URL или путь к картинке (необязательно)                        |

> ⚠️ Бот должен быть **администратором** приватного чата с правами
> «Приглашать по ссылке» и «Банить пользователей».

Пример через переменные окружения:
```bash
export BOT_TOKEN="123:ABC"
export ADMIN_IDS="111111111"
export PRIVATE_CHAT_ID="-1001234567890"
export SUPPORT_USERNAME="neterror_support"
```

## Запуск
```bash
python bot.py
```

## Подключение реальной оплаты
В `handlers/payments.py` (функция `cb_pay_confirm`) помечен блок
`ТОЧКА ИНТЕГРАЦИИ РЕАЛЬНОЙ ОПЛАТЫ`. Замените `payment_ok = True` на
реальную проверку:
- **CryptoPay**: создать инвойс через `createInvoice`, опрашивать `getInvoices`
  по `invoice_id` со статусом `paid`.
- **Telegram Stars**: использовать `bot.send_invoice` (currency `XTR`) и
  обработать `pre_checkout_query` + `successful_payment`.

## Заметки
- Все действия логируются в консоль и `neterror.log`.
- Интервал проверки подписок задаётся `SUB_CHECK_INTERVAL` (сек, по умолч. 86400).
