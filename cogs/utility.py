import discord
from discord.ext import commands
from discord import app_commands
import platform
import time
import datetime
from config import EMBED_COLOR_DEFAULT, EMBED_COLOR_SUCCESS
from checks import is_guild_owner

START_TIME = time.time()

class Utility(commands.Cog):
    """Server informational and utility commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- PING ---
    @app_commands.command(name="ping", description="Check the bot's WebSocket and API latency.")
    async def ping(self, interaction: discord.Interaction):
        t0 = time.perf_counter()
        await interaction.response.defer()
        t1 = time.perf_counter()
        api_latency = round((t1 - t0) * 1000)
        ws_latency = round(self.bot.latency * 1000)

        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"**WebSocket Latency:** `{ws_latency} ms`\n**API Response Time:** `{api_latency} ms`",
            color=EMBED_COLOR_SUCCESS
        )
        await interaction.followup.send(embed=embed)

    # --- SERVERINFO ---
    @app_commands.command(name="serverinfo", description="Display comprehensive information about this server.")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        owner = guild.owner or await self.bot.fetch_user(guild.owner_id)

        # Counts
        total_members = guild.member_count
        bots = sum(1 for m in guild.members if m.bot)
        humans = total_members - bots
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        roles = len(guild.roles)

        embed = discord.Embed(
            title=f"📊 Server Info — {guild.name}",
            color=EMBED_COLOR_DEFAULT,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="👑 Owner", value=f"{owner.mention} (`{owner.id}`)", inline=True)
        embed.add_field(name="🆔 Server ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="📅 Created On", value=f"<t:{int(guild.created_at.timestamp())}:D> (<t:{int(guild.created_at.timestamp())}:R>)", inline=False)
        embed.add_field(name="👥 Members", value=f"Total: **{total_members}**\nHumans: **{humans}** | Bots: **{bots}**", inline=True)
        embed.add_field(name="💬 Channels", value=f"Text: **{text_channels}** | Voice: **{voice_channels}**\nCategories: **{categories}**", inline=True)
        embed.add_field(name="🛡️ Security & Roles", value=f"Verification: **{str(guild.verification_level).capitalize()}**\nRoles: **{roles}**", inline=True)

        if guild.banner:
            embed.set_image(url=guild.banner.url)

        await interaction.response.send_message(embed=embed)

    # --- USERINFO ---
    @app_commands.command(name="userinfo", description="Display profile, roles, and join dates for a member.")
    @app_commands.describe(member="The member to view (defaults to yourself)")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        roles = [r.mention for r in target.roles[1:]]  # Exclude @everyone
        roles_str = ", ".join(roles) if roles else "None"
        if len(roles_str) > 1024:
            roles_str = f"{len(roles)} roles"

        embed = discord.Embed(
            title=f"👤 User Info — {target.display_name}",
            color=target.color if target.color.value != 0 else EMBED_COLOR_DEFAULT,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Tag / Name", value=f"`{target.name}`", inline=True)
        embed.add_field(name="User ID", value=f"`{target.id}`", inline=True)
        embed.add_field(name="Bot Account?", value="Yes" if target.bot else "No", inline=True)
        embed.add_field(name="📅 Account Created", value=f"<t:{int(target.created_at.timestamp())}:D> (<t:{int(target.created_at.timestamp())}:R>)", inline=False)
        embed.add_field(name="📥 Server Joined", value=f"<t:{int(target.joined_at.timestamp())}:D> (<t:{int(target.joined_at.timestamp())}:R>)" if target.joined_at else "Unknown", inline=False)
        embed.add_field(name=f"🎭 Roles [{len(roles)}]", value=roles_str, inline=False)

        await interaction.response.send_message(embed=embed)

    # --- BOTINFO ---
    @app_commands.command(name="botinfo", description="View bot system statistics, uptime, and versions.")
    async def botinfo(self, interaction: discord.Interaction):
        uptime_sec = int(time.time() - START_TIME)
        uptime_str = str(datetime.timedelta(seconds=uptime_sec))

        total_guilds = len(self.bot.guilds)
        total_users = sum(g.member_count or 0 for g in self.bot.guilds)

        embed = discord.Embed(
            title="🤖 Server Manager Bot Statistics",
            description="A comprehensive, modular management bot with slash commands.",
            color=EMBED_COLOR_DEFAULT
        )
        embed.add_field(name="⏱️ Uptime", value=f"`{uptime_str}`", inline=True)
        embed.add_field(name="🌐 Guilds", value=f"`{total_guilds}`", inline=True)
        embed.add_field(name="👥 Total Users", value=f"`{total_users}`", inline=True)
        embed.add_field(name="🐍 Python", value=f"`v{platform.python_version()}`", inline=True)
        embed.add_field(name="📦 discord.py", value=f"`v{discord.__version__}`", inline=True)
        embed.add_field(name="💻 Platform", value=f"`{platform.system()} {platform.release()}`", inline=True)

        await interaction.response.send_message(embed=embed)

    # --- HELP ---
    HELP_SECTIONS = [
        ("👑 Server Design (Owner only)",
         "`/design_server` — Build from a template (gaming, tech, study, minimal)\n"
         "`/design_ai` — Gemini AI designs a custom server for any theme\n"
         "`/fix_roles` — Add missing roles & fix the role order\n"
         "`/create_channel`, `/create_category`, `/delete_category`\n"
         "`/stats setup|remove`, `/tempvoice setup`, `/chatter set_api_key`, `/reload`"),
        ("🛡️ Moderation",
         "`/kick`, `/ban`, `/unban`, `/timeout`, `/untimeout`, `/clear`\n"
         "`/warn`, `/warnings`, `/clearwarns`, `/slowmode`, `/lock`, `/unlock`\n"
         "`/role give|take|set_mod`"),
        ("🤖 Auto-Mod & Logs",
         "`/automod add_word|remove_word|list_words|toggle_invites|toggle_spam`\n"
         "`/logs set_channel`"),
        ("👋 Welcome, Roles & Verification",
         "`/welcome set_channel|set_leave_channel|set_autorole|toggle|test`\n"
         "`/roles panel` — Self-role buttons\n"
         "`/verify setup` — Verify button that unlocks the server"),
        ("📈 Leveling",
         "`/rank`, `/leaderboard`\n"
         "`/levels toggle|set_channel|reward|rewards|reset`"),
        ("🎉 Community",
         "`/poll`, `/suggest`, `/suggestions set_channel`, `/afk`\n"
         "`/remind`, `/reminders list|cancel`\n"
         "`/giveaway start|end|reroll`, `/announce`, `/say`\n"
         "⏰ After a Disboard `/bump`, the bumper is pinged when the next bump is allowed (2h)"),
        ("🎫 Tickets", "`/tickets setup_panel` — Deploy the ticket button panel"),
        ("🧠 AI (Gemini)",
         "Say her name, mention her or reply to her to chat; she then follows that channel for 10 min • `/summarize`, `/translate`\n"
         "👑 Owner: just ask it to do things, e.g. *@bot timeout @x for 10m*, *ping @x*\n"
         "`/chatter toggle|chance|set_channel|status`, `/persona edit|view|reset` (owner)"),
        ("🎲 Fun", "`/8ball`, `/coinflip`, `/roll`, `/choose`, `/rps`, `/avatar`"),
        ("⚙️ Utility", "`/serverinfo`, `/userinfo`, `/botinfo`, `/ping`, `/help`"),
    ]

    @app_commands.command(name="help", description="Overview of all available bot commands.")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📚 Server Manager Bot — Command Reference",
            description="All commands use **Slash Commands (`/`)**. Commands marked owner-only can only be used by the server owner.",
            color=EMBED_COLOR_DEFAULT
        )
        for name, value in self.HELP_SECTIONS:
            embed.add_field(name=name, value=value, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- HOT RELOAD (INSTANT UPDATES) ---
    @app_commands.command(name="reload", description="[Owner] Hot-reload bot modules without restarting the bot process.")
    @app_commands.describe(cog="The module name to reload (e.g. moderation, welcome, tickets, or 'all')")
    @is_guild_owner()
    async def reload(self, interaction: discord.Interaction, cog: str = "all"):
        if cog.lower() == "all":
            reloaded = []
            failed = []
            for ext in list(self.bot.extensions.keys()):
                try:
                    await self.bot.reload_extension(ext)
                    reloaded.append(f"`{ext.split('.')[-1]}`")
                except Exception as e:
                    failed.append(f"`{ext.split('.')[-1]}` ({e})")
            
            msg = f"🔄 **Hot-Reloaded:** {', '.join(reloaded)}"
            if failed:
                msg += f"\n❌ **Failed:** {', '.join(failed)}"
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            ext_name = f"cogs.{cog}" if not cog.startswith("cogs.") else cog
            try:
                await self.bot.reload_extension(ext_name)
                await interaction.response.send_message(f"✅ Successfully reloaded `{ext_name}`!", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to reload `{ext_name}`: `{e}`", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
