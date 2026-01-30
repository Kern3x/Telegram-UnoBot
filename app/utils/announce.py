from app.utils.text_models import mention


def podium_lines(state: dict) -> list[str]:
    placements = state.get("placements") or []
    meta = state.get("player_meta", {}) or {}
    rewards = state.get("rewards") or {}
    min_range = state.get("rewards_min_range") or {}

    def display(x_uid: int) -> str:
        m = meta.get(str(x_uid), {})
        name = m.get("name") or (
            ("@" + m["username"]) if m.get("username") else str(x_uid)
        )
        return mention(x_uid, name)

    lines = ["🏁 <b>Гру завершено!</b>\n"]
    medals = ["🥇 ", "🥈 ", "🥉 "]
    for i, uid in enumerate(placements[:3]):
        r = rewards.get(int(uid)) or rewards.get(str(uid)) or {}
        c = r.get("coins")
        x = r.get("xp")
        bonus = ""
        if c is not None and x is not None:
            bonus = f" (+{c} 💰, +{x} 🧩)"
        lines.append(f"{medals[i]}{display(int(uid))}{bonus}")

    if len(placements) > 3:
        coins_rng = min_range.get("coins") or ()
        xp_rng = min_range.get("xp") or ()
        if coins_rng and xp_rng:
            lines.append(
                f"Іншим гравцям: +{coins_rng[0]}..{coins_rng[1]} 💰, +{xp_rng[0]}..{xp_rng[1]} 🧩"
            )
    return lines


def announce_after_move(
    bot, kb, chat_id: int, played_uid: int, state: dict, svc, settings
) -> None:
    players = state.get("players") or []
    meta = state.get("player_meta", {}) or {}

    finished = str(state.get("status") or "").lower() == "finished"

    def display(x_uid: int) -> str:
        m = meta.get(str(x_uid), {})
        name = m.get("name") or (
            ("@" + m["username"]) if m.get("username") else str(x_uid)
        )
        return mention(x_uid, name)

    cur_uid = None
    if players and not finished:
        try:
            cur_uid = int(svc.current_player_id(state))
        except Exception:
            cur_uid = None
    top = state.get("top_card") or {}
    cur_color = state.get("current_color")

    color = settings.colors.get(cur_color, cur_color)
    top_color = settings.colors.get(top.get("color", ""), top.get("color", ""))

    if top.get("color") in ["wild", "p4"]:
        top_color = ""

    kind = settings.other_type_cards.get(top.get("kind", ""), "")
    top_value = top.get("value") or ""

    if kind in ["wild", "p4", "p2", "skip", "rev"]:
        kind = settings.other_type_cards.get(kind, "")

    if kind == "num":
        kind = ""

    # finished => показуємо переможця і не даємо інлайн-кнопок гри
    if finished:
        text = [
            *podium_lines(state),
            "",
            f"Last card: {kind} {top_value} {top_color}",
        ]
        bot.send_message(
            chat_id,
            "\n".join(text),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return

    text = [
        f"✅ Хід зробив: {display(played_uid)}",
        f"🃏 Верхня карта: {kind} {top_value} {top_color}\n",
        f"🎨 Поточний колір: <b>{color}</b>",
    ]
    if cur_uid:
        text.append(f"➡️ Далі хід: {display(cur_uid)}")

    bot.send_message(
        chat_id,
        "\n".join(text),
        parse_mode="HTML",
        reply_markup=kb.game.get_cards_kb(chat_id),
        disable_web_page_preview=True,
    )
