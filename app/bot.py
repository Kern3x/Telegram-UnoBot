import logging

from telebot import TeleBot

from config import settings
from app.utils.db_manager import init_db
from app.handlers.message import (
    GameMessageHandler,
    UnoWordHandler,
    ProfileMessageHandler,
    BotAddedHandler,
)
from app.handlers.query import (
    GameLobbyQueryHandler,
    InlineHandQueryHandler,
    StickerMoveHandler,
    DrawCallbackHandler,
    ColorChoiceCallbackHandler,
    DumpAllCallbackHandler,
)
from app.handlers.commands import (
    StartCommandHandler,
    UnoStartCommandHandler,
    TopCommandHandler,
)
from app.workers.timers import set_bot
from app.workers.scheduler import start_scheduler
from app.utils.card_file_cache import ensure_sticker_set_cached


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot")


class TelegramBot:
    def __init__(self) -> None:
        self.bot = TeleBot(settings.BOT_TOKEN, parse_mode="HTML")

        start_scheduler()
        set_bot(self.bot)

        cache = ensure_sticker_set_cached(
            self.bot, getattr(settings, "STICKER_SET_NAME", "")
        )
        if not cache:
            raise RuntimeError("Failed to cache sticker set; check STICKER_SET_NAME.")

        self._register_handlers()

    def _register_handlers(self) -> None:
        # Initialize each class handler that registers its decorators internally
        StartCommandHandler(self.bot)
        UnoStartCommandHandler(self.bot)
        TopCommandHandler(self.bot)

        GameMessageHandler(self.bot)
        UnoWordHandler(self.bot)
        ProfileMessageHandler(self.bot)
        BotAddedHandler(self.bot)

        GameLobbyQueryHandler(self.bot)
        InlineHandQueryHandler(self.bot)
        StickerMoveHandler(self.bot)
        DrawCallbackHandler(self.bot)
        ColorChoiceCallbackHandler(self.bot)
        DumpAllCallbackHandler(self.bot)

    def start(self) -> None:
        init_db()  # models already imported — tables will be created

        logger.info("TeleBot started…")

        self.bot.remove_webhook()

        self.bot.infinity_polling(
            skip_pending=True,
            timeout=20,
            long_polling_timeout=25,
            allowed_updates=[
                "message",
                "callback_query",
                "inline_query",
                "chosen_inline_result",
                "my_chat_member",
            ],
        )
