from app.utils.text_models import mention


def send_level_up_notifications(bot, chat_id: int, level_ups: dict, meta: dict) -> None:
    if not level_ups:
        return

    for uid_s, info in level_ups.items():
        try:
            uid = int(uid_s)
        except Exception:
            continue

        m = meta.get(str(uid), {}) if meta else {}
        name = m.get("name") or (("@" + m["username"]) if m.get("username") else str(uid))
        gained = int(info.get("gained") or 0)
        level = int(info.get("level") or 0)

        # Group message
        try:
            bot.send_message(
                chat_id,
                f"Level up: {mention(uid, name)} +{gained} -> level {level}",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            pass

        # Private message
        try:
            bot.send_message(
                uid,
                f"Level up! You reached level {level} (+{gained}).",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            pass
