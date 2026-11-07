import discord
from discord.ext import commands
from discord import app_commands
import io
import datetime
from config import EMBED_COLOR_TICKET, EMBED_COLOR_SUCCESS, EMBED_COLOR_ERROR
import data_manager

class TicketActionView(discord.ui.View):
    """Buttons inside an active ticket channel: Close and Transcript."""
    
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="btn_ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Confirmation view
        confirm_view = ConfirmCloseView()
        await interaction.response.send_message("⚠️ Are you sure you want to close and delete this ticket?", view=confirm_view, ephemeral=True)

    @discord.ui.button(label="Save Transcript", style=discord.ButtonStyle.secondary, emoji="📥", custom_id="btn_ticket_transcript")
    async def transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        
        lines = [f"=== TICKET TRANSCRIPT: {channel.name} ===", f"Generated at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}", ""]
        async for msg in channel.history(limit=500, oldest_first=True):
            timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"[{timestamp}] {msg.author.name}: {msg.content}")
            for att in msg.attachments:
                lines.append(f"    [Attachment: {att.url}]")

        file_data = "\n".join(lines).encode("utf-8")
        transcript_file = discord.File(io.BytesIO(file_data), filename=f"{channel.name}-transcript.txt")
        await interaction.followup.send("📄 Here is the transcript of this ticket:", file=transcript_file, ephemeral=True)

class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Yes, Close & Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Closing ticket in 5 seconds...")
        import asyncio
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.NotFound:
            pass

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Ticket closure cancelled.", view=None)

class TicketPanelView(discord.ui.View):
    """The persistent button on the ticket panel for users to create a new ticket."""
    
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="btn_create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user

        # Prevent duplicate open tickets for same user (owner ID is stored in the channel topic)
        existing_ch = next((ch for ch in guild.text_channels if ch.topic == f"ticket-owner:{member.id}"), None)
        if existing_ch:
            return await interaction.response.send_message(f"❌ You already have an open ticket: {existing_ch.mention}", ephemeral=True)

        cfg = data_manager.get_guild_data(guild.id)
        count = cfg.get("ticket_count", 0) + 1
        data_manager.update_guild_data(guild.id, "ticket_count", count)

        # Category
        cat_id = cfg.get("ticket_category_id")
        category = guild.get_channel(int(cat_id)) if cat_id else None

        # Permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        mod_id = cfg.get("mod_role_id")
        mod_role = guild.get_role(int(mod_id)) if mod_id else None
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True)

        channel_name = f"ticket-{count:04d}"
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            topic=f"ticket-owner:{member.id}",
            overwrites=overwrites,
            reason=f"Support ticket created by {member}"
        )

        embed = discord.Embed(
            title="🎫 Support Ticket Opened",
            description=(
                f"Welcome {member.mention}!\n\n"
                f"Please explain your question or issue in detail here. A member of the staff team will be with you shortly.\n\n"
                f"Use the buttons below to manage this ticket."
            ),
            color=EMBED_COLOR_TICKET,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text=f"Ticket #{count:04d} • Created by {member.name}")

        view = TicketActionView()
        await ticket_channel.send(content=f"{member.mention} Welcome to your ticket!", embed=embed, view=view)
        await interaction.response.send_message(f"✅ Your ticket has been created: {ticket_channel.mention}", ephemeral=True)

class Tickets(commands.Cog):
    """Interactive Support Ticket System with buttons, transcripts, and private channels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Register persistent views
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketActionView())

    ticket_group = app_commands.Group(name="tickets", description="Configure server support tickets")

    @ticket_group.command(name="setup_panel", description="Post the interactive ticket creation panel in a channel.")
    @app_commands.describe(
        channel="Channel where the ticket panel will be posted",
        title="Title of the ticket embed",
        description="Description explaining how to use tickets",
        category="Category channel where newly opened tickets will be placed (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str = "📩 Need Assistance? Open a Support Ticket!",
        description: str = "Click the button below to open a private ticket with our server staff.",
        category: discord.CategoryChannel = None
    ):
        if category:
            data_manager.update_guild_data(interaction.guild.id, "ticket_category_id", category.id)

        embed = discord.Embed(
            title=title,
            description=description,
            color=EMBED_COLOR_TICKET
        )
        embed.set_footer(text=f"{interaction.guild.name} Support System")

        view = TicketPanelView()
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Ticket panel successfully deployed in {channel.mention}!", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
