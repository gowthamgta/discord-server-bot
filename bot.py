import os
import sys
import signal
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands, tasks
from discord import app_commands
import config
import storage_sync
from checks import NotGuildOwner

# Force UTF-8 on Windows consoles to prevent Unicode errors with server names and emojis.
# line_buffering: hosted containers (e.g. Hugging Face) otherwise hold output back until the buffer fills.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

# Setup logging. force=True: libraries imported earlier (Gradio, spaces) may have already configured
# logging, which would otherwise make this call a silent no-op and hide every INFO line.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout),
              # Same lines saved to bot.log (max 1 MB, 2 old copies) so problems can be read later
              RotatingFileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.log"),
                                  maxBytes=1_000_000, backupCount=2, encoding="utf-8")],
    force=True
)
logger = logging.getLogger("DiscordManagerBot")
# Libraries that log every single HTTP request; keep only their warnings
for noisy in ("google_genai", "httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

# Define intents
intents = discord.Intents.all()

class ManagerBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",  # Prefix for legacy fallback; primarily slash commands
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        # Save data/ to the Hugging Face dataset before the process is stopped.
        # Only possible when bot.py is the main thread; app.py handles SIGTERM itself.
        try:
            asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(self.close()))
        except (NotImplementedError, RuntimeError, ValueError):
            pass
        if storage_sync.is_enabled():
            self.sync_data.start()

        # Load all cogs dynamically
        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
        for filename in os.listdir(cogs_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                extension = f"cogs.{filename[:-3]}"
                try:
                    await self.load_extension(extension)
                    logger.info(f"Loaded extension: {extension}")
                except Exception as e:
                    logger.error(f"Failed to load extension {extension}: {e}")

        # Every command is server-scoped, so hide them all from DMs
        for cmd in self.tree.get_commands():
            cmd.guild_only = True

        # Slash Command Syncing
        if config.TEST_GUILD_ID:
            try:
                guild_obj = discord.Object(id=int(config.TEST_GUILD_ID))
                self.tree.copy_global_to(guild=guild_obj)
                synced = await self.tree.sync(guild=guild_obj)
                logger.info(f"Synced {len(synced)} slash commands immediately to test guild: {config.TEST_GUILD_ID}")
            except Exception as e:
                logger.error(f"Failed to sync commands to test guild: {e}")
        else:
            try:
                synced = await self.tree.sync()
                logger.info(f"Globally synced {len(synced)} slash commands.")
            except Exception as e:
                logger.error(f"Failed to sync global commands: {e}")

    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.application_command:
            logger.info(f"Slash command /{interaction.data.get('name')} used by {interaction.user} "
                        f"(id {interaction.user.id}, server owner: "
                        f"{bool(interaction.guild) and interaction.user.id == interaction.guild.owner_id})")

    async def on_ready(self):
        logger.info("==================================================")
        logger.info(f" Logged in as: {self.user.name} (ID: {self.user.id})")
        logger.info(f" Connected to {len(self.guilds)} server(s)")
        logger.info(f" discord.py version: {discord.__version__}")
        logger.info("==================================================")
        
        # Set Bot Presence
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"over {len(self.guilds)} server(s) | /help"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

    @tasks.loop(minutes=5)
    async def sync_data(self):
        await asyncio.to_thread(storage_sync.upload_changes)

    async def close(self):
        if storage_sync.is_enabled():
            logger.info("Shutting down: saving data to Hugging Face dataset...")
            await asyncio.to_thread(storage_sync.upload_changes)
        await super().close()

bot = ManagerBot()

# --- GLOBAL SLASH COMMAND ERROR HANDLER ---
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, NotGuildOwner):
        logger.warning(f"/{interaction.command and interaction.command.qualified_name} refused: "
                       f"{interaction.user} (id {interaction.user.id}) is not the server owner "
                       f"(owner id {interaction.guild and interaction.guild.owner_id})")
        msg = "👑 **Owner Only:** Only the server owner can use this command."
    elif isinstance(error, app_commands.MissingPermissions):
        perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
        msg = f"🚫 **Permission Denied:** You need the {perms} permission(s) to use this command."
    elif isinstance(error, app_commands.BotMissingPermissions):
        perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
        msg = f"⚠️ **Bot Missing Permissions:** I need the {perms} permission(s) to execute this command."
    elif isinstance(error, app_commands.CommandOnCooldown):
        msg = f"⏳ **Cooldown:** Please wait `{round(error.retry_after, 1)}s` before trying again."
    elif isinstance(error, app_commands.CheckFailure):
        logger.warning(f"/{interaction.command and interaction.command.qualified_name} blocked by a check: {error!r}")
        msg = "🚫 You are not allowed to use this command here."
    else:
        logger.error(f"Unhandled app command error in {interaction.command}: {error}", exc_info=True)
        msg = f"❌ An unexpected error occurred while executing this command: `{error}`"

    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except discord.HTTPException:
        pass

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is online and running 24/7!")

    def log_message(self, format, *args):
        # Keep logs clean by ignoring HTTP access logs
        pass

def start_health_server():
    # Only web hosts that hand out a port (Hugging Face sets SPACE_ID, others PORT) need the status page
    if os.environ.get("HEALTH_SERVER_DISABLED") == "1" or not (os.environ.get("PORT") or os.environ.get("SPACE_ID")):
        return
    port = int(os.environ.get("PORT", 7860))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        logger.info(f"Health check web server running on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.warning(f"Health check web server could not start on port {port}: {e}")

def main():
    threading.Thread(target=start_health_server, daemon=True).start()
    token = config.DISCORD_TOKEN.strip()
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("\n" + "=" * 60)
        print(" [!] DISCORD_TOKEN is missing!")
        print(" Locally: add it to the .env file.")
        print(" On Hugging Face: add it under Space Settings -> Variables and secrets.")
        print("=" * 60 + "\n")
        sys.exit(1)

    # Pull saved data/ from the HF dataset before anything reads it
    storage_sync.restore()
    try:
        bot.run(token, log_handler=None)
    except discord.LoginFailure:
        logger.error("Discord rejected DISCORD_TOKEN. It is wrong or was reset: copy a fresh one from the "
                     "Developer Portal (Bot -> Reset Token) into your .env / Space secret.")
    except discord.PrivilegedIntentsRequired:
        logger.error("Enable the Presence, Server Members and Message Content intents in the "
                     "Developer Portal (Bot -> Privileged Gateway Intents), then restart.")

if __name__ == "__main__":
    main()
