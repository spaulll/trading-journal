"""Published Telegram command menu (Phase 8).

The bot owns the menu it registers with Telegram; the UI reads the same
list here instead of hard-coding a second copy that would drift.
"""

from fastapi import APIRouter

from app.services import telegram_bot

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.get("/commands")
def list_commands():
    """What the bot understands, as published to Telegram."""
    return {
        "configured": telegram_bot.is_configured(),
        "commands": telegram_bot.COMMAND_MENU,
    }
