"""The persona's own custom emojis (named like miyu_happy / miyu_happy_anim).

They come from the bot's application emojis (Developer Portal -> Emojis, usable in every server)
and from each server's emoji list. The AI writes them as :name: and render() turns that into the real emoji.
"""
import logging
import re
import discord

logger = logging.getLogger("Emojis")

PREFIX = "miyu_"
MAX_PER_MESSAGE = 2

_app: dict[str, str] = {}               # {name: "<:name:id>"} from the application
_guild: dict[int, dict[str, str]] = {}  # {guild_id: {name: "<:name:id>"}}


def _ours(emojis) -> dict[str, str]:
    return {e.name.lower(): str(e) for e in emojis if e.name.lower().startswith(PREFIX) and getattr(e, "available", True)}


async def refresh(bot: discord.Client):
    global _app
    try:
        _app = _ours(await bot.fetch_application_emojis())
    except (discord.HTTPException, AttributeError) as e:
        logger.warning(f"Couldn't load application emojis: {e}")
    for guild in bot.guilds:
        refresh_guild(guild)
    logger.info(f"Persona emojis: {len(_app)} from the app, "
                + ", ".join(f"{len(v)} in {g}" for g, v in _guild.items()))


def refresh_guild(guild: discord.Guild):
    _guild[guild.id] = _ours(guild.emojis)


def available(guild_id: int | None) -> dict[str, str]:
    found = dict(_app)
    found.update(_guild.get(guild_id, {}))  # the server's own copy wins
    return found


def describe(name: str) -> str:
    mood = name[len(PREFIX):].replace("_anim", "").replace("_", " ")
    return f":{name}: ({mood}{', animated' if name.endswith('_anim') else ''})"


def prompt_rule(guild_id: int | None) -> str:
    """Tells the AI which of her emojis exist and when to use them; empty if there are none."""
    names = sorted(available(guild_id))
    if not names:
        return ""
    return (
        "- You have your own custom emojis (pictures of you). Use one when it matches the feeling of your reply, "
        "like a person would: a greeting -> wave, happy news -> cheering or sparkle, love for your owner -> love_hug or "
        "heart_eyes, teasing -> wink_heart or giggle, confusion -> thinking or curious, sad -> crying or sad_cat, "
        f"surprise -> shocked. Write it exactly as :name:, at most {MAX_PER_MESSAGE} per message, usually at the end. "
        "Skip them for serious or very short factual replies. Prefer the animated version for big emotions. "
        "Only these exist: " + ", ".join(describe(n) for n in names)
    )


_TOKEN = re.compile(r"<a?:\w+:\d+>|:([A-Za-z0-9_]{2,32}):")


def render(text: str, guild_id: int | None) -> str:
    """Turns :miyu_x: into the real emoji; drops made-up ones and any beyond the limit."""
    found = available(guild_id)
    used = 0

    def swap(m: re.Match) -> str:
        nonlocal used
        name = m.group(1)
        if name is None:              # already a real <:name:id> emoji
            return m.group(0)
        key = name.lower()
        if not key.startswith(PREFIX):
            return m.group(0)         # some other :text:, leave it
        if key not in found or used >= MAX_PER_MESSAGE:
            return ""
        used += 1
        return found[key]

    return re.sub(r"[ \t]{2,}", " ", _TOKEN.sub(swap, text)).strip()
