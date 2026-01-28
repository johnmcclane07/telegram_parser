import logging
import time
from urllib.parse import urlparse
import asyncio
from telethon import TelegramClient
from transformers import pipeline
from qrcode import QRCode
import getpass
from telethon import errors
from decouple import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== Telegram ==================

API_ID = config("API_ID", cast=int)
API_HASH = config("API_HASH")

# ================== ML ==================

sentiment_pipeline = pipeline(
    model="seara/rubert-tiny2-russian-sentiment",
)

BATCH_SIZE = 32

# ================== Utils ==================

def parse_telegram_post_url(url: str):
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    return parts[0], int(parts[1])

# ================== Sentiment ==================

def analyze_batch(comments):
    texts = [c.text[:512] for c in comments]

    start = time.perf_counter()

    outputs = sentiment_pipeline(
        texts,
        batch_size=BATCH_SIZE,
        truncation=True,
    )

    elapsed = time.perf_counter() - start
    logger.info(f"[BATCH] {len(texts)} comments in {elapsed:.2f}s")

    results = []

    for comment, result in zip(comments, outputs):
        label = result["label"].lower()

        results.append({
            "comment_id": comment.id,
            "text": comment.text,
            "date": comment.date,
            "sentiment": label,
            "label": label,
            "score": float(result["score"]),
        })

    return results

# ================== QR Utils ==================

qr = QRCode()

def gen_qr(token: str):
    qr.clear()
    qr.add_data(token)
    qr.print_ascii()

def display_url_as_qr(url: str):
    print("Сканируй QR-код в Telegram:")
    gen_qr(url)

# ================== Telegram Client ==================

async def get_client_qr():
    client = TelegramClient("qr_session", API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        return client

    qr_login = await client.qr_login()
    logged_in = False

    while not logged_in:
        display_url_as_qr(qr_login.url)
        try:
            logged_in = await qr_login.wait(timeout=10)
        except errors.SessionPasswordNeededError:
            password = getpass.getpass("Введите пароль двухфакторной аутентификации Telegram: ")
            await client.sign_in(password=password)
            logged_in = True
        except Exception:
            qr_login = await qr_login.recreate()

    me = await client.get_me()
    print("Вы вошли как:", me.username)

    return client


# ================== Main ==================

async def fetch_comments(channel_id, post_id):
    async with await get_client_qr() as client:
        logger.info(f"[START] Fetching comments {channel_id}/{post_id}")

        buffer = []
        all_results = []

        async for message in client.iter_messages(
            entity=channel_id,
            reply_to=post_id,
            reverse=True,
        ):
            if not message.text:
                continue

            buffer.append(message)

            if len(buffer) >= BATCH_SIZE:
                batch_results = analyze_batch(buffer)
                all_results.extend(batch_results)
                buffer.clear()

        if buffer:
            batch_results = analyze_batch(buffer)
            all_results.extend(batch_results)

        logger.info("[END] Done")
        return all_results