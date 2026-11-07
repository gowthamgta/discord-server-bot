import discord
from discord.ext import commands, tasks
from discord import app_commands
import data_manager
from checks import is_guild_owner

STATS_CATEGORY_NAME = "📊 ─── SERVER STATS ───"


def _stats_names(guild: discord.Guild) -> dict:
    humans = sum(1 for m in guild.members if not m.bot)
    return {
        "members": f"👥 Members: {guild.member_count}",
        "humans": f"🙋 Humans: {humans}",
        "bots": f"🤖 Bots: {(guild.member_count or 0) - humans}",
    }


async def create_stats_channels(guild: discord.Guild):
    """Creates a locked category with voice channels that display live member counts."""
    cfg = data_manager.get_guild_data(guild.id)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True),
    }
    # Stats stay visible even if a verification gate hides everything else
    category = await guild.create_category(STATS_CATEGORY_NAME, overwrites=overwrites, position=0, reason="Server stats counters")
    channels = {}
    for key, name in _stats_names(guild).items():
        ch = await guild.create_voice_channel(name, category=category, overwrites=overwrites, reason="Server stats counters")
        channels[key] = ch.id
    cfg["stats_channels"] = channels
    data_manager.save()


class Voice(commands.Cog):
    """Join-to-create temporary voice rooms and live server stats counters."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_stats.start()

    def cog_unload(self):
        self.update_stats.cancel()

    # --- JOIN TO CREATE ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        cfg = data_manager.get_guild_data(member.guild.id)
        hub_id = cfg.get("tempvoice_hub_id")

        if after.channel and hub_id and after.channel.id == int(hub_id):
            overwrites = dict(after.channel.category.overwrites) if after.channel.category else {}
            overwrites[member] = discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True, move_members=True, mute_members=True)
            try:
                room = await member.guild.create_voice_channel(
                    f"🔊・{member.display_name}'s Room"[:100],
                    category=after.channel.category,
                    overwrites=overwrites,
                    reason="Join-to-create voice room"
                )
                await member.move_to(room)
                cfg["tempvoice_channels"].append(room.id)
                data_manager.save()
            except discord.HTTPException:
                pass

        if before.channel and before.channel.id in cfg.get("tempvoice_channels", []) and not before.channel.members:
            try:
                await before.channel.delete(reason="Temporary voice room empty")
            except discord.HTTPException:
                pass
            cfg["tempvoice_channels"].remove(before.channel.id)
            data_manager.save()

    tempvoice_group = app_commands.Group(name="tempvoice", description="Join-to-create voice rooms")

    @tempvoice_group.command(name="setup", description="[Owner] Create a 'Create a Room' voice channel.")
    @app_commands.describe(category="Category to put the hub (and new rooms) in")
    @is_guild_owner()
    async def tempvoice_setup(self, interaction: discord.Interaction, category: discord.CategoryChannel = None):
        hub = await interaction.guild.create_voice_channel("➕・Create a Room", category=category, reason="Join-to-create hub")
        data_manager.update_guild_data(interaction.guild.id, "tempvoice_hub_id", hub.id)
        await interaction.response.send_message(f"✅ Join {hub.mention} to get your own private voice room. It is deleted when empty.")

    # --- SERVER STATS COUNTERS ---
    stats_group = app_commands.Group(name="stats", description="Live member-count channels")

    @stats_group.command(name="setup", description="[Owner] Create live member/human/bot counter channels.")
    @is_guild_owner()
    async def stats_setup(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await create_stats_channels(interaction.guild)
        await interaction.followup.send("📊 Stats counters created. They refresh every 10 minutes.")

    @stats_group.command(name="remove", description="[Owner] Delete the live counter channels.")
    @is_guild_owner()
    async def stats_remove(self, interaction: discord.Interaction):
        cfg = data_manager.get_guild_data(interaction.guild.id)
        category = None
        for ch_id in cfg.get("stats_channels", {}).values():
            ch = interaction.guild.get_channel(int(ch_id))
            if ch:
                category = ch.category
                await ch.delete(reason="Stats counters removed")
        if category and not category.channels:
            await category.delete(reason="Stats counters removed")
        cfg["stats_channels"] = {}
        data_manager.save()
        await interaction.response.send_message("🗑️ Stats counters removed.", ephemeral=True)

    @tasks.loop(minutes=10)  # Discord only allows 2 channel renames per 10 minutes
    async def update_stats(self):
        for guild in self.bot.guilds:
            stats = data_manager.get_guild_data(guild.id).get("stats_channels") or {}
            names = _stats_names(guild)
            for key, ch_id in stats.items():
                ch = guild.get_channel(int(ch_id))
                if ch and key in names and ch.name != names[key]:
                    try:
                        await ch.edit(name=names[key], reason="Stats refresh")
                    except discord.HTTPException:
                        pass

    @update_stats.before_loop
    async def before_update_stats(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Voice(bot))
