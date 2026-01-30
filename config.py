import os
from dotenv import load_dotenv


load_dotenv()


class Settings:
    BOT_TOKEN: str = os.getenv("TOKEN", "your-bot-token-here")
    DB_URL: str = os.getenv("DATABASE_URL", "sqlite:///./uno_bot.db")

    TURN_SECONDS = 30
    UNO_SECONDS = 10

    ADD_GROUP_BOT_URL = "https://t.me/test_uno_ua_bot?startgroup&admin=delete_messages+restrict_members+pin_messages+manage_topics"
    STICKER_SET_NAME = "UnoUaBot"

    REWARD_TOP1_COINS_RANGE = (80, 120)
    REWARD_TOP2_COINS_RANGE = (50, 80)
    REWARD_TOP3_COINS_RANGE = (30, 50)
    REWARD_MIN_COINS_RANGE = (10, 20)

    REWARD_TOP1_XP_RANGE = (60, 100)
    REWARD_TOP2_XP_RANGE = (40, 70)
    REWARD_TOP3_XP_RANGE = (25, 45)
    REWARD_MIN_XP_RANGE = (5, 15)

    if not BOT_TOKEN:
        raise RuntimeError("TOKEN not set in .env")

    if not DB_URL:
        raise RuntimeError("DATABASE_URL not set in .env")
    
    colors: dict = {
        "red": "🔴",
        "yellow": "🟡",
        "green": "🟢",
        "blue": "🔵",
    }

    other_type_cards: dict = {
        "skip": "Пропуск ходу",
        "rev": "Зворотній напрямок",
        "p2": "+2",
        "wild": "Зміна кольору",
        "p4": "+4",
    }


settings = Settings()
