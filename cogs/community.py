import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import re
import time
import uuid
from typing import Literal
from config import EMBED_COLOR_DEFAULT, EMBED_COLOR_SUCCESS
import data_manager
from utils import parse_duration


class Community(commands.Cog):
    """Polls, suggestions, AFK status, reminders, and announcements."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    # --- POLLS (native Discord polls) ---
    @app_commands.command(name="poll", description="Create a poll. Separate options with | (e.g. Pizza | Burgers | Tacos).")
    @app_commands.describe(question="The poll question", options="2-10 options separated by |", hours="How long the poll runs (1-168)", multiple="Allow picking more than one answer")
    async def poll(self, interaction: discord.Interaction, question: app_commands.Range[str, 1, 300], options: str,
                   hours: app_commands.Range[int, 1, 168] = 24, multiple: bool = False):
        answers = [o.strip() for o in options.split("|") if o.strip()]
        if not 2 <= len(answers) <= 10:
            return await interaction.response.send_message("❌ Provide between 2 and 10 options separated by `|`.", ephemeral=True)
        poll = discord.Poll(question=question, duration=datetime.timedelta(hours=hours), multiple=multiple)
        for answer in answers:
            poll.add_answer(text=answer[:55])
        await interaction.response.send_message(poll=poll)

    # --- SUGGESTIONS ---
    @app_commands.command(name="suggest", description="Submit a suggestion for the server.")
    async def suggest(self, interaction: discord.Interaction, idea: app_commands.Range[str, 5, 1500]):
        ch_id = data_manager.get_guild_data(interaction.guild.id).get("suggestion_channel_id")
        channel = interaction.guild.get_channel(int(ch_id)) if ch_id else None
        if not channel:
            return await interaction.response.send_message("⚠️ Suggestions aren't set up. An admin can run `/suggestions set_channel`.", ephemeral=True)

        embed = discord.Embed(title="💡 New Suggestion", description=idea, color=EMBED_COLOR_DEFAULT, timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        msg = await channel.send(embed=embed)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
        try:
            await msg.create_thread(name=f"Discuss: {idea[:80]}")
        except discord.HTTPException:
            pass
        await interaction.response.send_message(f"✅ Suggestion posted in {channel.mention}!", ephemeral=True)

    suggestions_group = app_commands.Group(name="suggestions", description="Configure suggestions")

    @suggestions_group.command(name="set_channel", description="Channel where /suggest posts go.")
    @app_commands.checks.has_permissions(administrator=True)
    async def suggestions_set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        data_manager.update_guild_data(interaction.guild.id, "suggestion_channel_id", channel.id)
        await interaction.response.send_message(f"✅ Suggestions will be posted in {channel.mention}.")

    # --- AFK ---
    @app_commands.command(name="afk", description="Set yourself as AFK. People who mention you will be told.")
    async def afk(self, interaction: discord.Interaction, reason: app_commands.Range[str, 1, 200] = "AFK"):
        cfg = data_manager.get_guild_data(interaction.guild.id)
        cfg["afk"][str(interaction.user.id)] = {"reason": reason, "since": int(time.time())}
        data_manager.save()
        await interaction.response.send_message(f"💤 {interaction.user.mention} is now AFK: {reason}", allowed_mentions=discord.AllowedMentions.none())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        cfg = data_manager.get_guild_data(message.guild.id)
        afk = cfg.get("afk", {})
        if not afk:
            return

        if afk.pop(str(message.author.id), None):
            data_manager.save()
            await message.channel.send(f"👋 Welcome back {message.author.mention}, I removed your AFK.", delete_after=8)

        notes = []
        for user in message.mentions[:5]:
            info = afk.get(str(user.id))
            if info:
                notes.append(f"💤 **{user.display_name}** is AFK: {info['reason']} (since <t:{info['since']}:R>)")
        if notes:
            await message.reply("\n".join(notes), allowed_mentions=discord.AllowedMentions.none(), delete_after=20)

    # --- REMINDERS ---
    @app_commands.command(name="remind", description="Set a reminder, e.g. when: 2h30m  text: check the oven.")
    @app_commands.describe(when="Delay like 10m, 2h, 1d, 1w", text="What should I remind you about?")
    async def remind(self, interaction: discord.Interaction, when: str, text: app_commands.Range[str, 1, 500]):
        seconds = parse_duration(when)
        if not seconds or seconds > 365 * 86400:
            return await interaction.response.send_message("❌ Invalid time. Use formats like `10m`, `2h30m`, `1d`, `1w`.", ephemeral=True)

        cfg = data_manager.get_guild_data(interaction.guild.id)
        mine = [r for r in cfg["reminders"] if r["user_id"] == interaction.user.id]
        if len(mine) >= 25:
            return await interaction.response.send_message("❌ You already have 25 reminders pending.", ephemeral=True)

        due = int(time.time() + seconds)
        cfg["reminders"].append({"id": uuid.uuid4().hex[:6], "user_id": interaction.user.id,
                                 "channel_id": interaction.channel_id, "due": due, "text": text})
        data_manager.save()
        await interaction.response.send_message(f"⏰ Got it! I'll remind you <t:{due}:R>.", ephemeral=True)

    reminders_group = app_commands.Group(name="reminders", description="Manage your reminders")

    @reminders_group.command(name="list", description="Show your pending reminders.")
    async def reminders_list(self, interaction: discord.Interaction):
        mine = [r for r in data_manager.get_guild_data(interaction.guild.id)["reminders"] if r["user_id"] == interaction.user.id]
        if not mine:
            return await interaction.response.send_message("You have no pending reminders.", ephemeral=True)
        lines = [f"`{r['id']}` — <t:{r['due']}:R>: {r['text'][:80]}" for r in sorted(mine, key=lambda r: r["due"])]
        await interaction.response.send_message(embed=discord.Embed(title="⏰ Your Reminders", description="\n".join(lines), color=EMBED_COLOR_DEFAULT), ephemeral=True)

    @reminders_group.command(name="cancel", description="Cancel a reminder by its ID (see /reminders list).")
    async def reminders_cancel(self, interaction: discord.Interaction, reminder_id: str):
        cfg = data_manager.get_guild_data(interaction.guild.id)
        before = len(cfg["reminders"])
        cfg["reminders"] = [r for r in cfg["reminders"] if not (r["id"] == reminder_id.strip() and r["user_id"] == interaction.user.id)]
        if len(cfg["reminders"]) == before:
            return await interaction.response.send_message("❌ No reminder of yours with that ID.", ephemeral=True)
        data_manager.save()
        await interaction.response.send_message("🗑️ Reminder cancelled.", ephemeral=True)

    @tasks.loop(seconds=20)
    async def check_reminders(self):
        now = time.time()
        for guild in self.bot.guilds:
            cfg = data_manager.get_guild_data(guild.id)
            due = [r for r in cfg.get("reminders", []) if r["due"] <= now]
            if not due:
                continue
            cfg["reminders"] = [r for r in cfg["reminders"] if r["due"] > now]
            data_manager.save()
            for r in due:
                text = f"⏰ <@{r['user_id']}>, reminder: **{r['text']}**"
                channel = guild.get_channel(r["channel_id"])
                try:
                    if channel:
                        await channel.send(text, allowed_mentions=discord.AllowedMentions(users=True))
                    else:
                        member = guild.get_member(r["user_id"])
                        if member:
                            await member.send(text)
                except discord.HTTPException:
                    pass

    # --- BUMP REMINDER ---
    # Bots can't run Disboard's /bump, but when someone bumps, remind them once the 2-hour cooldown is over
    DISBOARD_ID = 302050872383242240
    BUMP_COOLDOWN = 2 * 60 * 60

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id != self.DISBOARD_ID or not message.guild:
            return
        if not any("bump done" in (e.description or "").lower() for e in message.embeds):
            return
        meta = getattr(message, "interaction_metadata", None)
        bumper_id = meta.user.id if meta and meta.user else message.guild.owner_id
        cfg = data_manager.get_guild_data(message.guild.id)
        cfg["reminders"] = [r for r in cfg["reminders"] if r["id"] != "bump"]
        cfg["reminders"].append({"id": "bump", "user_id": bumper_id, "channel_id": message.channel.id,
                                 "text": "the server can be bumped again! Type `/bump`", "due": time.time() + self.BUMP_COOLDOWN})
        data_manager.save()
        try:
            await message.add_reaction("⏰")
        except discord.HTTPException:
            pass

    @check_reminders.before_loop
    async def before_reminders(self):
        await self.bot.wait_until_ready()

    # --- ANNOUNCEMENTS ---
    @app_commands.command(name="announce", description="Post a styled announcement embed.")
    @app_commands.describe(channel="Where to post", title="Announcement title", message="Body text (use \\n for new lines)",
                           ping="Who to ping", color="Hex color, e.g. #5865F2", image_url="Optional image URL")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def announce(self, interaction: discord.Interaction, channel: discord.TextChannel, title: app_commands.Range[str, 1, 256],
                       message: app_commands.Range[str, 1, 4000], ping: Literal["none", "everyone", "here"] = "none",
                       color: str = "#5865F2", image_url: str = None):
        match = re.fullmatch(r"#?([0-9a-fA-F]{6})", color.strip())
        embed = discord.Embed(title=title, description=message.replace("\\n", "\n"),
                              color=int(match.group(1), 16) if match else EMBED_COLOR_DEFAULT,
                              timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.set_footer(text=f"Announced by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        if image_url and image_url.startswith(("http://", "https://")):
            embed.set_image(url=image_url)

        content = {"none": None, "everyone": "@everyone", "here": "@here"}[ping]
        await channel.send(content=content, embed=embed, allowed_mentions=discord.AllowedMentions(everyone=ping != "none"))
        await interaction.response.send_message(f"📢 Announcement posted in {channel.mention}.", ephemeral=True)

    @app_commands.command(name="say", description="Make the bot send a message in a channel.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def say(self, interaction: discord.Interaction, message: app_commands.Range[str, 1, 2000], channel: discord.TextChannel = None):
        target = channel or interaction.channel
        await target.send(message, allowed_mentions=discord.AllowedMentions.none())
        await interaction.response.send_message("✅ Sent.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Community(bot))
