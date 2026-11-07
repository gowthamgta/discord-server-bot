import discord
from discord.ext import commands
from discord import app_commands
import random
import time
from config import EMBED_COLOR_DEFAULT, EMBED_COLOR_SUCCESS
import data_manager
from utils import xp_for_level

XP_COOLDOWN_SECONDS = 60


class Leveling(commands.Cog):
    """Message XP, levels, rank cards, leaderboard, and level role rewards."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldowns = {}  # (guild_id, user_id): last_xp_timestamp

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        key = (message.guild.id, message.author.id)
        now = time.time()
        if now - self.cooldowns.get(key, 0) < XP_COOLDOWN_SECONDS:
            return

        cfg = data_manager.get_guild_data(message.guild.id)
        if not cfg.get("xp_enabled", True):
            return
        self.cooldowns[key] = now

        entry = cfg["levels"].setdefault(str(message.author.id), {"xp": 0, "level": 0})
        entry["xp"] += random.randint(15, 25)

        leveled_up = False
        while entry["xp"] >= xp_for_level(entry["level"]):
            entry["xp"] -= xp_for_level(entry["level"])
            entry["level"] += 1
            leveled_up = True
        data_manager.save()

        if leveled_up:
            await self._on_level_up(message, entry["level"], cfg)

    async def _on_level_up(self, message: discord.Message, level: int, cfg: dict):
        member = message.author
        reward_text = ""
        role_id = cfg.get("level_rewards", {}).get(str(level))
        role = message.guild.get_role(int(role_id)) if role_id else None
        if role:
            try:
                await member.add_roles(role, reason=f"Reached level {level}")
                reward_text = f"\n🎁 You earned the {role.mention} role!"
            except discord.Forbidden:
                pass

        ch_id = cfg.get("levelup_channel_id")
        channel = message.guild.get_channel(int(ch_id)) if ch_id else message.channel
        embed = discord.Embed(
            description=f"🎉 {member.mention} reached **level {level}**!{reward_text}",
            color=EMBED_COLOR_SUCCESS
        )
        try:
            await (channel or message.channel).send(embed=embed)
        except discord.HTTPException:
            pass

    def _rank_of(self, guild_id: int, user_id: int) -> tuple[dict, int]:
        levels = data_manager.get_guild_data(guild_id).get("levels", {})
        ranking = sorted(levels.items(), key=lambda kv: (kv[1]["level"], kv[1]["xp"]), reverse=True)
        for pos, (uid, entry) in enumerate(ranking, 1):
            if uid == str(user_id):
                return entry, pos
        return {"xp": 0, "level": 0}, len(ranking) + 1

    @app_commands.command(name="rank", description="Show your (or someone's) level and XP.")
    async def rank(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        entry, pos = self._rank_of(interaction.guild.id, target.id)
        needed = xp_for_level(entry["level"])
        filled = int(12 * entry["xp"] / needed)
        bar = "🟩" * filled + "⬛" * (12 - filled)

        embed = discord.Embed(title=f"📈 {target.display_name}'s Rank", color=target.color if target.color.value else EMBED_COLOR_DEFAULT)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Level", value=f"**{entry['level']}**", inline=True)
        embed.add_field(name="Rank", value=f"**#{pos}**", inline=True)
        embed.add_field(name="XP", value=f"`{entry['xp']} / {needed}`", inline=True)
        embed.add_field(name="Progress", value=bar, inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Show the top 10 most active members.")
    async def leaderboard(self, interaction: discord.Interaction):
        levels = data_manager.get_guild_data(interaction.guild.id).get("levels", {})
        ranking = sorted(levels.items(), key=lambda kv: (kv[1]["level"], kv[1]["xp"]), reverse=True)[:10]
        if not ranking:
            return await interaction.response.send_message("Nobody has earned XP yet — start chatting!", ephemeral=True)

        medals = ["🥇", "🥈", "🥉"]
        lines = [
            f"{medals[i] if i < 3 else f'`#{i + 1}`'} <@{uid}> — Level **{e['level']}** ({e['xp']} XP)"
            for i, (uid, e) in enumerate(ranking)
        ]
        embed = discord.Embed(title=f"🏆 {interaction.guild.name} Leaderboard", description="\n".join(lines), color=EMBED_COLOR_DEFAULT)
        await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    # --- CONFIG ---
    levels_group = app_commands.Group(name="levels", description="Configure the leveling system")

    @levels_group.command(name="toggle", description="Enable or disable XP gain.")
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle(self, interaction: discord.Interaction, enabled: bool):
        data_manager.update_guild_data(interaction.guild.id, "xp_enabled", enabled)
        await interaction.response.send_message(f"✅ Leveling is now **{'enabled' if enabled else 'disabled'}**.")

    @levels_group.command(name="set_channel", description="Channel for level-up announcements (blank = same channel).")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        data_manager.update_guild_data(interaction.guild.id, "levelup_channel_id", channel.id if channel else None)
        await interaction.response.send_message(f"✅ Level-ups will be announced in {channel.mention if channel else 'the channel where they happen'}.")

    @levels_group.command(name="reward", description="Give a role automatically when members reach a level.")
    @app_commands.describe(level="Level that unlocks the role", role="Role to give (leave blank to remove this reward)")
    @app_commands.checks.has_permissions(administrator=True)
    async def reward(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 500], role: discord.Role = None):
        cfg = data_manager.get_guild_data(interaction.guild.id)
        if role:
            if role >= interaction.guild.me.top_role:
                return await interaction.response.send_message("❌ That role is above my highest role.", ephemeral=True)
            cfg["level_rewards"][str(level)] = role.id
            msg = f"✅ Members reaching **level {level}** will get {role.mention}."
        else:
            cfg["level_rewards"].pop(str(level), None)
            msg = f"✅ Removed the reward for level {level}."
        data_manager.save()
        await interaction.response.send_message(msg)

    @levels_group.command(name="rewards", description="List all level role rewards.")
    async def rewards(self, interaction: discord.Interaction):
        rewards = data_manager.get_guild_data(interaction.guild.id).get("level_rewards", {})
        if not rewards:
            return await interaction.response.send_message("No level rewards set. Use `/levels reward`.", ephemeral=True)
        lines = [f"Level **{lvl}** → <@&{rid}>" for lvl, rid in sorted(rewards.items(), key=lambda kv: int(kv[0]))]
        await interaction.response.send_message(embed=discord.Embed(title="🎁 Level Rewards", description="\n".join(lines), color=EMBED_COLOR_DEFAULT))

    @levels_group.command(name="reset", description="Reset a member's XP and level.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset(self, interaction: discord.Interaction, member: discord.Member):
        cfg = data_manager.get_guild_data(interaction.guild.id)
        cfg["levels"].pop(str(member.id), None)
        data_manager.save()
        await interaction.response.send_message(f"✅ Reset XP for {member.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
