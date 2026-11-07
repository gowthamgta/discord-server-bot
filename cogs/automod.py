import discord
from discord.ext import commands
from discord import app_commands
import re
import time
from collections import defaultdict
from config import EMBED_COLOR_ERROR, EMBED_COLOR_WARNING
import data_manager

DISCORD_INVITE_REGEX = re.compile(r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/[a-zA-Z0-9]+", re.IGNORECASE)

def _word_pattern(word: str) -> str:
    """Whole-word match; edges that are symbols (e.g. 'discord.gg/') match anywhere."""
    word = word.lower()
    start = r"(?<!\w)" if re.match(r"\w", word[0]) else ""
    end = r"(?!\w)" if re.match(r"\w", word[-1]) else ""
    return start + re.escape(word) + end


class AutoMod(commands.Cog):
    """Automatic moderation for filtering banned words, invite links, and message spam."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # In-memory spam tracker: {user_id: [timestamps]}
        self.user_message_timestamps = defaultdict(list)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        member = message.author
        # Staff bypass: users with manage_messages or administrator are exempt
        if member.guild_permissions.manage_messages or member.guild_permissions.administrator:
            return

        cfg = data_manager.get_guild_data(message.guild.id)
        content_lower = message.content.lower()

        # 1. Anti-Invite Check
        if cfg.get("anti_invite", True) and DISCORD_INVITE_REGEX.search(message.content):
            try:
                await message.delete()
                warn_msg = await message.channel.send(
                    f"🚫 {member.mention}, Discord server invite links are not permitted here!",
                    delete_after=6
                )
            except (discord.Forbidden, discord.NotFound):
                pass
            return

        # 2. Banned Words Filter (whole words only, so "ass" doesn't match "class")
        banned_words = cfg.get("banned_words", [])
        for word in banned_words:
            if word and re.search(_word_pattern(word), content_lower):
                try:
                    await message.delete()
                    await message.channel.send(
                        f"⚠️ {member.mention}, your message contained a blacklisted term and was removed.",
                        delete_after=5
                    )
                except (discord.Forbidden, discord.NotFound):
                    pass
                return

        # 3. Anti-Spam Rate Limiting (5 messages in 4 seconds)
        if cfg.get("anti_spam", True):
            now = time.time()
            timestamps = self.user_message_timestamps[member.id]
            # Keep only messages from the last 4 seconds
            self.user_message_timestamps[member.id] = [t for t in timestamps if now - t < 4.0]
            self.user_message_timestamps[member.id].append(now)

            if len(self.user_message_timestamps[member.id]) >= 5:
                # Trigger spam action
                self.user_message_timestamps[member.id].clear()
                try:
                    await message.delete()
                    await message.channel.send(
                        f"🛑 {member.mention}, slow down! You are sending messages too quickly.",
                        delete_after=6
                    )
                except (discord.Forbidden, discord.NotFound):
                    pass

    # --- SLASH COMMAND GROUP ---
    automod_group = app_commands.Group(name="automod", description="Configure server auto-moderation settings")

    @automod_group.command(name="add_word", description="Add a word or phrase to the server word filter.")
    @app_commands.describe(word="Word or phrase to filter")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_word(self, interaction: discord.Interaction, word: str):
        clean_word = word.strip().lower()
        if len(clean_word) < 2:
            return await interaction.response.send_message("❌ Word must be at least 2 characters long.", ephemeral=True)

        cfg = data_manager.get_guild_data(interaction.guild.id)
        banned = cfg.get("banned_words", [])
        if clean_word in banned:
            return await interaction.response.send_message(f"⚠️ `{clean_word}` is already in the banned words list.", ephemeral=True)

        banned.append(clean_word)
        data_manager.update_guild_data(interaction.guild.id, "banned_words", banned)
        await interaction.response.send_message(f"✅ Added `{clean_word}` to the blacklisted words filter.", ephemeral=True)

    @automod_group.command(name="remove_word", description="Remove a word from the server word filter.")
    @app_commands.describe(word="Word to remove from the filter")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_word(self, interaction: discord.Interaction, word: str):
        clean_word = word.strip().lower()
        cfg = data_manager.get_guild_data(interaction.guild.id)
        banned = cfg.get("banned_words", [])

        if clean_word not in banned:
            return await interaction.response.send_message(f"❌ `{clean_word}` is not currently in the filter.", ephemeral=True)

        banned.remove(clean_word)
        data_manager.update_guild_data(interaction.guild.id, "banned_words", banned)
        await interaction.response.send_message(f"✅ Removed `{clean_word}` from the filter.", ephemeral=True)

    @automod_group.command(name="list_words", description="Display all currently blacklisted words.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def list_words(self, interaction: discord.Interaction):
        cfg = data_manager.get_guild_data(interaction.guild.id)
        banned = cfg.get("banned_words", [])

        if not banned:
            return await interaction.response.send_message("ℹ️ No banned words are currently configured.", ephemeral=True)

        word_list = ", ".join(f"`{w}`" for w in banned)
        embed = discord.Embed(
            title="🚫 Blacklisted Words Filter",
            description=word_list,
            color=EMBED_COLOR_WARNING
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @automod_group.command(name="toggle_invites", description="Toggle automatic deletion of unauthorized Discord invite links.")
    @app_commands.describe(enabled="True to block invite links, False to allow")
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle_invites(self, interaction: discord.Interaction, enabled: bool):
        data_manager.update_guild_data(interaction.guild.id, "anti_invite", enabled)
        status = "enabled (blocking links)" if enabled else "disabled (allowing links)"
        await interaction.response.send_message(f"✅ Anti-Invite protection is now **{status}**.", ephemeral=True)

    @automod_group.command(name="toggle_spam", description="Toggle rapid-fire message rate limit protection.")
    @app_commands.describe(enabled="True to enable anti-spam, False to disable")
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle_spam(self, interaction: discord.Interaction, enabled: bool):
        data_manager.update_guild_data(interaction.guild.id, "anti_spam", enabled)
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"✅ Anti-Spam protection is now **{status}**.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
