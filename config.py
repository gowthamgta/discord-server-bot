import os
from dotenv import load_dotenv

load_dotenv()

# Discord Bot Credentials
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID", None)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Default Bot Appearance
EMBED_COLOR_DEFAULT = 0x5865F2    # Discord Blurple
EMBED_COLOR_SUCCESS = 0x57F287    # Green
EMBED_COLOR_WARNING = 0xFEE75C    # Yellow
EMBED_COLOR_ERROR = 0xED4245      # Red
EMBED_COLOR_TICKET = 0xEB459E     # Pink
EMBED_COLOR_AI = 0x8B5CF6         # Modern Violet

# Data Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STORAGE_FILE = os.path.join(DATA_DIR, "server_data.json")

os.makedirs(DATA_DIR, exist_ok=True)
