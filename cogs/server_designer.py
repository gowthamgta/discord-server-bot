import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import json
import logging
import re
from typing import Literal
from config import EMBED_COLOR_SUCCESS, EMBED_COLOR_DEFAULT, EMBED_COLOR_ERROR, EMBED_COLOR_WARNING, EMBED_COLOR_AI
import data_manager
from checks import is_guild_owner
from rate_limiter import gemini_queue
from cogs.tickets import TicketPanelView
from cogs.roles import build_selfrole_view, build_color_view, VerifyView, is_safe_self_role
from cogs.voice import create_stats_channels

logger = logging.getLogger("ServerDesigner")

# Channel "purpose" values wire a channel into a bot feature after it is built
PURPOSES = {
    "welcome", "rules", "announcements", "log", "ticket", "verify", "roles",
    "suggestions", "levelup", "ai_chat", "tempvoice", "afk"
}

DEFAULT_RULES = [
    "Be respectful. No harassment, hate speech, or personal attacks.",
    "No spam, flooding, or unsolicited advertising (including DM ads).",
    "Keep content in the right channels and keep it SFW.",
    "No sharing of personal information — yours or anyone else's.",
    "Follow Discord's Terms of Service and Community Guidelines.",
    "Staff decisions are final. Open a ticket if you need help or want to appeal."
]

TEMPLATES = {
    "gaming": {
        "name": "🎮 Gaming & Community",
        "description": "Full-featured setup for gaming clans, stream communities, and general hangouts.",
        "stats": True,
        "self_roles": [
            {"name": "🎯 FPS", "color": "#E74C3C"}, {"name": "⚔️ MOBA", "color": "#9B59B6"},
            {"name": "🧱 Sandbox", "color": "#2ECC71"}, {"name": "🏎️ Racing", "color": "#F39C12"},
            {"name": "📢 Event Pings", "color": "#3498DB"}, {"name": "🎁 Giveaway Pings", "color": "#E91E63"}
        ],
        "categories": [
            {
                "name": "📌 ─── INFORMATION ───",
                "channels": [
                    {"name": "✅・verify", "type": "text", "purpose": "verify", "topic": "Click the button to get access to the server."},
                    {"name": "📜・rules-and-info", "type": "text", "read_only": True, "purpose": "rules", "topic": "Server rules and general guidelines."},
                    {"name": "📢・announcements", "type": "text", "read_only": True, "purpose": "announcements", "topic": "Official server news and updates."},
                    {"name": "👋・welcome", "type": "text", "read_only": True, "purpose": "welcome", "topic": "New member arrival announcements."},
                    {"name": "🎭・pick-your-roles", "type": "text", "read_only": True, "purpose": "roles", "topic": "Grab roles for your games and pings."},
                    {"name": "🎁・giveaways-and-events", "type": "text", "topic": "Community events, tournaments, and giveaways."}
                ]
            },
            {
                "name": "💬 ─── GENERAL CHAT ───",
                "channels": [
                    {"name": "💬・general-chat", "type": "text", "topic": "Main hangout area for chatting with everyone."},
                    {"name": "🤖・bot-commands", "type": "text", "topic": "Use bot slash commands and games here."},
                    {"name": "🧠・ask-the-ai", "type": "text", "purpose": "ai_chat", "topic": "Chat with the AI — it replies to every message here."},
                    {"name": "🐸・memes-and-humor", "type": "text", "slowmode": 5, "topic": "Share memes, funny clips, and laughs."},
                    {"name": "📸・media-and-clips", "type": "text", "slowmode": 10, "topic": "Post screenshots, photos, art, and gameplay clips."},
                    {"name": "🆙・level-ups", "type": "text", "read_only": True, "purpose": "levelup", "topic": "Level-up announcements."},
                    {"name": "💡・suggestions", "type": "text", "read_only": True, "purpose": "suggestions", "topic": "Use /suggest to post an idea. Vote with reactions."}
                ]
            },
            {
                "name": "🎮 ─── GAMING & LFG ───",
                "channels": [
                    {"name": "🎯・looking-for-group", "type": "text", "topic": "Find teammates and squad up for games."},
                    {"name": "🏆・game-highlights", "type": "text", "topic": "Show off your best clutches and wins."}
                ]
            },
            {
                "name": "🔊 ─── VOICE LOUNGES ───",
                "channels": [
                    {"name": "➕・Create a Room", "type": "voice", "purpose": "tempvoice"},
                    {"name": "🔊・Lounge Alpha", "type": "voice"},
                    {"name": "🎮・Squad 1", "type": "voice"},
                    {"name": "🎮・Squad 2", "type": "voice"},
                    {"name": "💤・AFK", "type": "voice", "purpose": "afk"}
                ]
            },
            {
                "name": "🆘 ─── SUPPORT ───",
                "channels": [
                    {"name": "🎟️・open-a-ticket", "type": "text", "read_only": True, "purpose": "ticket", "topic": "Click the button to open a private support ticket."}
                ]
            },
            {
                "name": "🛡️ ─── STAFF HEADQUARTERS ───",
                "staff_only": True,
                "channels": [
                    {"name": "🔒・staff-chat", "type": "text", "topic": "Private discussions for moderators and admins."},
                    {"name": "📋・mod-logs", "type": "text", "purpose": "log", "topic": "Automated server audit trail and moderation logs."},
                    {"name": "🔊・Staff Voice", "type": "voice"}
                ]
            }
        ]
    },
    "tech": {
        "name": "💻 Tech & Programming Hub",
        "description": "Tailored for software developers, engineers, and tech enthusiasts.",
        "stats": True,
        "self_roles": [
            {"name": "🐍 Python", "color": "#3776AB"}, {"name": "🌐 Web Dev", "color": "#F7DF1E"},
            {"name": "☁️ DevOps", "color": "#2496ED"}, {"name": "🤖 AI / ML", "color": "#8B5CF6"},
            {"name": "📢 Event Pings", "color": "#3498DB"}
        ],
        "categories": [
            {
                "name": "📌 ─── INFORMATION ───",
                "channels": [
                    {"name": "✅・verify", "type": "text", "purpose": "verify"},
                    {"name": "📜・rules-and-faq", "type": "text", "read_only": True, "purpose": "rules", "topic": "Community guidelines and FAQ."},
                    {"name": "📢・announcements", "type": "text", "read_only": True, "purpose": "announcements", "topic": "Tech community updates."},
                    {"name": "👋・welcome", "type": "text", "read_only": True, "purpose": "welcome", "topic": "Member welcomes."},
                    {"name": "🎭・roles", "type": "text", "read_only": True, "purpose": "roles", "topic": "Pick your stack."}
                ]
            },
            {
                "name": "💬 ─── TECH LOUNGE ───",
                "channels": [
                    {"name": "💬・general-dev", "type": "text", "topic": "General software engineering and tech discussion."},
                    {"name": "🚀・project-showcase", "type": "forum", "topic": "Show off projects, open source repos, and apps."},
                    {"name": "🧠・ai-assistant", "type": "text", "purpose": "ai_chat", "topic": "Ask the AI anything."},
                    {"name": "🤖・bot-commands", "type": "text", "topic": "Bot playground."},
                    {"name": "🆙・level-ups", "type": "text", "read_only": True, "purpose": "levelup"},
                    {"name": "💡・suggestions", "type": "text", "read_only": True, "purpose": "suggestions", "topic": "Use /suggest to post an idea."}
                ]
            },
            {
                "name": "💻 ─── PROGRAMMING ───",
                "channels": [
                    {"name": "🐍・python", "type": "text", "topic": "Python, automation, AI, and scripts."},
                    {"name": "🌐・web-and-frontend", "type": "text", "topic": "React, Vue, HTML, CSS, JavaScript, TypeScript."},
                    {"name": "⚙️・backend-and-cloud", "type": "text", "topic": "Databases, APIs, Docker, Kubernetes, AWS."},
                    {"name": "❓・code-help", "type": "forum", "topic": "Ask questions and get help debugging."}
                ]
            },
            {
                "name": "🔊 ─── VOICE COLLAB ───",
                "channels": [
                    {"name": "➕・Create a Room", "type": "voice", "purpose": "tempvoice"},
                    {"name": "🔊・Pair Programming", "type": "voice"},
                    {"name": "🎧・Study & Work Room", "type": "voice"}
                ]
            },
            {
                "name": "🆘 ─── SUPPORT ───",
                "channels": [
                    {"name": "🎟️・open-a-ticket", "type": "text", "read_only": True, "purpose": "ticket"}
                ]
            },
            {
                "name": "🛡️ ─── STAFF ───",
                "staff_only": True,
                "channels": [
                    {"name": "🔒・staff-chat", "type": "text"},
                    {"name": "📋・mod-logs", "type": "text", "purpose": "log"}
                ]
            }
        ]
    },
    "study": {
        "name": "📚 Study & Learning Group",
        "description": "Focused layout for study groups, classes, and learning communities.",
        "stats": True,
        "self_roles": [
            {"name": "🔢 Math", "color": "#E67E22"}, {"name": "🔬 Science", "color": "#1ABC9C"},
            {"name": "💻 Coding", "color": "#3498DB"}, {"name": "🗣️ Languages", "color": "#E91E63"},
            {"name": "⏰ Study Session Pings", "color": "#F1C40F"}
        ],
        "categories": [
            {
                "name": "📌 ─── START HERE ───",
                "channels": [
                    {"name": "📜・rules", "type": "text", "read_only": True, "purpose": "rules"},
                    {"name": "📢・announcements", "type": "text", "read_only": True, "purpose": "announcements"},
                    {"name": "👋・welcome", "type": "text", "read_only": True, "purpose": "welcome"},
                    {"name": "🎭・subjects", "type": "text", "read_only": True, "purpose": "roles", "topic": "Pick the subjects you study."}
                ]
            },
            {
                "name": "📚 ─── STUDY HALL ───",
                "channels": [
                    {"name": "💬・general", "type": "text"},
                    {"name": "❓・homework-help", "type": "forum", "topic": "Ask for help. Show your work!"},
                    {"name": "📝・notes-and-resources", "type": "forum", "topic": "Share notes, links, and study material."},
                    {"name": "🧠・ai-tutor", "type": "text", "purpose": "ai_chat", "topic": "Ask the AI tutor questions."},
                    {"name": "🎯・goals-and-progress", "type": "text", "topic": "Post daily goals and keep each other accountable."},
                    {"name": "🆙・level-ups", "type": "text", "read_only": True, "purpose": "levelup"},
                    {"name": "💡・suggestions", "type": "text", "read_only": True, "purpose": "suggestions"}
                ]
            },
            {
                "name": "🔊 ─── FOCUS ROOMS ───",
                "channels": [
                    {"name": "➕・Create a Room", "type": "voice", "purpose": "tempvoice"},
                    {"name": "🤫・Silent Study", "type": "voice"},
                    {"name": "🗣️・Group Study", "type": "voice"}
                ]
            },
            {
                "name": "🆘 ─── SUPPORT ───",
                "channels": [
                    {"name": "🎟️・contact-staff", "type": "text", "read_only": True, "purpose": "ticket"}
                ]
            },
            {
                "name": "🛡️ ─── STAFF ───",
                "staff_only": True,
                "channels": [
                    {"name": "🔒・staff-chat", "type": "text"},
                    {"name": "📋・logs", "type": "text", "purpose": "log"}
                ]
            }
        ]
    },
    "minimal": {
        "name": "✨ Clean & Minimalist",
        "description": "Clean, lightweight structure with only essential channels.",
        "stats": False,
        "self_roles": [],
        "categories": [
            {
                "name": "📌 ─── INFO ───",
                "channels": [
                    {"name": "📜・rules-and-news", "type": "text", "read_only": True, "purpose": "rules"},
                    {"name": "👋・welcome", "type": "text", "read_only": True, "purpose": "welcome"}
                ]
            },
            {
                "name": "💬 ─── GENERAL ───",
                "channels": [
                    {"name": "💬・general", "type": "text"},
                    {"name": "📸・media", "type": "text"},
                    {"name": "🤖・commands", "type": "text"}
                ]
            },
            {
                "name": "🔊 ─── VOICE ───",
                "channels": [
                    {"name": "🔊・General Voice 1", "type": "voice"},
                    {"name": "🔊・General Voice 2", "type": "voice"}
                ]
            },
            {
                "name": "🛡️ ─── MODERATION ───",
                "staff_only": True,
                "channels": [
                    {"name": "🔒・staff", "type": "text"},
                    {"name": "📋・logs", "type": "text", "purpose": "log"}
                ]
            }
        ]
    }
}

_MOD_PERMS = dict(kick_members=True, ban_members=True, manage_messages=True, moderate_members=True,
                  view_audit_log=True, manage_nicknames=True, manage_threads=True,
                  mute_members=True, deafen_members=True, move_members=True)

# Staff and special roles, highest first. Displayed name color = the highest colored role a member has.
STAFF_ROLES = [
    # The server owner already has every permission, so this role is purely a badge
    {"name": "👑 Owner", "color": (241, 196, 15), "perms": {}, "hoist": True},
    {"name": "🛡️ Admin", "color": (231, 76, 60), "perms": {"administrator": True}, "hoist": True},
    {"name": "🔨 Moderator", "color": (52, 152, 219), "perms": _MOD_PERMS, "hoist": True},
    # Trainee staff: clean up chat and time people out, but no kicks or bans
    {"name": "🧰 Helper", "color": (26, 188, 156), "perms": dict(manage_messages=True, moderate_members=True, manage_threads=True), "hoist": True},
    {"name": "🤖 Bots", "color": (155, 89, 182), "perms": {}, "hoist": True},
    {"name": "⭐ VIP", "color": (233, 30, 99), "perms": {}, "hoist": True},
]

# One-of-a-kind name colors members pick from a panel; they sit above level roles so the chosen color wins
COLOR_ROLES = [
    {"name": "🔴 Red", "color": "#E74C3C"}, {"name": "🟠 Orange", "color": "#E67E22"},
    {"name": "🟡 Yellow", "color": "#F1C40F"}, {"name": "🟢 Green", "color": "#2ECC71"},
    {"name": "🔵 Blue", "color": "#3498DB"}, {"name": "🟣 Purple", "color": "#9B59B6"},
    {"name": "🩷 Pink", "color": "#FF6FB5"}, {"name": "⚪ White", "color": "#ECF0F1"},
]

# Earned automatically through chat activity (wired into the leveling system), highest first
LEVEL_ROLES = [
    {"name": "💠 Legend", "color": "#00D2FF", "level": 50},
    {"name": "🥇 Veteran", "color": "#FFD700", "level": 30},
    {"name": "🥈 Regular", "color": "#C0C0C0", "level": 15},
    {"name": "🥉 Active", "color": "#CD7F32", "level": 5},
]

# Base role every verified member gets. No color, so color/level roles show instead; hoisted to list members.
MEMBER_ROLE = {"name": "👥 Member", "color": None, "perms": {}, "hoist": True}

AI_DESIGN_PROMPT = """You are an expert Discord server architect. Design a complete Discord server for this theme:
"{theme}"

Return ONLY a JSON object with exactly this shape:
{{
  "name": "short server style name with an emoji",
  "description": "one sentence, max 200 characters",
  "categories": [
    {{"name": "💬 ─── GENERAL ───", "staff_only": false, "channels": [
      {{"name": "💬・general-chat", "type": "text", "topic": "short topic", "read_only": false, "purpose": "none", "slowmode": 0}}
    ]}}
  ],
  "self_roles": [{{"name": "🎮 Gamer", "color": "#RRGGBB"}}],
  "rules": ["short rule", "..."]
}}

Requirements:
- 4 to 7 categories, 2 to 7 channels each. "type" is "text", "voice" or "forum".
- Use "forum" (1 or 2 per server) for organised posts like help/questions, showcases, guides or feedback.
- "slowmode" is seconds between messages per member: 5-10 for busy media/meme channels, 0 elsewhere.
- Name style: categories like "💬 ─── GENERAL ───"; text channels like "💬・general-chat" (lowercase, hyphens); voice channels like "🔊・Lounge".
- "purpose" is one of: none, rules, announcements, welcome, verify, roles, suggestions, levelup, ai_chat, ticket, log, tempvoice, afk.
- Include exactly one channel for each of these purposes: rules, announcements, welcome, roles, suggestions, levelup, ai_chat, ticket (a PUBLIC channel where members open support tickets).
- Rules, announcements, welcome, roles, suggestions, levelup and ticket channels must be read_only true.
- Include one voice channel with purpose "tempvoice" named "➕・Create a Room".
- Include one category with staff_only true containing a text channel with purpose "log" and a staff chat.
- 4 to 8 self_roles: interest or notification roles relevant to the theme (e.g. "📢 Event Pings"). No staff, level or color roles: the bot adds those itself.
- 5 to 8 concise, theme-appropriate rules.
- Make channels specific and useful for the theme, not generic filler."""


def _clean_name(value, fallback: str, limit: int = 100) -> str:
    text = str(value or "").strip()
    return text[:limit] if text else fallback


def _parse_color(value) -> discord.Color:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return discord.Color.from_rgb(*[max(0, min(255, int(c))) for c in value])
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(value or "").strip())
    return discord.Color(int(match.group(1), 16)) if match else discord.Color.light_grey()


def normalize_layout(raw: dict) -> dict:
    """Validates and clamps a template or AI-generated layout so it is safe to build."""
    if not isinstance(raw, dict):
        raise ValueError("Layout must be a JSON object.")

    layout = {
        "name": _clean_name(raw.get("name"), "Custom Design", 80),
        "description": _clean_name(raw.get("description"), "", 200),
        "stats": bool(raw.get("stats", True)),
        "self_roles": [],
        "rules": [],
        "categories": []
    }

    for r in (raw.get("self_roles") or [])[:10]:
        if isinstance(r, dict) and r.get("name"):
            layout["self_roles"].append({"name": _clean_name(r["name"], "Role", 50), "color": r.get("color")})

    layout["rules"] = [_clean_name(r, "", 300) for r in (raw.get("rules") or []) if str(r).strip()][:10] or list(DEFAULT_RULES)

    used_purposes = set()
    total_channels = 0
    for cat in (raw.get("categories") or [])[:10]:
        if not isinstance(cat, dict):
            continue
        new_cat = {"name": _clean_name(cat.get("name"), "📁 ─── CHANNELS ───"), "staff_only": bool(cat.get("staff_only")), "channels": []}
        for ch in (cat.get("channels") or [])[:10]:
            if not isinstance(ch, dict) or total_channels >= 60:
                continue
            raw_type = str(ch.get("type", "text")).lower()
            ch_type = raw_type if raw_type in ("voice", "forum") else "text"
            purpose = str(ch.get("purpose") or "none").lower()
            # Each purpose may only be wired once, and must match the channel type (forums take no purpose)
            voice_purposes = {"tempvoice", "afk"}
            if (purpose not in PURPOSES or purpose in used_purposes or ch_type == "forum"
                    or ((purpose in voice_purposes) != (ch_type == "voice"))):
                purpose = "none"
            if purpose != "none":
                used_purposes.add(purpose)
            name = _clean_name(ch.get("name"), "channel")
            if ch_type != "voice":
                name = name.replace(" ", "-").lower()
            try:
                slowmode = max(0, min(21600, int(ch.get("slowmode") or 0))) if ch_type != "voice" else 0
            except (TypeError, ValueError):
                slowmode = 0
            new_cat["channels"].append({
                "name": name,
                "type": ch_type,
                "topic": _clean_name(ch.get("topic"), "", 1024),
                "read_only": bool(ch.get("read_only")) and ch_type == "text",
                "purpose": purpose,
                "slowmode": slowmode
            })
            total_channels += 1
        if new_cat["channels"]:
            layout["categories"].append(new_cat)

    if not layout["categories"]:
        raise ValueError("Layout has no channels.")

    # Always guarantee a private staff area with a log channel
    if "log" not in used_purposes:
        layout["categories"].append({
            "name": "🛡️ ─── STAFF ───",
            "staff_only": True,
            "channels": [
                {"name": "🔒・staff-chat", "type": "text", "topic": "", "read_only": False, "purpose": "none"},
                {"name": "📋・mod-logs", "type": "text", "topic": "Automated audit logs.", "read_only": False, "purpose": "log"}
            ]
        })
    return layout


def layout_preview_embed(layout: dict, clean_existing: bool, verification: bool) -> discord.Embed:
    embed = discord.Embed(
        title=f"🏗️ Design Preview — {layout['name']}",
        description=(layout["description"] + "\n\n" if layout["description"] else "") + "Review the layout below, then press **Build** to apply it.",
        color=EMBED_COLOR_AI
    )
    for cat in layout["categories"][:20]:
        lines = []
        for ch in cat["channels"]:
            icon = {"voice": "🔊", "forum": "🗂️"}.get(ch["type"], "#")
            tags = ([ch["purpose"]] if ch["purpose"] != "none" else []) + ([f"slowmode {ch['slowmode']}s"] if ch.get("slowmode") else [])
            lines.append(f"{icon} {ch['name']}" + (f" *({', '.join(tags)})*" if tags else ""))
        title = cat["name"] + (" 🔒" if cat["staff_only"] else "")
        embed.add_field(name=title[:256], value="\n".join(lines)[:1024], inline=False)

    roles_lines = [
        "**Staff:** " + " › ".join(r["name"] for r in STAFF_ROLES[:4]),
        "**Special:** " + ", ".join(r["name"] for r in STAFF_ROLES[4:]),
        "**Name colors** (pick one): " + " ".join(r["name"].split(" ")[0] for r in COLOR_ROLES),
        "**Level rewards:** " + ", ".join(f"{r['name']} (lvl {r['level']})" for r in reversed(LEVEL_ROLES)),
        f"**Base:** {MEMBER_ROLE['name']}",
    ]
    if layout["self_roles"]:
        roles_lines.append("**Self-roles:** " + ", ".join(r["name"] for r in layout["self_roles"]))
    embed.add_field(name="🎭 Role Hierarchy (top → bottom)", value="\n".join(roles_lines)[:1024], inline=False)

    options = [
        f"🧹 Delete existing channels: **{'YES — all current channels will be deleted' if clean_existing else 'No'}**",
        f"✅ Verification gate: **{'On' if verification else 'Off'}**",
        f"📊 Live stats counters: **{'On' if layout['stats'] else 'Off'}**"
    ]
    embed.add_field(name="⚙️ Options", value="\n".join(options), inline=False)
    embed.add_field(name="🔐 Server Settings Applied", value="\n".join(SERVER_SETTINGS_SUMMARY), inline=False)
    embed.set_footer(text="Only the server owner can confirm this build.")
    return embed


def _overwrite(overwrites: dict, target, **perms):
    """Merges permission flags into an overwrite map without dropping existing flags."""
    current = overwrites.get(target, discord.PermissionOverwrite())
    merged = discord.PermissionOverwrite.from_pair(*current.pair())
    merged.update(**perms)
    overwrites[target] = merged


SERVER_SETTINGS_SUMMARY = [
    "🔕 Notifications: **@mentions only** (new servers ping everyone for every message)",
    "📢 Only staff can ping @everyone / @here",
    "🛡️ Verification level: at least **Medium** (account must be 5+ minutes old)",
    "🖼️ Explicit image filter: **all members**",
    "👋 Discord's own join messages off (the bot's welcome card replaces them)",
]


async def _make_role(guild: discord.Guild, spec: dict, reason: str, mentionable: bool = False):
    """Creates a designed role, or returns the existing one with that name (kept as it is)."""
    role = discord.utils.get(guild.roles, name=spec["name"])
    if role:
        return role
    color = spec.get("color")
    try:
        role = await guild.create_role(
            name=spec["name"],
            color=discord.Color.default() if color is None else _parse_color(color),
            permissions=discord.Permissions(**spec.get("perms", {})),
            hoist=spec.get("hoist", False), mentionable=mentionable, reason=f"Server design: {reason}")
        await asyncio.sleep(0.2)
        return role
    except discord.HTTPException:
        return None


async def upgrade_roles(guild: discord.Guild, add_missing: bool = True,
                        color_channel: discord.TextChannel | None = None) -> discord.Embed:
    """Repairs an existing server: adds missing designed roles, wires them, and fixes the hierarchy order."""
    cfg = data_manager.get_guild_data(guild.id)
    created = {}
    if add_missing:
        for spec in STAFF_ROLES + COLOR_ROLES + LEVEL_ROLES + [MEMBER_ROLE]:
            if not discord.utils.get(guild.roles, name=spec["name"]):
                role = await _make_role(guild, spec, "role upgrade")
                if role:
                    created[spec["name"]] = role
    by_name = {r.name: r for r in guild.roles}
    by_name.update(created)
    for spec in LEVEL_ROLES:
        if spec["name"] in by_name:
            cfg["level_rewards"][str(spec["level"])] = by_name[spec["name"]].id
    cfg["color_role_ids"] = [by_name[s["name"]].id for s in COLOR_ROLES if s["name"] in by_name]
    for key, name in (("mod_role_id", "🔨 Moderator"),):
        if name in by_name:
            cfg[key] = by_name[name].id
    data_manager.save()

    warning = await fix_role_order(guild, created)
    order = _design_role_order(guild, created)
    embed = discord.Embed(title="🎭 Role Hierarchy Updated" if not warning else "⚠️ Role Hierarchy Partly Updated",
                          color=EMBED_COLOR_WARNING if warning else EMBED_COLOR_SUCCESS)
    embed.description = warning or "Roles are now in the right order (top → bottom):\n" + " › ".join(r.mention for r in order)[:3900]
    if created:
        embed.add_field(name="➕ Added", value=", ".join(created)[:1024], inline=False)
    colors = [r for r in by_name.values() if r.id in cfg["color_role_ids"] and is_safe_self_role(r, guild.me)]
    if color_channel and colors:
        colors.sort(key=lambda r: [s["name"] for s in COLOR_ROLES].index(r.name))
        await color_channel.send(embed=discord.Embed(
            title="🎨 Pick Your Name Color",
            description="Choose one color for your name. Picking another swaps it; click yours again to remove it.\n\n"
                        + "  ".join(r.mention for r in colors), color=EMBED_COLOR_DEFAULT), view=build_color_view(colors))
        embed.add_field(name="🎨 Color Panel", value=f"Posted in {color_channel.mention}", inline=False)
    return embed


def _design_role_order(guild: discord.Guild, known_roles: dict | None = None, self_roles=None) -> list[discord.Role]:
    """The designed roles in the server, in the order they should appear (top first).
    known_roles: roles just created, which discord.py's cache may not list yet."""
    lookup = {r.name: r for r in guild.roles}
    lookup.update(known_roles or {})
    known = ([s["name"] for s in STAFF_ROLES] + [s["name"] for s in COLOR_ROLES]
             + [s["name"] for s in LEVEL_ROLES] + [MEMBER_ROLE["name"]])
    order = [lookup[name] for name in known if name in lookup]
    if self_roles is None:
        # Repair mode: design self-roles are the mentionable, permission-less roles the bot can manage
        self_roles = [r for r in sorted(guild.roles, key=lambda r: -r.position)
                      if r not in order and not r.is_default() and not r.managed and r.mentionable
                      and r.permissions.value == 0 and r < guild.me.top_role]
    return order + [r for r in self_roles if r not in order]


async def fix_role_order(guild: discord.Guild, known_roles: dict | None = None, self_roles=None) -> str | None:
    """Puts the designed roles in order: staff > VIP > colors > levels > Member > self-roles.
    Returns a warning for the owner, or None on success."""
    if not guild.me.guild_permissions.manage_roles:
        return ("My role doesn't have the **Manage Roles** permission. Turn it on in Server Settings → Roles → "
                f"{guild.me.top_role.name} → Permissions, then try again.")
    order = _design_role_order(guild, known_roles, self_roles)
    if not order:
        return "I couldn't find any designed roles in this server."
    blocked = [r for r in order if r >= guild.me.top_role]
    if blocked:
        return (f"My role is below {', '.join(r.name for r in blocked[:3])}. Drag my role to the top in "
                "Server Settings → Roles, then try again.")
    reason = "Server design: role hierarchy order"
    # The cache (and roles created a moment ago) can hold stale positions, so ask Discord for the real ones
    try:
        fresh = {r.id: r for r in await guild.fetch_roles()}
        order = [fresh.get(r.id, r) for r in order]
    except discord.HTTPException:
        pass
    # Reuse the slots these roles already occupy, so no other role is moved; if positions are tied,
    # fall back to stacking them at the bottom (Discord shifts the rest)
    slots = sorted((r.position for r in order), reverse=True)
    if len(set(slots)) < len(slots) or min(slots) < 1:
        slots = [len(order) - i for i in range(len(order))]
    positions = dict(zip(order, slots))
    try:
        await guild.edit_role_positions(positions=positions, reason=reason)
        return None
    except discord.HTTPException as e:
        logger.warning(f"Bulk role reorder refused ({e.status} {e.code}): {e.text} | "
                       + ", ".join(f"{r.name}={p}" for r, p in positions.items()))
        first_error = e
    # Fall back to moving one role at a time, top first
    failed = []
    for role, pos in positions.items():
        try:
            await role.edit(position=pos, reason=reason)
        except discord.HTTPException as e:
            logger.warning(f"Moving {role.name} to {pos} refused ({e.status} {e.code}): {e.text}")
            failed.append(role.name)
            if e.code == first_error.code == 50013:
                break  # a permission problem won't fix itself for the next role
    if failed and first_error.code == 50013:
        me = guild.me
        logger.warning(f"Bot role {me.top_role.name} at position {me.top_role.position}, manage_roles="
                       f"{me.guild_permissions.manage_roles}, administrator={me.guild_permissions.administrator}")
        return ("Discord says I'm missing permissions. Check that my role has **Manage Roles** (or Administrator) "
                "and is above every role listed here. If the server requires 2FA for moderation, my developer "
                "account needs 2FA turned on too.")
    if failed:
        return (f"Discord refused to move {len(failed)} role(s): {', '.join(failed[:5])}. "
                f"Discord said: {first_error.text or first_error.status}")
    return None


async def apply_server_settings(guild: discord.Guild, wired: dict) -> list[str]:
    """Applies the recommended safety and notification settings. Never lowers a stricter existing setting."""
    notes = []
    reason = "Server design: recommended settings"

    perms = guild.default_role.permissions
    if perms.mention_everyone:
        perms.update(mention_everyone=False)
        try:
            await guild.default_role.edit(permissions=perms, reason=reason)
            notes.append("• **@everyone pings:** staff only")
        except discord.HTTPException:
            pass

    settings = {
        "default_notifications": discord.NotificationLevel.only_mentions,
        "system_channel_flags": discord.SystemChannelFlags(join_notifications=False, join_notification_replies=False,
                                                           premium_subscriptions=True, guild_reminder_notifications=False),
    }
    if guild.verification_level.value < discord.VerificationLevel.medium.value:
        settings["verification_level"] = discord.VerificationLevel.medium
    if guild.explicit_content_filter != discord.ContentFilter.all_members:
        settings["explicit_content_filter"] = discord.ContentFilter.all_members
    # Boost thank-yous go to the main chat
    general = next((c for c in guild.text_channels if "general" in c.name), None) or wired.get("welcome")
    if general:
        settings["system_channel"] = general

    applied = []
    try:
        await guild.edit(**settings, reason=reason)
        applied = list(settings)
    except discord.HTTPException:
        for key, value in settings.items():  # one rejected setting shouldn't block the rest
            try:
                await guild.edit(**{key: value}, reason=reason)
                applied.append(key)
            except discord.HTTPException:
                pass
    labels = {"default_notifications": "mentions-only notifications", "system_channel_flags": "join messages off",
              "verification_level": "verification Medium", "explicit_content_filter": "image filter on",
              "system_channel": "boost messages in main chat"}
    if applied:
        notes.append("• **Server Settings:** " + ", ".join(labels[k] for k in applied))
    return notes


async def build_server(guild: discord.Guild, layout: dict, *, clean_existing: bool, verification: bool,
                       keep_channel_id: int, owner: discord.Member) -> discord.Embed:
    """Builds roles, categories, and channels from a normalized layout and wires bot features."""
    cfg = data_manager.get_guild_data(guild.id)

    # 1. Optional cleanup
    deleted = 0
    if clean_existing:
        for ch in list(guild.channels):
            if ch.id == keep_channel_id:
                continue
            try:
                await ch.delete(reason=f"Server redesign by owner {owner}")
                deleted += 1
                await asyncio.sleep(0.3)
            except discord.HTTPException:
                pass
        for key in ("welcome_channel_id", "leave_channel_id", "log_channel_id", "ticket_category_id",
                    "chatter_channel_id", "suggestion_channel_id", "levelup_channel_id", "tempvoice_hub_id"):
            cfg[key] = None
        cfg["tempvoice_channels"] = []
        cfg["stats_channels"] = {}
        data_manager.save()

    # 2. Roles. Discord adds each new role at the bottom, so creating them top-first already gives
    # the right order; fix_role_order then sets every position explicitly to be sure.
    # Final order, top to bottom: staff > VIP > name colors > level roles > Member > self-roles
    async def make_role(spec: dict, reason: str, mentionable: bool = False):
        return await _make_role(guild, spec, reason, mentionable)

    roles = {}
    for spec in STAFF_ROLES:
        role = await make_role(spec, "role hierarchy")
        if role:
            roles[spec["name"]] = role
    color_roles = [r for r in [await make_role(s, "name color") for s in COLOR_ROLES] if r]
    level_roles = {}
    for spec in LEVEL_ROLES:
        role = await make_role(spec, "level reward")
        if role:
            level_roles[spec["level"]] = role
    member_role = await make_role(MEMBER_ROLE, "member role")
    if member_role:
        roles[MEMBER_ROLE["name"]] = member_role
    self_roles = [r for r in [await make_role(s, "self-role", mentionable=True) for s in layout["self_roles"]] if r]
    just_made = {r.name: r for r in [*roles.values(), *color_roles, *level_roles.values()]}
    order_warning = await fix_role_order(guild, just_made, self_roles)

    owner_role = roles.get("👑 Owner")
    admin_role = roles.get("🛡️ Admin")
    mod_role = roles.get("🔨 Moderator")
    helper_role = roles.get("🧰 Helper")
    bots_role = roles.get("🤖 Bots")
    staff_roles = [r for r in (admin_role, mod_role, helper_role) if r]

    # Level roles are handed out automatically by the leveling system
    for level, role in level_roles.items():
        cfg["level_rewards"][str(level)] = role.id
    cfg["color_role_ids"] = [r.id for r in color_roles]

    for role, target in ((owner_role, owner), (bots_role, guild.me)):
        if role and target and role not in target.roles:
            try:
                await target.add_roles(role, reason="Server design")
            except discord.HTTPException:
                pass

    if mod_role:
        cfg["mod_role_id"] = mod_role.id

    # 3. Categories and channels
    wired = {}
    created_count = 0
    has_verify = verification and any(ch["purpose"] == "verify" for cat in layout["categories"] for ch in cat["channels"])

    for cat_spec in layout["categories"]:
        cat_overwrites = {guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_roles=True)}
        is_verify_cat = any(ch["purpose"] == "verify" for ch in cat_spec["channels"])

        if cat_spec["staff_only"]:
            _overwrite(cat_overwrites, guild.default_role, view_channel=False)
            for staff in staff_roles:
                _overwrite(cat_overwrites, staff, view_channel=True, send_messages=True, connect=True)
        elif has_verify and not is_verify_cat:
            # Unverified members can only see the verification area
            _overwrite(cat_overwrites, guild.default_role, view_channel=False)
            if member_role:
                _overwrite(cat_overwrites, member_role, view_channel=True)

        try:
            category = await guild.create_category(name=cat_spec["name"], overwrites=cat_overwrites, reason="Server design")
        except discord.HTTPException:
            continue
        await asyncio.sleep(0.3)

        for ch_spec in cat_spec["channels"]:
            ch_overwrites = dict(cat_overwrites)
            purpose = ch_spec["purpose"]

            if ch_spec["read_only"] or purpose == "verify":
                _overwrite(ch_overwrites, guild.default_role, send_messages=False, add_reactions=purpose in ("suggestions", "announcements"))
                for staff in staff_roles:
                    _overwrite(ch_overwrites, staff, send_messages=True)
            if purpose == "verify" and has_verify and member_role:
                _overwrite(ch_overwrites, member_role, view_channel=False)

            slowmode = ch_spec.get("slowmode", 0)
            try:
                if ch_spec["type"] == "text":
                    ch_obj = await guild.create_text_channel(name=ch_spec["name"], category=category, topic=ch_spec["topic"] or None,
                                                             slowmode_delay=slowmode, overwrites=ch_overwrites, reason="Server design")
                elif ch_spec["type"] == "forum":
                    try:
                        ch_obj = await guild.create_forum(name=ch_spec["name"], category=category, topic=ch_spec["topic"] or None,
                                                          slowmode_delay=slowmode, overwrites=ch_overwrites, reason="Server design")
                    except discord.HTTPException:
                        # Forums need the server's Community feature; fall back to a normal text channel
                        ch_obj = await guild.create_text_channel(name=ch_spec["name"], category=category, topic=ch_spec["topic"] or None,
                                                                 slowmode_delay=slowmode, overwrites=ch_overwrites, reason="Server design")
                else:
                    ch_obj = await guild.create_voice_channel(name=ch_spec["name"], category=category,
                                                              overwrites=ch_overwrites, reason="Server design")
            except discord.HTTPException:
                continue
            created_count += 1
            if purpose != "none":
                wired[purpose] = ch_obj
            await asyncio.sleep(0.3)

    # 4. Wire channels into bot features
    notes = []
    if "ticket" in wired:
        try:
            tickets_cat = await guild.create_category(
                name="🎫 ─── OPEN TICKETS ───",
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True),
                    **{staff: discord.PermissionOverwrite(view_channel=True) for staff in staff_roles}
                },
                reason="Server design: ticket storage"
            )
            cfg["ticket_category_id"] = tickets_cat.id
        except discord.HTTPException:
            pass
        ticket_embed = discord.Embed(
            title="📩 Need Help? Open a Support Ticket!",
            description="Click the button below to open a private ticket with our server staff team.\n\nOur moderators and administrators will be with you shortly!",
            color=0xEB459E
        )
        ticket_embed.set_footer(text=f"{guild.name} Support System")
        await wired["ticket"].send(embed=ticket_embed, view=TicketPanelView())
        notes.append(f"• **Ticket Panel:** {wired['ticket'].mention}")

    if "rules" in wired:
        rules_embed = discord.Embed(
            title=f"📜 {guild.name} — Server Rules",
            description="\n\n".join(f"**{i}.** {rule}" for i, rule in enumerate(layout["rules"], 1)),
            color=EMBED_COLOR_DEFAULT
        )
        rules_embed.set_footer(text="By staying in this server you agree to follow these rules.")
        await wired["rules"].send(embed=rules_embed)
        notes.append(f"• **Rules:** posted in {wired['rules'].mention}")

    if has_verify and "verify" in wired and member_role:
        cfg["verify_role_id"] = member_role.id
        cfg["autorole_id"] = None
        verify_embed = discord.Embed(
            title="✅ Verification",
            description=f"Welcome to **{guild.name}**!\nRead the rules, then press the button below to unlock the server.",
            color=EMBED_COLOR_SUCCESS
        )
        await wired["verify"].send(embed=verify_embed, view=VerifyView())
        notes.append(f"• **Verification Gate:** {wired['verify'].mention} → grants {member_role.mention}")
    elif member_role:
        cfg["autorole_id"] = member_role.id
        cfg["verify_role_id"] = None
        notes.append(f"• **Auto-Role on Join:** {member_role.mention}")

    safe_self_roles = [r for r in self_roles if is_safe_self_role(r, guild.me)]
    if "roles" in wired and safe_self_roles:
        roles_embed = discord.Embed(
            title="🎭 Pick Your Roles",
            description="Click a button to add or remove a role.\n\n" + "\n".join(f"• {r.mention}" for r in safe_self_roles),
            color=EMBED_COLOR_DEFAULT
        )
        await wired["roles"].send(embed=roles_embed, view=build_selfrole_view(safe_self_roles))
        notes.append(f"• **Self-Role Panel:** {wired['roles'].mention} ({len(safe_self_roles)} roles)")

    safe_colors = [r for r in color_roles if is_safe_self_role(r, guild.me)]
    if "roles" in wired and safe_colors:
        colors_embed = discord.Embed(
            title="🎨 Pick Your Name Color",
            description="Choose one color for your name. Picking another swaps it; click yours again to remove it.\n\n"
                        + "  ".join(r.mention for r in safe_colors),
            color=EMBED_COLOR_DEFAULT
        )
        await wired["roles"].send(embed=colors_embed, view=build_color_view(safe_colors))
        notes.append(f"• **Name Color Panel:** {len(safe_colors)} colors")

    if level_roles:
        notes.append("• **Level Rewards:** " + ", ".join(f"lvl {lvl} → {r.mention}" for lvl, r in sorted(level_roles.items())))

    simple_wiring = {
        "welcome": ("welcome_channel_id", "Welcome Greetings"),
        "log": ("log_channel_id", "Audit & Mod Logs"),
        "ai_chat": ("chatter_channel_id", "AI Chat Channel"),
        "suggestions": ("suggestion_channel_id", "Suggestions"),
        "levelup": ("levelup_channel_id", "Level-Up Announcements"),
        "tempvoice": ("tempvoice_hub_id", "Join-to-Create Voice"),
    }
    for purpose, (key, label) in simple_wiring.items():
        if purpose in wired:
            cfg[key] = wired[purpose].id
            notes.append(f"• **{label}:** {wired[purpose].mention}")

    if "welcome" in wired:
        cfg["leave_channel_id"] = wired["welcome"].id

    if "afk" in wired:
        try:
            await guild.edit(afk_channel=wired["afk"], afk_timeout=900, reason="Server design")
            notes.append(f"• **AFK Channel:** {wired['afk'].mention}")
        except discord.HTTPException:
            pass

    notes += await apply_server_settings(guild, wired)
    if order_warning:
        notes.append(f"• ⚠️ **Role order:** {order_warning} (then run `/fix_roles`)")

    data_manager.save()

    if layout["stats"]:
        try:
            await create_stats_channels(guild)
            notes.append("• **Live Stats Counters:** created at the top of the server")
        except discord.HTTPException:
            pass

    # 5. Report
    embed = discord.Embed(
        title="🎉 Server Design Completed!",
        description=(
            f"Your server has been built using the **{layout['name']}** design.\n\n"
            f"📊 **Created:** **{created_count}** channels across **{len(layout['categories'])}** categories\n"
            + (f"🧹 **Deleted:** **{deleted}** old channels\n" if clean_existing else "")
            + f"🎭 **Roles:** {', '.join(r.mention for r in roles.values())}"
        ),
        color=EMBED_COLOR_SUCCESS
    )
    # Embed fields hold 1024 characters, so split the wiring notes across as many fields as needed
    chunk, chunks = "", []
    for note in notes:
        if len(chunk) + len(note) + 1 > 1024:
            chunks.append(chunk)
            chunk = ""
        chunk += note[:1024] + "\n"
    if chunk:
        chunks.append(chunk)
    for i, text in enumerate(chunks):
        embed.add_field(name="⚙️ Automated Bot Wiring" if i == 0 else "⚙️ (continued)", value=text, inline=False)
    embed.add_field(
        name="📝 Next Steps",
        value=(
            "• Drag the bot's own role to the **top** of the role list so it can manage every role.\n"
            "• Give trusted staff the Admin / Moderator / Helper roles.\n"
            + ("• This channel was kept so you could see this report — delete it when done.\n" if clean_existing else "")
        ),
        inline=False
    )
    embed.set_footer(text=f"Designed by {guild.me.display_name}")
    return embed


_building = set()  # guild IDs with a build in progress


def apply_verification(layout: dict, verification: bool) -> dict:
    """Removes the verify channel when verification is off, or adds one when it is on but missing."""
    if not verification:
        for cat in layout["categories"]:
            cat["channels"] = [ch for ch in cat["channels"] if ch["purpose"] != "verify"]
        layout["categories"] = [cat for cat in layout["categories"] if cat["channels"]]
    elif not any(ch["purpose"] == "verify" for cat in layout["categories"] for ch in cat["channels"]):
        public = next((cat for cat in layout["categories"] if not cat["staff_only"]), None)
        if public:
            public["channels"].insert(0, {"name": "✅・verify", "type": "text", "topic": "Click the button to get access to the server.",
                                          "read_only": True, "purpose": "verify"})
    return layout


class DesignConfirmView(discord.ui.View):
    """Build / Cancel buttons shown under a design preview. Only the server owner can press them."""

    def __init__(self, owner_id: int, layout: dict, clean_existing: bool, verification: bool):
        super().__init__(timeout=600)
        self.owner_id = owner_id
        self.layout = layout
        self.clean_existing = clean_existing
        self.verification = verification
        if clean_existing:
            self.build.label = "Delete Everything & Build"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("👑 Only the server owner can confirm this design.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Build", style=discord.ButtonStyle.success, emoji="🏗️")
    async def build(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild.id in _building:
            return await interaction.response.send_message("⏳ A design is already being built in this server. Wait for it to finish.", ephemeral=True)
        _building.add(interaction.guild.id)
        self.stop()
        building = discord.Embed(
            title="🏗️ Building your server...",
            description="Creating roles, categories, channels and permissions. This can take a minute or two — please don't run other design commands meanwhile.",
            color=EMBED_COLOR_WARNING
        )
        try:
            await interaction.response.edit_message(embed=building, view=None)
            report = await build_server(
                interaction.guild, self.layout,
                clean_existing=self.clean_existing, verification=self.verification,
                keep_channel_id=interaction.channel_id, owner=interaction.user
            )
        except Exception as e:
            report = discord.Embed(title="❌ Design Failed", description=f"`{e}`\n\nMake sure the bot has the **Administrator** permission.", color=EMBED_COLOR_ERROR)
        finally:
            _building.discard(interaction.guild.id)

        try:
            await interaction.edit_original_response(embed=report)
        except discord.HTTPException:
            await interaction.channel.send(embed=report)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="❎ Server design cancelled. Nothing was changed.", embed=None, view=None)


class ServerDesigner(commands.Cog):
    """Owner-only server architect: templates, AI-generated layouts, and manual channel tools."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _show_preview(self, interaction: discord.Interaction, layout: dict, clean_existing: bool, verification: bool):
        apply_verification(layout, verification)
        embed = layout_preview_embed(layout, clean_existing, verification)
        view = DesignConfirmView(interaction.user.id, layout, clean_existing, verification)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="design_server", description="[Owner] Design your server from a ready-made template (preview first).")
    @app_commands.describe(
        template="Choose the theme template for your server design",
        clean_existing="DELETE all existing channels first (you'll be asked to confirm)",
        verification="Hide the server until members press a Verify button"
    )
    @is_guild_owner()
    async def design_server(self, interaction: discord.Interaction, template: Literal["gaming", "tech", "study", "minimal"],
                            clean_existing: bool = False, verification: bool = False):
        layout = normalize_layout(TEMPLATES[template])
        await self._show_preview(interaction, layout, clean_existing, verification)

    @app_commands.command(name="design_ai", description="[Owner] Let Gemini AI design a custom server for any theme (preview first).")
    @app_commands.describe(
        theme="Describe your server, e.g. 'anime fan club with art sharing and watch parties'",
        clean_existing="DELETE all existing channels first (you'll be asked to confirm)",
        verification="Hide the server until members press a Verify button"
    )
    @is_guild_owner()
    async def design_ai(self, interaction: discord.Interaction, theme: app_commands.Range[str, 3, 300],
                        clean_existing: bool = False, verification: bool = False):
        if not gemini_queue.is_gemini_active:
            gemini_queue.refresh_client()
            if not gemini_queue.is_gemini_active:
                return await interaction.response.send_message("❌ Gemini is not configured. Add `GEMINI_API_KEY` to `.env` or use `/chatter set_api_key`.", ephemeral=True)

        await interaction.response.defer(thinking=True)
        try:
            raw = await gemini_queue.ask_gemini(AI_DESIGN_PROMPT.format(theme=theme), json_mode=True, quality=True)
            raw = re.sub(r"^```(?:json)?|```$", "", raw.strip()).strip()
            layout = normalize_layout(json.loads(raw))
        except Exception as e:
            return await interaction.followup.send(f"❌ The AI could not produce a valid design (`{type(e).__name__}`). Please try again or rephrase the theme.")
        await self._show_preview(interaction, layout, clean_existing, verification)

    @app_commands.command(name="fix_roles", description="[Owner] Add any missing designed roles and put the role hierarchy in order.")
    @app_commands.describe(add_missing="Create missing roles (Helper, name colors, level rewards...)",
                           color_panel_channel="Also post the name-color picker in this channel")
    @is_guild_owner()
    async def fix_roles(self, interaction: discord.Interaction, add_missing: bool = True,
                        color_panel_channel: discord.TextChannel = None):
        await interaction.response.defer(thinking=True)
        await interaction.followup.send(embed=await upgrade_roles(interaction.guild, add_missing, color_panel_channel))

    # --- MANUAL CHANNEL CREATION UTILITY ---
    @app_commands.command(name="create_channel", description="[Owner] Quickly create a custom text or voice channel.")
    @app_commands.describe(
        name="Name of the channel (e.g. general, announcements)",
        channel_type="Type of channel (text or voice)",
        category="Category to place the channel in (optional)",
        topic="Channel topic or description (optional)",
        read_only="Only staff can send messages"
    )
    @is_guild_owner()
    async def create_channel(self, interaction: discord.Interaction, name: str, channel_type: Literal["text", "voice"] = "text",
                             category: discord.CategoryChannel = None, topic: str = None, read_only: bool = False):
        guild = interaction.guild
        overwrites = {}
        if read_only:
            overwrites = dict(category.overwrites) if category else {}
            _overwrite(overwrites, guild.default_role, send_messages=False)
            _overwrite(overwrites, guild.me, send_messages=True)

        if channel_type == "text":
            ch = await guild.create_text_channel(name=name.strip().replace(" ", "-").lower(), category=category, topic=topic,
                                                 overwrites=overwrites or discord.utils.MISSING)
        else:
            ch = await guild.create_voice_channel(name=name.strip(), category=category, overwrites=overwrites or discord.utils.MISSING)
        await interaction.response.send_message(f"✅ Created {channel_type} channel {ch.mention} in category `{category.name if category else 'None'}`.")

    @app_commands.command(name="create_category", description="[Owner] Quickly create a new category.")
    @app_commands.describe(name="Name of the category", staff_only="Hide this category from everyone except staff")
    @is_guild_owner()
    async def create_category(self, interaction: discord.Interaction, name: str, staff_only: bool = False):
        guild = interaction.guild
        overwrites = {}
        if staff_only:
            overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
            overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True)
            mod_id = data_manager.get_guild_data(guild.id).get("mod_role_id")
            mod_role = guild.get_role(int(mod_id)) if mod_id else None
            if mod_role:
                overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True)
        cat = await guild.create_category(name=name.strip(), overwrites=overwrites)
        await interaction.response.send_message(f"✅ Created category **{cat.name}**{' (staff only)' if staff_only else ''}.")

    @app_commands.command(name="delete_category", description="[Owner] Delete a category and every channel inside it.")
    @app_commands.describe(category="The category to remove")
    @is_guild_owner()
    async def delete_category(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            f"⚠️ Delete **{category.name}** and its **{len(category.channels)}** channels? This cannot be undone.",
            view=view, ephemeral=True
        )
        await view.wait()
        if not view.confirmed:
            return await interaction.edit_original_response(content="❎ Cancelled.", view=None)
        for ch in category.channels:
            if ch.id != interaction.channel_id:
                try:
                    await ch.delete(reason=f"Category removed by owner {interaction.user}")
                except discord.HTTPException:
                    pass
        await category.delete(reason=f"Category removed by owner {interaction.user}")
        await interaction.edit_original_response(content=f"🗑️ Deleted category **{category.name}**.", view=None)


class ConfirmView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.stop()


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerDesigner(bot))
