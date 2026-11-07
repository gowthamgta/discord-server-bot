import discord
from discord.ext import commands
from discord import app_commands
import datetime
from config import EMBED_COLOR_SUCCESS, EMBED_COLOR_ERROR, EMBED_COLOR_WARNING
import data_manager

class Moderation(commands.Cog):
    """Core server moderation commands for staff members."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- KICK ---
    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if member.id == interaction.user.id:
            return await interaction.response.send_message("❌ You cannot kick yourself.", ephemeral=True)
        if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message("❌ You cannot kick someone with an equal or higher role than you.", ephemeral=True)
        if member.top_role >= interaction.guild.me.top_role:
            return await interaction.response.send_message("❌ I cannot kick this user because their role is higher than or equal to my highest role.", ephemeral=True)

        try:
            # Try to DM user
            try:
                embed_dm = discord.Embed(
                    title=f"Kicked from {interaction.guild.name}",
                    description=f"**Reason:** {reason}\n**Moderator:** {interaction.user}",
                    color=EMBED_COLOR_ERROR
                )
                await member.send(embed=embed_dm)
            except discord.Forbidden:
                pass

            await member.kick(reason=f"Kicked by {interaction.user} (ID: {interaction.user.id}): {reason}")
            
            embed = discord.Embed(
                title="👢 Member Kicked",
                description=f"**User:** {member.mention} (`{member.id}`)\n**Moderator:** {interaction.user.mention}\n**Reason:** {reason}",
                color=EMBED_COLOR_SUCCESS,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to kick user: {e}", ephemeral=True)

    # --- BAN ---
    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(member="The member to ban", reason="Reason for the ban", delete_message_days="Days of message history to delete (0 to 7)")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", delete_message_days: int = 1):
        if member.id == interaction.user.id:
            return await interaction.response.send_message("❌ You cannot ban yourself.", ephemeral=True)
        if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message("❌ You cannot ban someone with an equal or higher role than you.", ephemeral=True)
        if member.top_role >= interaction.guild.me.top_role:
            return await interaction.response.send_message("❌ I cannot ban this user because their role is higher than or equal to my highest role.", ephemeral=True)

        delete_seconds = max(0, min(7, delete_message_days)) * 86400

        try:
            try:
                embed_dm = discord.Embed(
                    title=f"Banned from {interaction.guild.name}",
                    description=f"**Reason:** {reason}\n**Moderator:** {interaction.user}",
                    color=EMBED_COLOR_ERROR
                )
                await member.send(embed=embed_dm)
            except discord.Forbidden:
                pass

            await member.ban(reason=f"Banned by {interaction.user} (ID: {interaction.user.id}): {reason}", delete_message_seconds=delete_seconds)
            
            embed = discord.Embed(
                title="🔨 Member Banned",
                description=f"**User:** {member.mention} (`{member.id}`)\n**Moderator:** {interaction.user.mention}\n**Reason:** {reason}\n**Message Purge:** {delete_message_days} days",
                color=EMBED_COLOR_SUCCESS,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to ban user: {e}", ephemeral=True)

    # --- UNBAN ---
    @app_commands.command(name="unban", description="Unban a user by their Discord User ID.")
    @app_commands.describe(user_id="The ID of the user to unban", reason="Reason for unbanning")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        try:
            uid = int(user_id)
            user = await self.bot.fetch_user(uid)
            await interaction.guild.unban(user, reason=f"Unbanned by {interaction.user}: {reason}")
            
            embed = discord.Embed(
                title="🔓 User Unbanned",
                description=f"**User:** {user.name} (`{user.id}`)\n**Moderator:** {interaction.user.mention}\n**Reason:** {reason}",
                color=EMBED_COLOR_SUCCESS,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            await interaction.response.send_message(embed=embed)
        except ValueError:
            await interaction.response.send_message("❌ Please provide a valid numeric User ID.", ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message("❌ User is not banned or could not be found.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error unbanning user: {e}", ephemeral=True)

    # --- TIMEOUT (MUTE) ---
    @app_commands.command(name="timeout", description="Timeout (mute) a member for a specified duration in minutes.")
    @app_commands.describe(member="The member to timeout", minutes="Duration in minutes (e.g. 5, 60, 1440)", reason="Reason for timeout")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
        if member.id == interaction.user.id:
            return await interaction.response.send_message("❌ You cannot timeout yourself.", ephemeral=True)
        if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message("❌ You cannot timeout someone with an equal or higher role than you.", ephemeral=True)
        if minutes <= 0 or minutes > 40320: # Discord max is 28 days (40320 mins)
            return await interaction.response.send_message("❌ Timeout duration must be between 1 and 40,320 minutes (28 days).", ephemeral=True)

        duration = datetime.timedelta(minutes=minutes)
        try:
            await member.timeout(duration, reason=f"Timeout by {interaction.user}: {reason}")
            embed = discord.Embed(
                title="⏳ Member Timed Out",
                description=f"**User:** {member.mention} (`{member.id}`)\n**Duration:** {minutes} minutes\n**Moderator:** {interaction.user.mention}\n**Reason:** {reason}",
                color=EMBED_COLOR_WARNING,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to timeout user: {e}", ephemeral=True)

    # --- UNTIMEOUT ---
    @app_commands.command(name="untimeout", description="Remove timeout from a member.")
    @app_commands.describe(member="The member to remove timeout from", reason="Reason for removing timeout")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        try:
            await member.timeout(None, reason=f"Untimeout by {interaction.user}: {reason}")
            embed = discord.Embed(
                title="🔊 Timeout Removed",
                description=f"**User:** {member.mention}\n**Moderator:** {interaction.user.mention}\n**Reason:** {reason}",
                color=EMBED_COLOR_SUCCESS,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to remove timeout: {e}", ephemeral=True)

    # --- CLEAR / PURGE MESSAGES ---
    @app_commands.command(name="clear", description="Purge a specified number of messages from this channel.")
    @app_commands.describe(amount="Number of messages to delete (1-100)", member="Filter messages only from this specific member (optional)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int, member: discord.Member = None):
        if amount <= 0 or amount > 100:
            return await interaction.response.send_message("❌ Amount must be between 1 and 100 messages.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        def check_msg(msg):
            if member:
                return msg.author.id == member.id
            return True

        deleted = await interaction.channel.purge(limit=amount, check=check_msg)
        filter_str = f" from {member.mention}" if member else ""
        await interaction.followup.send(f"🧹 Successfully cleared **{len(deleted)}** messages{filter_str}.", ephemeral=True)

    # --- WARN SYSTEM ---
    @app_commands.command(name="warn", description="Issue an official warning to a member.")
    @app_commands.describe(member="The member to warn", reason="Reason for the warning")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if member.bot:
            return await interaction.response.send_message("❌ You cannot warn bot accounts.", ephemeral=True)
        
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        total_warns = data_manager.add_warning(interaction.guild.id, member.id, reason, str(interaction.user), now_str)
        
        # Try to notify member via DM
        try:
            embed_dm = discord.Embed(
                title=f"⚠️ Warning in {interaction.guild.name}",
                description=f"You received an official warning.\n**Reason:** {reason}\n**Total Warnings:** {total_warns}",
                color=EMBED_COLOR_WARNING
            )
            await member.send(embed=embed_dm)
        except discord.Forbidden:
            pass

        embed = discord.Embed(
            title="⚠️ Member Warned",
            description=f"**User:** {member.mention} (`{member.id}`)\n**Reason:** {reason}\n**Moderator:** {interaction.user.mention}\n**Total Warnings:** {total_warns}",
            color=EMBED_COLOR_WARNING,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="warnings", description="View all warnings for a member.")
    @app_commands.describe(member="The member to check")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        warns = data_manager.get_warnings(interaction.guild.id, member.id)
        if not warns:
            return await interaction.response.send_message(f"✅ {member.mention} has no warnings on record.", ephemeral=True)

        embed = discord.Embed(
            title=f"📋 Warnings for {member.display_name}",
            description=f"Total: **{len(warns)}** warning(s)",
            color=EMBED_COLOR_WARNING
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        for w in warns[-10:]:  # Show up to 10 most recent
            embed.add_field(
                name=f"Warning #{w['id']} • {w['timestamp']}",
                value=f"**Reason:** {w['reason']}\n**Moderator:** {w['moderator']}",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarns", description="Clear all warnings for a member.")
    @app_commands.describe(member="The member whose warnings will be wiped")
    @app_commands.checks.has_permissions(administrator=True)
    async def clearwarns(self, interaction: discord.Interaction, member: discord.Member):
        count = data_manager.clear_warnings(interaction.guild.id, member.id)
        await interaction.response.send_message(f"✅ Cleared **{count}** warning(s) for {member.mention}.", ephemeral=True)

    # --- SLOWMODE ---
    @app_commands.command(name="slowmode", description="Set channel message cooldown / slowmode.")
    @app_commands.describe(seconds="Slowmode delay in seconds (0 to disable, up to 21600)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        if seconds < 0 or seconds > 21600:
            return await interaction.response.send_message("❌ Slowmode must be between 0 and 21,600 seconds (6 hours).", ephemeral=True)

        await interaction.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await interaction.response.send_message("⚡ Slowmode has been **disabled** for this channel.")
        else:
            await interaction.response.send_message(f"⏱️ Slowmode set to **{seconds} seconds** for {interaction.channel.mention}.")

    # --- LOCK & UNLOCK ---
    @app_commands.command(name="lock", description="Lock a text channel to prevent members from sending messages.")
    @app_commands.describe(channel="The channel to lock (defaults to current channel)", reason="Reason for locking")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = "Channel lockdown"):
        target_ch = channel or interaction.channel
        overwrite = target_ch.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await target_ch.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

        embed = discord.Embed(
            title="🔒 Channel Locked",
            description=f"{target_ch.mention} has been locked by {interaction.user.mention}.\n**Reason:** {reason}",
            color=EMBED_COLOR_ERROR
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unlock", description="Unlock a previously locked text channel.")
    @app_commands.describe(channel="The channel to unlock (defaults to current channel)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target_ch = channel or interaction.channel
        overwrite = target_ch.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None  # Reset to default
        await target_ch.set_permissions(interaction.guild.default_role, overwrite=overwrite)

        embed = discord.Embed(
            title="🔓 Channel Unlocked",
            description=f"{target_ch.mention} has been unlocked by {interaction.user.mention}.",
            color=EMBED_COLOR_SUCCESS
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
