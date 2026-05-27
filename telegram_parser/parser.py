import logging
import time
from urllib.parse import urlparse
from telethon import TelegramClient, errors
from transformers import pipeline
from qrcode import QRCode
import getpass
from decouple import config
from .models import TelegramPost, TelegramComment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== Telegram ==================

API_ID = config("API_ID", cast=int)
API_HASH = config("API_HASH")

# ================== ML ==================

sentiment_pipeline = pipeline(
    model="seara/rubert-tiny2-russian-sentiment",
)
BATCH_SIZE = 128

# ================== Utils ==================

def parse_telegram_post_url(url: str):

    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")

    if not parts or len(parts) < 2:
        raise ValueError("Неверная ссылка Telegram")

    chat_id = parts[0]  # username
    post_id = int(parts[1])

    return chat_id, post_id

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
        sentiment = result["label"].lower()

        sender = comment.sender

        username = getattr(sender, "username", None)
        phone = getattr(sender, "phone", None)
        name = getattr(sender, "first_name", None)

        results.append({
            "sender_username": username or "Unknown",
            "sender_phone": phone or "Unknown",
            "sender_name": name or "Unknown",
            "comment_id": comment.id,
            "text": comment.text,
            "date": comment.date,
            "sentiment": sentiment,
        })
    return results

# ================== QR Utils ==================

qr = QRCode()

def display_qr(url: str):
    qr.clear()
    qr.add_data(url)
    qr.print_ascii()
    print("Сканируй QR-код в Telegram")

# ================== Telegram Client ==================

async def get_client():

    client = TelegramClient('session', API_ID, API_HASH)

    await client.connect()

    if await client.is_user_authorized():
        return client

    qr = await client.qr_login()
    while True:
        display_qr(qr.url)  
        try:
            await qr.wait()
            break
        except errors.SessionPasswordNeededError:
            password = getpass.getpass("2FA: ")
            await client.sign_in(password=password)
            break
        except Exception as e:
            print(f"Ошибка: {e}, пересоздаю QR")
            qr = await qr.recreate()

    return client

# ================== Main ==================

async def fetch_comments(channel_id, post_id, request):
    """
    Скачивает комментарии к посту и сохраняет их в базу.
    Создание поста в базе происходит только после успешного парсинга комментариев.
    """

    async with await get_client() as client:
        logger.info(f"[START] Fetching comments {channel_id}/{post_id}")

        buffer = []
        all_results = []

        # Получаем entity канала
        entity = await client.get_entity(channel_id)

        try:
            async for message in client.iter_messages(
                entity=entity,
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

        except Exception as e:
            logger.error(f"Error while fetching messages: {e}")
            return [] 

        logger.info(f"[END] Done. Fetched {len(all_results)} comments")

        post, created = await TelegramPost.objects.aget_or_create(
            channel=channel_id,
            post_id=post_id
        )

        await post.parsed_by.aadd(request.user)
        await post.asave()

        comments_to_create = [
            TelegramComment(
                post=post,
                comment_id=result["comment_id"],
                username=result["sender_username"],
                phone=result["sender_phone"],
                name=result["sender_name"],
                text=result["text"],
                date=result["date"],
                sentiment=result["sentiment"],
            )
            for result in all_results
        ]

        await TelegramComment.objects.abulk_create(
            comments_to_create,
            update_conflicts=True,
            unique_fields=['post', 'comment_id'],
            update_fields=['username', 'phone', 'name', 'text', 'date', 'sentiment']
        )

    return all_results
