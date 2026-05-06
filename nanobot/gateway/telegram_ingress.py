"""Telegram ingress — secure multi-tenant message routing.

Linking flow:
  1. Authenticated user clicks "Link Telegram" on the web account page.
  2. Gateway generates a one-time signed token and returns a deep link:
       https://t.me/<bot>?start=lnk_<token>
  3. User clicks → Telegram opens → bot receives /start lnk_<token>.
  4. Ingress calls POST /v1/channel/redeem-link → gateway validates token
     and creates the channel_link row in Postgres.
  5. Subsequent messages from that chat_id route to the correct tenant.

Nobody can chat without first linking their account via the web UI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from loguru import logger

SIGNUP_URL = os.environ.get("HEALTHCLAW_SIGNUP_URL", "http://localhost:8080/signup")


@dataclass(slots=True)
class TelegramIngressConfig:
    telegram_bot_token: str
    gateway_base_url: str
    api_key: str


def _headers(cfg: TelegramIngressConfig) -> dict:
    return {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}


async def _redeem_link_token(
    cfg: TelegramIngressConfig, *, token: str, chat_id: int
) -> tuple[bool, str]:
    """Redeem a /start deep-link token. Returns (ok, detail)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"{cfg.gateway_base_url}/v1/channel/redeem-link",
                json={"token": token, "channel": "telegram", "external_id": str(chat_id)},
                headers=_headers(cfg),
            )
            data = res.json()
            if res.status_code == 200:
                return True, "ok"
            return False, data.get("detail", "unknown_error")
    except Exception:
        logger.exception("redeem_link_token failed for chat_id={}", chat_id)
        return False, "gateway_error"


async def _call_gateway(
    cfg: TelegramIngressConfig, *, chat_id: int, text: str
) -> str | None:
    """Send a message to the gateway. Returns the reply text, or None if unlinked."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(
                f"{cfg.gateway_base_url}/v1/channel/message",
                json={
                    "channel": "telegram",
                    "chat_id": str(chat_id),
                    "content": text,
                    "wait": True,
                },
                headers=_headers(cfg),
            )
            res.raise_for_status()
            data = res.json()
            # Gateway returns {"content": "..."} when routed, or a special status
            return str(data.get("content") or "")
    except Exception:
        logger.exception("gateway call failed for chat_id={}", chat_id)
        return None


def run() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    cfg = TelegramIngressConfig(
        telegram_bot_token=token,
        gateway_base_url=os.environ.get(
            "NANOBOT_GATEWAY_URL", "http://gateway:8080"
        ).strip(),
        api_key=os.environ.get("NANOBOT_API_KEY", "").strip(),
    )

    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )

    async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start — with or without a link token."""
        if not update.effective_chat:
            return
        chat_id = int(update.effective_chat.id)

        # /start lnk_<token>  →  attempt to link
        raw_token = (context.args[0] if context.args else "").strip()
        if raw_token.startswith("lnk_"):
            ok, detail = await _redeem_link_token(cfg, token=raw_token, chat_id=chat_id)
            if ok:
                await update.message.reply_text(
                    "✅ Your Telegram is now linked to your Healthclaw account!\n\n"
                    "Send me any message and your companion will respond."
                )
            elif detail == "token_already_used":
                await update.message.reply_text(
                    "⚠️ That link has already been used.\n"
                    "Go back to your account page and generate a new one."
                )
            elif detail == "token_expired":
                await update.message.reply_text(
                    "⏱️ That link has expired (15-minute limit).\n"
                    "Go back to your account page and generate a fresh link."
                )
            else:
                await update.message.reply_text(
                    "❌ Couldn't link — the token wasn't recognised.\n"
                    f"Detail: {detail}\n\n"
                    "Try generating a new link from your account page."
                )
            return

        # /start with no token  →  show signup instructions
        await update.message.reply_text(
            "👋 Welcome to Healthclaw!\n\n"
            "To use this bot you need a Healthclaw account.\n\n"
            f"➡️ Sign up at: {SIGNUP_URL}\n\n"
            "After signing up, go to your account page and click "
            "\"Link Telegram\" — you'll get a link that connects this chat "
            "to your account automatically."
        )

    async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Route a regular message to the correct tenant, or reject if unlinked."""
        if not update.effective_chat or not update.message or not update.message.text:
            return
        chat_id = int(update.effective_chat.id)

        try:
            await update.message.reply_chat_action("typing")
            reply = await _call_gateway(
                cfg, chat_id=chat_id, text=update.message.text.strip()
            )

            if reply is None:
                # Gateway error
                await update.message.reply_text(
                    "Sorry, I couldn't reach the server. Please try again in a moment."
                )
            elif reply == "":
                # Linked but no content returned
                pass
            else:
                await update.message.reply_text(reply)

        except Exception as exc:
            logger.exception("on_message error for chat_id={}", chat_id)
            try:
                await update.message.reply_text(f"Sorry, something went wrong: {exc}")
            except Exception:
                pass

    app = Application.builder().token(cfg.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    logger.info(
        "Telegram ingress started → {}  (signup URL: {})",
        cfg.gateway_base_url,
        SIGNUP_URL,
    )
    app.run_polling(close_loop=False)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
