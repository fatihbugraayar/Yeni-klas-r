# Telegram Emoji, Sticker & AI Studio Bot

An asynchronous aiogram bot with custom emoji and regular sticker sets, AI grid blueprints,
localized generation prompts, OpenCV face censorship,
Telegram Stars, SQLAlchemy persistence, and Turkish / English / German interfaces.

## Run locally

Use Python 3.12 for the locked dependency set. In PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
Copy-Item .env.example .env
# Edit .env: supply your BotFather token and an actual support contact.
.venv\Scripts\python.exe -m telegram_bot.main
```

The workspace already contains a virtual environment with the development dependencies installed.
Do not commit `.env`. Required settings are `BOT_TOKEN` and `SUPPORT_CONTACT`.
Configuration is read from environment variables and `.env`; environment variables take precedence.
No payment provider token is needed for Stars. The bot uses private chats and long polling.

Commands: `/start`, `/emoji_pack`, `/photo_edit`, `/ai_studio`, `/language`, `/quota`, `/status`, `/terms`,
`/support`, `/paysupport`, `/cancel`.

## Features and charging rules

| Service | Free allowance | Paid operation |
| --- | --- | --- |
| Emoji pack, 2×2 through 8×8 | First 3 successful packs | 50 Stars |
| Face pixelation or blur | 5 lifetime uses plus 1 daily use | 20 Stars |
| AI Studio, 1×1 through 9×9, emoji or sticker output | First successful pack | 100 Stars |

The three services have separate quota pools. AI Studio templates and prompts cost no credits
or Stars. Both Studio output formats share its one lifetime free pack.

## AI Grid Studio

1. Open `/ai_studio` and select a grid from 1×1 to 9×9.
2. Receive a 1024×1024 PNG blueprint with dashed boundaries, A1… I9 cell coordinates,
   numbered cells, and a checkerboard transparency guide. A localized, copyable prompt includes
   a subject slot to fill in.
3. Use the blueprint and prompt in your own image generator, then upload the generated sprite
   sheet to the bot. No AI API key is required by this bot. External generators have their own
   terms and prices; the bot does not call them or guarantee exact cell alignment in their output.
4. Choose **custom emoji (100×100 PNG)** or **regular stickers (512×512 PNG)** after uploading.
   Use an optional image caption as the branded pack title. The first pack is free; subsequent
   packs require a 100-XTR invoice before Telegram set creation.
5. Receive `t.me/addemoji/...` or `t.me/addstickers/...`, matching the chosen output.

Studio inputs are center-cropped and sliced in row-major order. Existing alpha is preserved;
white backgrounds are kept. Upload PNG as a document when transparency matters. A PNG above
512 KiB is reduced to a palette with transparent colors to meet the static-sticker upload budget.
The original emoji splitter continues to produce lossless 100×100 WebP tiles.
An 81-tile set starts with 50 entries and appends 31. Telegram may merge identical stickers;
use distinct assets in each cell. These limits and formats follow the
[Telegram sticker API](https://core.telegram.org/bots/api#createnewstickerset),
[static image requirements](https://core.telegram.org/stickers#static-stickers-and-emoji), and
[static sticker upload specifications](https://core.telegram.org/import-stickers#static-stickers).

Template drawing and slicing run in worker threads sharing a bounded processing pool. The
blueprint is sent from memory. Format buttons are bound to a specific upload, preventing an
old image's buttons from submitting its replacement. Only Telegram message metadata stays in
the input FSM; prepared tile files and paid jobs use the existing durable recovery path.

Daily photo credit resets lazily on the next interaction after **00:00 UTC**, never accumulates,
and is consumed before lifetime credit. Credit reservation and job insertion happen in one database
transaction. Invalid images and images with no detected faces do not reserve credit or generate
invoices. Failed free operations restore their reservation; yesterday's daily reservation cannot
add another credit today.

Images are EXIF-oriented, center-cropped into a square for direct emoji packs, split in row-major order,
and resized to 100×100 lossless WebP tiles with alpha preserved. Titles use an optional image caption
and always end in ` • by @bot_username`; slugs end in `_by_bot_username`.
The 8×8 flow creates the initial 50 stickers and appends 14 because Telegram limits a new set to
50 initial stickers. Static format is set on each `InputSticker` and on `uploadStickerFile` rather
than relying on the deprecated top-level `sticker_format` argument.
[Telegram sticker API](https://core.telegram.org/bots/api#createnewstickerset).

Face detection uses OpenCV's bundled frontal-face Haar cascade, with a detection preview capped at
1600 pixels per side. Pixelation or a 51×51 Gaussian blur changes only the detected rectangles;
source dimensions and alpha are preserved. Results are sent as **PNG documents**, avoiding
additional Telegram photo compression. Original EXIF is discarded. Automatic face detection can
miss faces, especially profiles or small faces; inspect the result before sharing. Sending an input
as a Telegram photo may already compress it, so upload a document when source quality matters.

The language follows the user's initial Telegram language (`tr`, `en`, `de`, including regional
variants). Unsupported languages fall back to Turkish. Manual choices persist in the database.
The main menu includes a language button and appears after delivery.

## Payments, recovery, and privacy

Invoices use `currency="XTR"`, an empty provider token, and one `LabeledPrice`, with an opaque job ID
payload. The checkout handler validates owner, currency, amount, terms acceptance, job status,
media availability, and expiry; its database validation has a 7.5-second timeout to leave time for
Telegram's 10-second response deadline. It bypasses CPU work and input-flow locks.
Successful payments are processed independently of FSM state. Charge IDs are unique; repeat updates
do not charge quotas or repeat completed operations. Additional charges for the same job are refunded.
The bot includes terms acceptance and `/paysupport` as described in
[Telegram's Stars integration guide](https://core.telegram.org/bots/payments-stars).

The polling reader stores successful-payment updates in a durable inbox **before advancing the
Telegram update offset**. A recovery loop replays unrecorded payments. Once a transaction is saved,
its persisted job or refund handles recovery. This uses a protected aiogram reader method; retain
the integration test when updating aiogram. Unfinished paid/free jobs, prepared assets, uploaded
sticker file IDs, deterministic pack names, and pending refunds survive process restarts. Grid/mode
selection uses `MemoryStorage`, so an unfinished input selection restarts after a reboot.

Network/server failures are retried three times after the initial attempt; Telegram rate limits
schedule a retry using `retry_after`. Permanent failures restore free credit or queue a Stars refund.
Refund failures remain in the database for retry. A partial emoji or sticker set can remain on Telegram after
a failed request. Delivery is **at least once** across a crash or ambiguous network timeout: Telegram
has no idempotency key for `sendDocument` / `sendMessage`, so a delivered result can be sent again if
the process crashes before the local completion commit. Payments and quota accounting are idempotent.

Prepared images live under `DATA_DIR`. They are deleted after successful delivery or failure.
Unpaid invoices expire after `INVOICE_TTL_MINUTES` (default 60); approved checkouts retain assets
for an extra 24 hours to allow delayed payment updates, after which late charges are refunded.
A sweep removes old orphaned or terminal-job directories. Images are not stored in FSM or logs.
Job metadata, user quotas/language, and payment receipts remain in the database for support.
Telegram retains its own uploaded copies. Store the data directory on protected storage, and
apply your own retention policy to historical database records and backups.

## Deploy

```powershell
docker compose up --build -d
docker compose logs -f bot
```

The container runs as an unprivileged user with a persistent named data volume and restart policy.
Docker deployment instructions are supplied; the image has not been built in this workspace.
Run **one bot process per token and data directory**. A local filesystem lock prevents accidental
concurrent workers using the same directory. This is a single-instance polling implementation;
multi-instance deployment needs distributed job leases, shared media storage, and a shared FSM.

SQLite with WAL is the default. PostgreSQL is supported through
`DATABASE_URL=postgresql+asyncpg://user:password@host:5432/bot`.
New installations create the schema on startup. The 1.1 upgrade includes an idempotent migration
adding `users.free_ai_studio_credits` with one credit for existing users. It preserves the previous
quotas, preferences, jobs, and payment records, and does not replenish Studio credit on later starts.

To upgrade an existing installation, stop the running bot, back up the database and media together,
retain your existing `.env`, then start the updated code. The migration runs during startup; it has
not been applied to the workspace's runtime database during development. Future schema changes
still need explicit migrations; `create_all` alone does not migrate columns. Optional `ADMIN_IDS`
accepts a JSON array of numeric Telegram user IDs; no administrative commands are implemented.

Keep database and media backups consistent, monitor logs and the `refund_pending` / `payment_inbox`
tables, and keep downtime below Telegram's 24-hour update-retention window. Set `CPU_CONCURRENCY`
according to available memory (default 2). Uploads are capped at 20 MB and 16 million pixels by
default; decoded memory can be much larger than the compressed input. Polling admits at most
64 concurrent updates, while image preparations and deliveries have separate bounded pools.

## Development and validation

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m ruff check telegram_bot tests
.venv\Scripts\python.exe -m pytest -q
```

Tests use a real temporary SQLite database and a simulated Telegram API session. They cover direct
grids and all nine Studio blueprints, both output sizes, alpha and ordering, bounding-box-only censorship, EXIF handling, image limits, real
no-face detection, concurrent quota reservation, UTC rollover, credit restoration, invoice
validation, duplicate charges, refund retry, 64-tile set creation/resume, 81-tile regular set creation,
localized Studio prompts, stale upload buttons, 100-XTR payment replay, legacy database migration,
routing and payment-inbox replay. Live Telegram uploads, Stars settlement, PostgreSQL, and Docker require separate deployment
smoke tests with configured credentials; no live payments were made during implementation.

Project layout follows the requested `telegram_bot/{database,locales,middlewares,services,handlers,
keyboards}` structure. Additional repository, worker, inbox, and runtime-lock modules keep payment
recovery independent of the conversational FSM.
