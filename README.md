# 🤖 VibeParser

Приватний Telegram-бот, який у реальному часі збирає нові замовлення з фриланс-бірж,
фільтрує їх за твоїми правилами та надсилає картку із сумою, описом, QR-кодом і
кнопками для швидкого відгуку.

Бот не замінює акаунт на біржі: він готує текст/файл і відкриває сторінку
замовлення. Для **Freelancehunt** є опційний справжній Auto-bid через офіційний API.

---

## Що вміє

- 📡 Опитує кілька джерел паралельно, кожні 20–3600 секунд.
- 🆕 Надсилає лише **нові** замовлення (перший цикл кожного джерела — тихий baseline).
- 🖼 Малює темну картку замовлення з бюджетом, категорією, тегами та QR-кодом.
- 🎛 Фільтри: ключові слова, мінус-слова, мінімальний/максимальний бюджет у гривні,
  «пропускати замовлення без бюджету», вибір активних джерел.
- 📄 Бібліотека резюме (PDF/DOC/DOCX/TXT/RTF/ODT) і швидких відповідей.
- ✍️ Композер відгуку: резюме, шаблон або власний текст → готове повідомлення з
  посиланням на замовлення.
- 🚀 Auto-bid на Freelancehunt (за наявності `FREELANCEHUNT_TOKEN`).
- 📊 Статус джерел, статистика, тестова картка, зміна інтервалу й ліміту з бота.
- 🔒 Приватність: доступ лише власнику / `ADMIN_IDS`.

## Джерела

| Джерело | Статус | Як працює |
|---|---|---|
| Freelancehunt | ✅ увімкнено | офіційний публічний JSON API |
| Weblancer | ✅ увімкнено | HTML-парсинг списку |
| Freelance.ua | ✅ увімкнено | HTML-парсинг списку |
| Freelancer.com | ✅ увімкнено | публічний JSON API |
| Djinni | ⚪ вимкнено | RSS (IT-вакансії, не лише замовлення) |
| Kwork | ⚪ вимкнено | HTML; сайт недоступний з частини мереж |

Увімкнути/вимкнути джерело можна в боті: **🎛 Фільтри → 📡 Джерела**.

---

## Швидкий старт (Windows)

Потрібен Python 3.11+ (перевірено на 3.12).

```powershell
cd D:\VibeParser

# 1. Віртуальне середовище
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Залежності
pip install -r requirements.txt

# 3. Конфігурація
Copy-Item .env.example .env
notepad .env
```

У `.env` встав:

```env
BOT_TOKEN=123456789:AA...
ADMIN_IDS=            # порожньо = перший /start стане власником
```

Запуск:

```powershell
python main.py
```

Відкрий свого бота в Telegram і натисни **Start**. Перший цикл збереже поточні
замовлення без сповіщень — далі приходитимуть лише нові.

## Запуск як `.exe` (Windows, без IDE)

Можна зібрати один самодостатній файл `VibeParser.exe`, якому не потрібен
встановлений Python:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

Скрипт встановить PyInstaller, згенерує іконку і покладе результат у
`dist\VibeParser.exe` (перша збірка триває 1–3 хвилини).

Далі:

1. Скопіюй `dist\VibeParser.exe` у будь-яку зручну теку (наприклад, `D:\VibeParserBot`).
2. Запусти exe подвійним кліком. При першому запуску поруч автоматично
   з'явиться `.env` з шаблону.
3. Встав `BOT_TOKEN` у `.env` (можна одразу погодитися відкрити Notepad) і
   запусти exe ще раз.
4. Дані, БД, резюме й лог з'являться в теці `data` поруч з exe:
   `data\vibeparser.log`.

Поради:

- Другий запуск exe не створить конфлікт: бот повідомить, що вже працює.
- `SCREENSHOT_MODE=page` у exe не підтримується (Playwright не входить у збірку) —
  використовуй `card`, це швидше й надійніше.
- Той самий exe має діагностичні команди:
  `VibeParser.exe demo`, `VibeParser.exe status`,
  `VibeParser.exe sources --source freelancehunt`.

## Швидкий старт (Linux / macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python main.py
```

## Docker

```bash
cp .env.example .env
nano .env
docker compose up -d --build
docker compose logs -f
```

Дані (БД, резюме, логи) зберігаються у `./data` завдяки volume.

---

## Налаштування `.env`

| Змінна | За замовчуванням | Опис |
|---|---|---|
| `BOT_TOKEN` | — | токен від [@BotFather](https://t.me/BotFather), обов'язковий |
| `ADMIN_IDS` | порожньо | ID користувачів через кому; порожньо = перший `/start` стає власником |
| `POLL_INTERVAL` | `75` | інтервал опитування, секунди (20–3600) |
| `HTTP_TIMEOUT` | `25` | таймаут запитів до бірж, секунди |
| `MAX_PAGES` | `2` | скільки сторінок списку читати (1–5) |
| `SCREENSHOT_MODE` | `card` | `card` — картка Pillow; `page` — скриншот сторінки через Playwright |
| `STARTUP_MESSAGE` | `false` | надсилати повідомлення про старт |
| `FREELANCEHUNT_TOKEN` | порожньо | токен API для Auto-bid |
| `RATE_*_UAH` | — | курси валют для фільтра за бюджетом |
| `DATA_DIR` | `./data` | тека даних |
| `DB_PATH` | `./data/vibeparser.db` | файл SQLite |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Де взяти `FREELANCEHUNT_TOKEN`

1. Зайди на <https://freelancehunt.com/my/api>.
2. Створи застосунок і скопіюй токен.
3. Додай у `.env`: `FREELANCEHUNT_TOKEN=...`
4. Перезапусти бота. У картках Freelancehunt з'явиться кнопка **🚀 Auto-bid**.

> Auto-bid публікує справжній відгук на біржі. Перевіряй суму, термін і текст
> перед підтвердженням. Для інших бірж автоматична публікація неможлива без
> їхнього офіційного API — бот готує текст і відкриває сторінку.

### Режим `SCREENSHOT_MODE=page`

Потрібен Playwright і браузер Chromium:

```bash
pip install -r requirements-optional.txt
playwright install chromium
```

Якщо скриншот не вдається (Cloudflare, таймаут), бот автоматично малює звичайну
картку. Для Docker може знадобитися `shm_size: "1gb"`.

---

## Команди та інтерфейс

| Команда | Дія |
|---|---|
| `/start` | головне меню |
| `/menu` | меню |
| `/check` | перевірити джерела зараз |
| `/status` | статус джерел і статистика |
| `/help` | довідка |

Кнопки:

- **📥 Замовлення** — останні замовлення, пагінація, картка з відгуком.
- **🔎 Пошук** — пошук по збережених замовленнях.
- **📄 Резюме** / **⚡ Швидкі відповіді** — бібліотека файлів і текстів.
- **🎛 Фільтри** — слова, бюджет, джерела.
- **📊 Статус** — здоров'я джерел, кількість замовлень, uptime.
- **⚙️ Налаштування** — сповіщення, інтервал, ліміт, тест картки.

Під кожною карткою:

- **✍️ Відгукнутись** — вибрати резюме / шаблон / свій текст;
- **🔗 Відкрити** — перейти на біржу;
- **🚀 Auto-bid** — лише Freelancehunt і лише з токеном.

---

## CLI без Telegram

```bash
python -m app.cli sources              # перевірити всі джерела
python -m app.cli sources --source weblancer --pages 2
python -m app.cli poll --render 3      # один цикл + 3 прев'ю карток
python -m app.cli demo                 # тестова картка
python -m app.cli status               # статистика БД
```

Для зібраного exe — так само, але без `python -m app.cli`:

```powershell
.\dist\VibeParser.exe sources --source weblancer --pages 2
.\dist\VibeParser.exe demo
.\dist\VibeParser.exe status
```

Прев'ю зберігаються у `data/previews/`.

## Тести

```bash
pip install -r requirements-dev.txt
pytest
```

Покрито: парсинг бюджетів, фільтри, БД і дедуплікацію, baseline-логіку
колектора, рендер картки, екранування HTML у підписах, парсери на локальних
фікстурах, реєстрацію роутерів бота.

---

## Структура проєкту

```
main.py                     # запуск бота + планувальник + CLI-режим
build_exe.ps1               # збірка dist\VibeParser.exe
VibeParser.spec             # рецепт PyInstaller
app/
  config.py                 # налаштування з .env
  paths.py                  # тека exe / ресурсів (source + frozen)
  models.py                 # Order, Filters, LibraryItem
  db.py                     # SQLite: orders, library, settings, source_state
  cli.py                    # офлайн-команди
  parsers/                  # 7 джерел + реєстр
  services/
    collector.py            # опитування, baseline, дедуплікація, сповіщення
    renderer.py             # картка Pillow + опційний Playwright
    notifier.py             # надсилання фото/тексту в Telegram
    matcher.py              # завантаження фільтрів
    scheduler.py            # фоновий цикл
    freelancehunt_bid.py    # Auto-bid через офіційний API
  bot/
    handlers/               # start, orders, library, filters, settings, autobid
    keyboards.py            # inline-клавіатури
    middlewares.py          # контроль доступу
  utils/
    single_instance.py      # захист від подвійного запуску
tests/                      # pytest
```

## Як це працює

1. Планувальник кожні N секунд запускає `Collector.collect_once()`.
2. Усі активні джерела опитуються паралельно (`asyncio.gather`).
3. Нові замовлення пишуться в SQLite; дублікати відсікаються `UNIQUE(source, external_id)`.
4. Перший успішний цикл джерела — тихий baseline (щоб не заспамити старими замовленнями).
5. Далі нові замовлення проходять фільтри й надсилаються картками (з лімітом за цикл).
6. Усе, що не підійшло під фільтри, залишається доступним у **📥 Замовлення**.

## Обмеження

- Більшість бірж не мають публічного API для подачі відгуків, тому бот готує
  текст/файл, а публікуєш ти.
- Парсери HTML залежать від розмітки сайтів. Якщо біржа змінить верстку,
  у **📊 Статус** з'явиться помилка джерела — парсер треба оновити.
- Cloudflare може блокувати окремі сайти з окремих мереж; бот продовжує
  працювати з іншими джерелами.
- Djinni — це переважно вакансії, тому джерело вимкнене за замовчуванням.

## Ліцензія

Приватний проєкт. Використовуй на власний розсуд.
