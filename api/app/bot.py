import logging
import os
from typing import Optional, Set

import discord
import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("genbot-discord")

TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
CHAT_API_URL = os.getenv("CHAT_API_URL", "http://api:3000").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
API_TIMEOUT = float(os.getenv("CHAT_API_TIMEOUT", "15"))

ALLOWED_CHANNEL_IDS = os.getenv("ALLOWED_CHANNEL_IDS", "")
ALLOWED_USER_IDS = os.getenv("ALLOWED_USER_IDS", "")
BLOCKED_CHANNEL_IDS = os.getenv("BLOCKED_CHANNEL_IDS", "")
BLOCKED_USER_IDS = os.getenv("BLOCKED_USER_IDS", "")


def parse_id_set(raw: str) -> Set[int]:
    items = [item.strip() for item in raw.split(",") if item.strip()]
    result: Set[int] = set()
    for item in items:
        try:
            result.add(int(item))
        except ValueError:
            logger.warning("Ignoring invalid ID: %s", item)
    return result


def normalize_chat_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    url = url.rstrip("/")
    if url.endswith("/chat"):
        return url
    return f"{url}/chat"


def should_process_message(
    channel_id: int,
    user_id: int,
    allowed_channels: Set[int],
    allowed_users: Set[int],
    blocked_channels: Set[int],
    blocked_users: Set[int],
) -> bool:
    if channel_id in blocked_channels or user_id in blocked_users:
        return False
    if allowed_channels and channel_id not in allowed_channels:
        return False
    if allowed_users and user_id not in allowed_users:
        return False
    return True


def split_message(text: str, limit: int = 2000) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        chunks.append(text[start:end])
        start = end
    return chunks


class GenBotClient(discord.Client):
    def __init__(self, *, chat_url: str, api_key: str, timeout: float) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.chat_url = normalize_chat_url(chat_url)
        self.api_key = api_key
        self.http_client = httpx.AsyncClient(timeout=timeout)
        self.allowed_channels = parse_id_set(ALLOWED_CHANNEL_IDS)
        self.allowed_users = parse_id_set(ALLOWED_USER_IDS)
        self.blocked_channels = parse_id_set(BLOCKED_CHANNEL_IDS)
        self.blocked_users = parse_id_set(BLOCKED_USER_IDS)

    async def close(self) -> None:
        await self.http_client.aclose()
        await super().close()

    async def on_ready(self) -> None:
        logger.info("Logged in as %s", self.user)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not message.content or not message.content.strip():
            return
        if len(message.content) > 2000:
            await message.channel.send(
                "El mensaje excede el maximo de 2000 caracteres."
            )
            return
        if not should_process_message(
            message.channel.id,
            message.author.id,
            self.allowed_channels,
            self.allowed_users,
            self.blocked_channels,
            self.blocked_users,
        ):
            return

        payload = {
            "user_id": f"discord:{message.author.id}",
            "message": message.content,
        }
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = await self.http_client.post(
                self.chat_url, json=payload, headers=headers
            )
            if response.status_code != 200:
                logger.warning("API error %s: %s", response.status_code, response.text)
                await message.channel.send(
                    "No pude obtener respuesta del servicio en este momento."
                )
                return
            data = response.json()
            text = data.get("response", "")
            if not text:
                await message.channel.send("No se recibio una respuesta valida.")
                return
            for chunk in split_message(text):
                await message.channel.send(chunk)
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            logger.warning("Request error: %s", exc)
            await message.channel.send(
                "No pude conectar con el servicio en este momento."
            )
        except Exception as exc:
            logger.exception("Unexpected error: %s", exc)
            await message.channel.send("Ocurrio un error inesperado.")


async def start_bot() -> None:
    if not TOKEN:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN")
    if not CHAT_API_URL:
        raise RuntimeError("Missing CHAT_API_URL")

    client = GenBotClient(
        chat_url=CHAT_API_URL, api_key=LLM_API_KEY, timeout=API_TIMEOUT
    )
    await client.start(TOKEN)
