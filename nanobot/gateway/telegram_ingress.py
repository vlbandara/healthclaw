from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from loguru import logger


@dataclass(slots=True)
class TelegramIngressConfig:
    telegram_bot_token: str
    gateway_base_url: str = "http://gateway:8080"
    api_key: str = ""


async def _call_gateway(cfg: TelegramIngressConfig, *, chat_id: int, text: str) -> str:
    headers = {}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    payload = {
        "tenant_external_id": f"telegram:{chat_id}",
        "session_key": f"telegram:{chat_id}",
        "channel": "telegram",
        "chat_id": str(chat_id),
        "content": text,
        "wait": True,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        res = await client.post(f"{cfg.gateway_base_url}/v1/turn", json=payload, headers=headers)
        res.raise_for_status()
        data = res.json()
        return str(data.get("content") or "")


async def _redeem_onboarding_token(cfg: TelegramIngressConfig, *, chat_id: int, token: str) -> str:
    headers = {}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    payload = {"token": token, "channel": "telegram", "chat_id": str(chat_id)}
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(f"{cfg.gateway_base_url}/v1/onboarding/redeem", json=payload, headers=headers)
        if res.status_code >= 400:
            try:
                data = res.json()
                detail = data.get("detail") or res.text
            except Exception:
                detail = res.text
            return f"Couldn’t link that setup token ({detail}). Open the link again from the onboarding page."
        return "Linked. Say hi and we’ll start."


def run() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    cfg = TelegramIngressConfig(
        telegram_bot_token=token,
        gateway_base_url=os.environ.get("NANOBOT_GATEWAY_URL", "http://gateway:8080").strip(),
        api_key=os.environ.get("NANOBOT_API_KEY", "").strip(),
    )

    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

    async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            if not update.effective_chat or not update.message or not update.message.text:
                return
            chat_id = int(update.effective_chat.id)
            user_text = update.message.text
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            out = await _call_gateway(cfg, chat_id=chat_id, text=user_text)
            if not out:
                out = "(empty)"
            await context.bot.send_message(chat_id=chat_id, text=out)
        except Exception as exc:
            logger.exception("telegram ingress error")
            if update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"Sorry, I hit an error: {exc}",
                )

    async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            if not update.effective_chat:
                return
            chat_id = int(update.effective_chat.id)
            token = ""
            if context.args:
                token = str(context.args[0] or "").strip()
            if not token:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Send me your setup link token (open the Healthclaw onboarding page and tap Telegram).",
                )
                return
            msg = await _redeem_onboarding_token(cfg, chat_id=chat_id, token=token)
            await context.bot.send_message(chat_id=chat_id, text=msg)
        except Exception:
            logger.exception("telegram ingress start error")

    app = Application.builder().token(cfg.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    logger.info("Telegram ingress started. Forwarding to {}", cfg.gateway_base_url)
    # python-telegram-bot Application.run_polling() is a blocking call (not awaitable).
    app.run_polling(close_loop=False)


def main() -> None:
    run()


if __name__ == "__main__":
    main()

