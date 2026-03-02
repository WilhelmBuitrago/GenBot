import logging
import os
from typing import Optional, Set

import discord
from discord import app_commands
from discord.ext import commands
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


def normalize_base_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    return url.rstrip("/")


def build_chat_url(base_url: str) -> str:
    base = normalize_base_url(base_url)
    if not base:
        return base
    if base.endswith("/chat"):
        return base
    return f"{base}/chat"


def build_prices_url(base_url: str) -> str:
    base = normalize_base_url(base_url)
    if not base:
        return base
    if base.endswith("/prices"):
        return base
    return f"{base}/prices"


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


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
http_client = httpx.AsyncClient(timeout=API_TIMEOUT)
allowed_channels = parse_id_set(ALLOWED_CHANNEL_IDS)
allowed_users = parse_id_set(ALLOWED_USER_IDS)
blocked_channels = parse_id_set(BLOCKED_CHANNEL_IDS)
blocked_users = parse_id_set(BLOCKED_USER_IDS)


@bot.event
async def on_ready() -> None:
    await tree.sync()
    logger.info("Logged in as %s", bot.user)


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return
    if not message.content or not message.content.strip():
        return
    if len(message.content) > 2000:
        await message.channel.send("El mensaje excede el maximo de 2000 caracteres.")
        return
    if not should_process_message(
        message.channel.id,
        message.author.id,
        allowed_channels,
        allowed_users,
        blocked_channels,
        blocked_users,
    ):
        return

    payload = {
        "user_id": f"discord:{message.author.id}",
        "message": message.content,
    }
    headers = {}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    try:
        response = await http_client.post(
            build_chat_url(CHAT_API_URL), json=payload, headers=headers
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
        await message.channel.send("No pude conectar con el servicio en este momento.")
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        await message.channel.send("Ocurrio un error inesperado.")

    await bot.process_commands(message)


@tree.command(name="prices", description="Obtener tabla de precios")
@app_commands.describe(
    region="Filtrar por region",
    service="Filtrar por servicio",
)
async def prices(
    interaction: discord.Interaction,
    region: Optional[str] = None,
    service: Optional[str] = None,
) -> None:
    await interaction.response.defer()
    headers = {}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    params = {}
    if region:
        params["region"] = region
    if service:
        params["service"] = service

    try:
        response = await http_client.get(
            build_prices_url(CHAT_API_URL), params=params, headers=headers
        )
        if response.status_code != 200:
            logger.warning("API error %s: %s", response.status_code, response.text)
            await interaction.followup.send(
                "No pude obtener los precios en este momento."
            )
            return

        data = response.json().get("prices", [])
        if not data:
            await interaction.followup.send("No se encontraron precios.")
            return

        embed = discord.Embed(title="Tabla de Precios", color=discord.Color.blue())
        for item in data:
            item_service = str(item.get("service", "")).strip() or "Sin servicio"
            item_region = str(item.get("region", "")).strip()
            item_price = str(item.get("price", "")).strip() or "0"
            item_description = str(item.get("description", "")).strip()

            detail = item_region or item_description or "Sin detalle"
            value_lines = [f"{item_price} USD"]
            if item_region and item_description and item_description != item_region:
                value_lines.append(item_description)
            embed.add_field(
                name=f"{item_service} ({detail})",
                value="\n".join(value_lines),
                inline=False,
            )

        await interaction.followup.send(embed=embed)
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("Request error: %s", exc)
        await interaction.followup.send(
            "No pude conectar con el servicio en este momento."
        )
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        await interaction.followup.send("Ocurrio un error inesperado.")


async def start_bot() -> None:
    if not TOKEN:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN")
    if not CHAT_API_URL:
        raise RuntimeError("Missing CHAT_API_URL")

    try:
        await bot.start(TOKEN)
    finally:
        await http_client.aclose()
