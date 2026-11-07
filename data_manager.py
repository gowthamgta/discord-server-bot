import os
import copy
import json
import threading
from config import STORAGE_FILE

# Re-entrant lock: helpers below call each other while holding it
_lock = threading.RLock()
_cache = None  # In-memory copy of the JSON file, loaded once

DEFAULT_GUILD_DATA = {
    "welcome_channel_id": None,
    "welcome_enabled": True,
    "autorole_id": None,
    "leave_channel_id": None,
    "log_channel_id": None,
    "ticket_category_id": None,
    "ticket_count": 0,
    "mod_role_id": None,
    "banned_words": ["badword1", "discord.gg/"],
    "anti_invite": True,
    "anti_spam": True,
    "chatter_enabled": True,
    "chatter_chance": 8,
    "chatter_channel_id": None,
    "owner_rules": [],  # standing orders from the owner that the AI always follows
    "warnings": {},  # user_id (str): [{"reason": "...", "moderator": "...", "time": "..."}]
    # Leveling
    "xp_enabled": True,
    "levelup_channel_id": None,
    "level_rewards": {},  # level (str): role_id
    "color_role_ids": [],  # name-color roles; a member may hold only one
    "levels": {},  # user_id (str): {"xp": int, "level": int}
    # Community
    "suggestion_channel_id": None,
    "verify_role_id": None,
    "afk": {},  # user_id (str): {"reason": "...", "since": ts}
    "reminders": [],  # [{"id", "user_id", "channel_id", "due", "text"}]
    "giveaways": {},  # message_id (str): {...}
    # Voice
    "tempvoice_hub_id": None,
    "tempvoice_channels": [],
    "stats_channels": {},  # "members" | "humans" | "bots": channel_id
}


def _load():
    global _cache
    if _cache is None:
        if os.path.exists(STORAGE_FILE):
            try:
                with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                    _cache = json.load(f)
            except Exception:
                _cache = {}
        else:
            _cache = {}
    return _cache


def load_data():
    with _lock:
        return _load()


def save_raw(data=None):
    """Atomically write data (defaults to the cache) to disk."""
    global _cache
    with _lock:
        if data is not None:
            _cache = data
        tmp_path = STORAGE_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(_load(), f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, STORAGE_FILE)


def save():
    save_raw()


def get_guild_data(guild_id: int):
    """Returns the live settings dict for a guild. Mutate it, then call save()."""
    gid = str(guild_id)
    with _lock:
        data = _load()
        modified = False
        if gid not in data:
            data[gid] = copy.deepcopy(DEFAULT_GUILD_DATA)
            modified = True
        else:
            # Fill missing keys if any were added later
            for k, v in DEFAULT_GUILD_DATA.items():
                if k not in data[gid]:
                    data[gid][k] = copy.deepcopy(v)
                    modified = True
        if modified:
            save_raw()
        return data[gid]


def update_guild_data(guild_id: int, key: str, value):
    with _lock:
        get_guild_data(guild_id)[key] = value
        save_raw()


def add_warning(guild_id: int, user_id: int, reason: str, moderator_name: str, timestamp_str: str):
    uid = str(user_id)
    with _lock:
        warnings = get_guild_data(guild_id).setdefault("warnings", {})
        user_warns = warnings.setdefault(uid, [])
        user_warns.append({
            "id": len(user_warns) + 1,
            "reason": reason,
            "moderator": moderator_name,
            "timestamp": timestamp_str
        })
        save_raw()
        return len(user_warns)


def get_warnings(guild_id: int, user_id: int):
    with _lock:
        return list(get_guild_data(guild_id).get("warnings", {}).get(str(user_id), []))


def clear_warnings(guild_id: int, user_id: int):
    uid = str(user_id)
    with _lock:
        warnings = get_guild_data(guild_id).get("warnings", {})
        if uid in warnings:
            count = len(warnings.pop(uid))
            save_raw()
            return count
    return 0


def all_guild_ids():
    with _lock:
        return [int(gid) for gid in _load().keys()]
