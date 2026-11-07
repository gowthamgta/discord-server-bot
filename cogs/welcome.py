import discord
from discord.ext import commands
from discord import app_commands
import datetime
from config import EMBED_COLOR_SUCCESS, EMBED_COLOR_WARNING
import data_manager

class Welcome(commands.Cog):
    """Handles new member welcome embeds, farewell notices, and automatic role assignment."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        cfg = data_manager.get_guild_data(guild.id)

        # 1. Auto-Role Assignment
        autorole_id = cfg.get("autorole_id")
        if autorole_id:
            role = guild.get_role(int(autorole_id))
            if role:
                try:
                    await member.add_roles(role, reason="Auto-Role on server join")
                except discord.Forbidden:
                    pass

        # 2. Welcome Message
        if not cfg.get("welcome_enabled", True):
            return

        ch_id = cfg.get("welcome_channel_id")
        if not ch_id:
            return

        channel = guild.get_channel(int(ch_id))
        if not channel:
            return

        embed = discord.Embed(
            title=f"👋 Welcome to {guild.name}!",
            description=(
                f"Hey {member.mention}, we're glad to have you here!\n\n"
                f"📜 Make sure to check the server rules.\n"
                f"👥 You are member **#{guild.member_count}**."
            ),
            color=EMBED_COLOR_SUCCESS,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"User ID: {member.id} • Joined")
        
        try:
            await channel.send(content=f"Welcome {member.mention}!", embed=embed)
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        cfg = data_manager.get_guild_data(guild.id)
        
        leave_ch_id = cfg.get("leave_channel_id")
        if not leave_ch_id:
            return

        channel = guild.get_channel(int(leave_ch_id))
        if not channel:
            return

        embed = discord.Embed(
            title="👋 Member Left",
            description=f"**{member.name}** has left the server. We now have **{guild.member_count}** members.",
            color=EMBED_COLOR_WARNING,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # --- SLASH COMMAND GROUP ---
    welcome_group = app_commands.Group(name="welcome", description="Manage welcome messages and auto-roles")

    @welcome_group.command(name="set_channel", description="Set the channel where welcome messages are sent.")
    @app_commands.describe(channel="The channel for welcome greetings")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        data_manager.update_guild_data(interaction.guild.id, "welcome_channel_id", channel.id)
        await interaction.response.send_message(f"✅ Welcome messages will now be sent in {channel.mention}.")

    @welcome_group.command(name="set_leave_channel", description="Set the channel for goodbye messages (blank to disable).")
    @app_commands.describe(channel="Channel for farewell messages")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_leave_channel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        data_manager.update_guild_data(interaction.guild.id, "leave_channel_id", channel.id if channel else None)
        await interaction.response.send_message(f"✅ Goodbye messages {'will be sent in ' + channel.mention if channel else 'are disabled'}.")

    @welcome_group.command(name="set_autorole", description="Set a role to automatically give to new members when they join.")
    @app_commands.describe(role="The role to assign automatically (or leave blank to disable)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_autorole(self, interaction: discord.Interaction, role: discord.Role = None):
        if role:
            if role >= interaction.guild.me.top_role:
                return await interaction.response.send_message("❌ I cannot assign this role because it is higher than or equal to my highest role.", ephemeral=True)
            data_manager.update_guild_data(interaction.guild.id, "autorole_id", role.id)
            await interaction.response.send_message(f"✅ New members will automatically receive the {role.mention} role.")
        else:
            data_manager.update_guild_data(interaction.guild.id, "autorole_id", None)
            await interaction.response.send_message("✅ Auto-role has been **disabled**.")

    @welcome_group.command(name="toggle", description="Enable or disable welcome messages.")
    @app_commands.describe(enabled="True to enable, False to disable")
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle(self, interaction: discord.Interaction, enabled: bool):
        data_manager.update_guild_data(interaction.guild.id, "welcome_enabled", enabled)
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"✅ Welcome messages have been **{status}**.")

    @welcome_group.command(name="test", description="Send a test welcome embed to preview how it looks.")
    @app_commands.checks.has_permissions(administrator=True)
    async def test(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"👋 Welcome to {interaction.guild.name}!",
            description=(
                f"Hey {interaction.user.mention}, we're glad to have you here!\n\n"
                f"📜 Make sure to check the server rules.\n"
                f"👥 You are member **#{interaction.guild.member_count}**."
            ),
            color=EMBED_COLOR_SUCCESS,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"User ID: {interaction.user.id} • Preview")
        await interaction.response.send_message("Previewing welcome embed:", embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
