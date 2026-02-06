import os
from aiogram import Bot

import logging

logger = logging.getLogger(__name__)


class TelegramBot:
    """Cliente de bot de Telegram con aiogram."""

    def __init__(self):
        """
        Inicializar bot de Telegram.

        Args:
            token: Token del bot de Telegram
        """
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if token and chat_id:
            try:
                self._telegram_bot = Bot(token=token)
                self._telegram_chat_id = chat_id
                logger.info("✅ Telegram notifications enabled")
            except Exception as e:
                logger.warning(f"Failed to setup Telegram bot: {e}")
        else:
            logger.info("ℹ️ Telegram notifications disabled (no credentials)")

    async def send_message(self, message: str) -> None:
        """Send notification via Telegram if bot is configured."""
        if self._telegram_bot and self._telegram_chat_id:
            try:
                await self._telegram_bot.send_message(
                    chat_id=self._telegram_chat_id, text=message, parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to send Telegram notification: {e}")
