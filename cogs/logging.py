import discord
from discord.ext import commands
from discord import app_commands
import datetime
from config import EMBED_COLOR_ERROR, EMBED_COLOR_WARNING, EMBED_COLOR_SUCCESS, EMBED_COLOR_DEFAULT
import data_manager

class Logging(commands.Cog):
    """Server audit logging for tracking message edits/deletions, member activity, and moderation events."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        cfg = data_manager.get_guild_data(guild.id)
        ch_id = cfg.get("log_channel_id")
        if ch_id:
            return guild.get_channel(int(ch_id))
        return None

    # --- MESSAGE DELETE LOG ---
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        log_channel = self.get_log_channel(message.guild)
        if not log_channel:
            return

        content = message.content or "*(No text content / embed only)*"
        if len(content) > 1024:
            content = content[:1021] + "..."

        embed = discord.Embed(
            title="🗑️ Message Deleted",
            description=f"**Author:** {message.author.mention} (`{message.author.id}`)\n**Channel:** {message.channel.mention}",
            color=EMBED_COLOR_ERROR,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Deleted Content", value=content, inline=False)
        embed.set_footer(text=f"Message ID: {message.id}")
        
        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # --- MESSAGE EDIT LOG ---
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return

        log_channel = self.get_log_channel(before.guild)
        if not log_channel:
            return

        before_text = before.content[:1020] if before.content else "*(empty)*"
        after_text = after.content[:1020] if after.content else "*(empty)*"

        embed = discord.Embed(
            title="✏️ Message Edited",
            description=f"**Author:** {before.author.mention} (`{before.author.id}`)\n**Channel:** {before.channel.mention}\n[Jump to Message]({after.jump_url})",
            color=EMBED_COLOR_WARNING,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Before", value=before_text, inline=False)
        embed.add_field(name="After", value=after_text, inline=False)
        embed.set_footer(text=f"Message ID: {after.id}")

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # --- MEMBER JOIN AUDIT LOG ---
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        log_channel = self.get_log_channel(member.guild)
        if not log_channel:
            return

        account_age = datetime.datetime.now(datetime.timezone.utc) - member.created_at
        is_new_account = account_age.days < 7

        embed = discord.Embed(
            title="📥 Member Joined",
            description=f"{member.mention} (`{member.id}`)",
            color=EMBED_COLOR_SUCCESS if not is_new_account else EMBED_COLOR_WARNING,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        if is_new_account:
            embed.add_field(name="⚠️ Security Alert", value="Account is less than 7 days old!", inline=False)

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # --- MEMBER LEAVE AUDIT LOG ---
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        log_channel = self.get_log_channel(member.guild)
        if not log_channel:
            return

        embed = discord.Embed(
            title="📤 Member Left",
            description=f"**{member.name}** (`{member.id}`)",
            color=EMBED_COLOR_ERROR,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Roles", value=", ".join([r.mention for r in member.roles[1:]]) or "None", inline=False)
        embed.add_field(name="Remaining Members", value=str(member.guild.member_count), inline=True)

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # --- BAN & UNBAN LOGS ---
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        log_channel = self.get_log_channel(guild)
        if not log_channel:
            return

        embed = discord.Embed(
            title="🔨 Member Banned Event",
            description=f"**User:** {user.name} (`{user.id}`)",
            color=EMBED_COLOR_ERROR,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        log_channel = self.get_log_channel(guild)
        if not log_channel:
            return

        embed = discord.Embed(
            title="🔓 Member Unbanned Event",
            description=f"**User:** {user.name} (`{user.id}`)",
            color=EMBED_COLOR_SUCCESS,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # --- SLASH COMMAND GROUP ---
    logs_group = app_commands.Group(name="logs", description="Configure audit log channel")

    @logs_group.command(name="set_channel", description="Set the channel where server logs and audit events are sent.")
    @app_commands.describe(channel="The channel for audit logs")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        data_manager.update_guild_data(interaction.guild.id, "log_channel_id", channel.id)
        await interaction.response.send_message(f"✅ Audit logs will now be sent in {channel.mention}.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Logging(bot))
