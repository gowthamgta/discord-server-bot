---
title: Kralveth
emoji: 🤖
colorFrom: indigo
colorTo: blue
sdk: gradio
app_file: app.py
pinned: false
---

# 🤖 Discord Server Manager Bot

A comprehensive, modular Discord server management bot written in **Python (`discord.py` v2.7+)** with **Discord Slash Commands (`/`)**, persistent UI buttons, and automated moderation systems.

---

## ⚡ Features Included

| Module | Features & Slash Commands |
| :--- | :--- |
| **🧠 RAG & Knowledge Base** | In-memory & persistent vector store, recursive character chunking with overlap, dense embeddings (Gemini `gemini-embedding-001`), grounded Q&A with source citations, multi-tenant server isolation (`/ask`, `/rag upload`, `/rag index_channel`, `/rag add_snippet`, `/rag search`, `/rag docs`, `/rag delete_doc`, `/rag clear`) |
| **🛡️ Core Moderation** | `/kick`, `/ban`, `/unban`, `/timeout` (mute), `/untimeout`, `/clear` (purge), `/warn`, `/warnings`, `/clearwarns`, `/slowmode`, `/lock`, `/unlock` |
| **👋 Welcome & Auto-Role** | Aesthetic greeting embeds with avatar & member count, farewell logs, `/welcome set_channel`, `/welcome set_autorole`, `/welcome test` |
| **🤖 Auto-Moderation** | Automatic anti-spam rate limiter, unauthorized Discord invite link blocker, blacklisted words filter (`/automod add_word`, `/automod remove_word`, `/automod list_words`) |
| **📋 Audit Logging** | Logs deleted messages, edited messages, member joins/leaves, account age alerts, and bans (`/logs set_channel`) |
| **🎫 Ticket Support System** | Interactive button panel (`/tickets setup_panel`), automated private channel creation, and 1-click transcript export |
| **🤖 Contextual AI Chatter** | Context-aware responses to random messages (e.g. 8% chance), 100% on mentions, and optional Google Gemini 2.5 Flash integration (`/chatter toggle`, `/chatter chance`, `/chatter set_channel`, `/chatter set_api_key`) |
| **👑 Server Design (Owner only)** | Template or Gemini-AI generated layouts with a preview + confirm step, correct role hierarchy, verification gate, and auto-wiring of every feature (`/design_server`, `/design_ai`, `/create_channel`, `/create_category`, `/delete_category`) |
| **🎭 Roles & Verification** | Persistent self-role button panels (`/roles panel`), verify button gate (`/verify setup`), `/role give`, `/role take`, `/role set_mod` |
| **📈 Leveling** | Message XP, level-up announcements, level role rewards (`/rank`, `/leaderboard`, `/levels ...`) |
| **🎉 Community** | Native polls, suggestions with vote reactions + threads, AFK, reminders, button giveaways, announcements (`/poll`, `/suggest`, `/afk`, `/remind`, `/giveaway`, `/announce`, `/say`) |
| **🔊 Voice & Stats** | Join-to-create private voice rooms (`/tempvoice setup`), live member counters (`/stats setup`) |
| **🎲 Fun & AI Tools** | `/8ball`, `/coinflip`, `/roll`, `/choose`, `/rps`, `/avatar`, AI `/summarize` and `/translate` |
| **⚙️ Server Utilities** | `/serverinfo`, `/userinfo`, `/botinfo`, `/ping`, `/reload` (owner), `/help` |

---


---

## 🧠 Retrieval-Augmented Generation (RAG) System Architecture

This bot features a production-grade, multi-tenant **Retrieval-Augmented Generation (RAG)** pipeline designed for Discord communities:

1. **Document Ingestion & Multi-Format Parsing**:
   - Parses `.pdf`, `.md`, `.txt`, `.json`, `.csv`, and Discord channel message histories directly into structured documents.
   - Preserves granular metadata (guild ID, channel ID, document source, page number, author, creation timestamp).

2. **Recursive Character Chunking**:
   - Splits text hierarchically using sentence and paragraph boundary separators (`\n\n`, `\n`, `. `, `? `, `! `, ` `).
   - Uses configurable chunk sizes (~550 chars) with sliding-window overlap (~90 chars) to prevent loss of context across boundaries.

3. **Dense Vector Embeddings & Offline Resilience**:
   - Primary: Google Gemini `gemini-embedding-001` (768-dimensional dense embeddings).
   - Fallback: Deterministic normalized term/character n-gram hashing vectorizer (384-dimensional) ensuring zero fatal crashes during network partitions or offline testing.

4. **In-Memory & Persistent Vector Store**:
   - High-throughput cosine similarity indexing powered by vectorized NumPy matrix multiplications (`M @ q`).
   - Multi-tenant tenant-level data isolation: vectors are strictly partitioned per Discord Guild.
   - Automated compressed persistence to disk (`data/rag_store/vectors.npz` and `chunks_meta.json`).

5. **Grounded Generation & Source Attribution**:
   - Semantic retrieval with confidence thresholding to prevent hallucination on out-of-domain questions.
   - Injects structured source tags and forces LLM grounding.
   - Formats Discord embeds with confidence percentages, source pills, and latency statistics.
   - Integrates directly with the bot's conversational chatter module (`cogs/chatter.py`) for contextual grounded conversations.


### 📊 Empirical Retrieval Quality & Latency Benchmark (20-Query Test Suite)

Evaluated via 	ests/eval_retrieval.py across an 8-document server corpus and 20 ground-truth query pairs:
- **Hit Rate @ Top-3 (Recall@3)**: **100.0% (20/20)**
- **Hit Rate @ Top-1 (Recall@1)**: **75.0% (15/20)**
- **Mean Reciprocal Rank (MRR)**: **0.867**
- **Average Vector Search Latency**: **0.08 ms** (P50: 0.07 ms, P95: 0.10 ms)

## 🚀 Step-by-Step Setup Guide (2 Minutes)

### Step 1: Create Your Bot on Discord Developer Portal
1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and sign in.
2. Click **New Application** (top right) and name your bot (e.g., `Server Guardian`).
3. In the left sidebar, click **Bot**:
   - Click **Reset Token** and copy your token.
   - **Crucial:** Scroll down to **Privileged Gateway Intents** and enable:
     - ✅ **Presence Intent**
     - ✅ **Server Members Intent** *(needed for welcome messages & auto-role)*
     - ✅ **Message Content Intent** *(needed for auto-moderation & anti-invite)*
   - Click **Save Changes**.

---

### Step 2: Configure Your Bot Token
Open `C:\Projects\discord_server_bot\.env` in any text editor and paste your token:
```env
DISCORD_TOKEN=your_copied_bot_token_here
TEST_GUILD_ID=
```
> *(Optional)* To sync slash commands immediately without waiting for Discord's global cache, right-click your Discord server name -> **Copy Server ID**, and paste it into `TEST_GUILD_ID`.

---

### Step 3: Invite the Bot to Your Server
1. In the Discord Developer Portal, go to **OAuth2** -> **URL Generator** in the left sidebar.
2. Under **SCOPES**, check:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Under **BOT PERMISSIONS**, select:
   - ✅ **Administrator** *(or Kick Members, Ban Members, Manage Channels, Manage Roles, Manage Messages, Moderate Members)*.
4. Copy the **Generated URL** at the bottom, paste it into your browser, select your server, and click **Authorize**.

---

### Step 4: Run the Bot
Double-click `run.bat` inside `C:\Projects\discord_server_bot\` or run:
```powershell
& "C:\Users\gotam\AppData\Local\Python\bin\python.exe" C:\Projects\discord_server_bot\bot.py
```

Once started, the bot will display:
```
==================================================
 Logged in as: Server Guardian (ID: 123456789)
 Connected to 1 server(s)
 discord.py version: 2.7.1
==================================================
```

---

## 📖 Quick Command Cheat Sheet

### Moderation
* `/kick member:@User reason:Rule violation` — Kicks the user and notifies them via DM.
* `/ban member:@User reason:Spam delete_message_days:1` — Bans the user and purges messages.
* `/unban user_id:123456789` — Unbans a user by their Discord ID.
* `/timeout member:@User minutes:60 reason:Cooldown` — Mutes a member for a given duration.
* `/clear amount:25 member:@User` — Purges up to 100 messages (with optional user filter).
* `/warn member:@User reason:Language` — Adds a formal warning to user record.
* `/warnings member:@User` — Shows all active warnings on record.
* `/lock channel:#general reason:Emergency lockdown` — Restricts sending messages.

### Server Setup & Automation
* `/welcome set_channel channel:#welcome` — Configures the welcome greeting channel.
* `/welcome set_autorole role:@Member` — Automatically gives the role to new members on join.
* `/welcome test` — Previews the welcome card.
* `/automod add_word word:scam` — Adds a word to the automatic deletion filter.
* `/automod toggle_invites enabled:True` — Blocks foreign discord server invite links.
* `/logs set_channel channel:#mod-logs` — Sends deleted/edited messages and audit logs here.
* `/tickets setup_panel channel:#support` — Deploys the interactive "Create Ticket" button panel.

### 🤖 Contextual AI Chatter
* **Talk to the AI:** just @mention the bot or reply to one of its messages — no command needed.
* `/persona edit` *(owner)* — Opens a box to set the AI's name, personality and speaking style (saved in `data/persona.txt`). `/persona view`, `/persona reset`.
* `/chatter toggle enabled:True` — Turns random conversational replies ON/OFF.
* `/chatter chance percent:10` — Sets the percentage chance (1-50%) for the bot to interject naturally.
* `/chatter set_channel channel:#ai-chat` — Sets a channel where the bot replies to 100% of messages.
* `/chatter set_api_key api_key:AIzaSy...` — Plugs in your free Google Gemini API key for advanced intelligence.
* `/chatter status` — Displays the active AI model, settings, and triggers.

### 👑 Owner Chat Actions
As the server owner, just tell the bot what to do when you mention or reply to it:
* *@Miyu make a text channel called clips in the GAMING category*
* *@Miyu timeout @spammer for 10 minutes* • *give @alice the Moderator role* • *lock this channel*
* *@Miyu start a giveaway for Nitro, 1 day, 2 winners* • *announce in #news that the tournament starts Friday*
* *@Miyu design the server with the gaming template* (shows the usual preview)
* *@Miyu ping @Sam and tell him dinner's ready* • *tag the Moderators in #staff-chat* • *ping everyone, the event starts now* (asks to Confirm)
  Only the owner can make Miyu ping. Her normal chat replies never ping anyone.

* *@Miyu from now on, greet every newcomer with a space pun* saves a **standing order** she follows in every chat (*list your standing orders*, *forget order 2*).

Kick, ban, delete, message purges and @everyone / @here pings show a **Confirm** button first. Only the owner's own message can trigger an action. Messages from anyone else are plain chat. Supported actions are listed in `owner_actions.py`.

### 🧠 AI Models (free tiers)
* **Chat** uses fast Gemini *lite* models first (`gemini-3.5-flash-lite`, ~1s, largest free daily quota); `/design_ai` uses the smarter `gemini-3-flash-preview` / `gemini-3.5-flash`.
* **Groq fallback** (`qwen/qwen3.8-27b`, `gpt-oss-120b`, `gpt-oss-20b`): each allows 1,000 requests/day and 8,000 tokens/min.
* A model that is rate-limited or overloaded is skipped automatically (1 minute, or 1 hour after a daily-quota error) and the next one is used. `/chatter status` shows which models are cooling down.
* Google doesn't publish fixed free-tier numbers; check your project's real limits in [Google AI Studio](https://aistudio.google.com).

### 👑 Server Designer (server owner only)
* `/design_server template:gaming` — Shows a preview of the layout; press **Build** to apply it.
  *(Templates: `gaming`, `tech`, `study`, `minimal`)*
* `/design_ai theme:anime fan club with art sharing and watch parties` — Gemini designs a custom layout for your theme.
* Options on both: `clean_existing:True` deletes all current channels first (asks for confirmation), `verification:True` hides the server until members press **Verify**.
* **Roles (top → bottom):** 👑 Owner (badge) › 🛡️ Admin › 🔨 Moderator › 🧰 Helper › 🤖 Bots › ⭐ VIP › 8 name colors › level rewards (🥉 Active 5, 🥈 Regular 15, 🥇 Veteran 30, 💠 Legend 50, given automatically) › 👥 Member › self-roles. Positions are set explicitly after creating them.
* **Panels:** self-role buttons, plus a "pick one" name-color picker.
* **Channels:** categories, text, voice and **forum** channels (falls back to text without Community), slowmode on busy media channels, staff-only areas for Admin/Moderator/Helper.
* **Server settings:** mentions-only notifications, only staff can ping @everyone, verification at least Medium, explicit-image filter, Discord's own join messages off. Stricter existing settings are never lowered.
* **Wiring:** welcome, logs, tickets, rules, suggestions, level-ups, AI chat, join-to-create voice, AFK channel and live stats counters.
* **`/fix_roles`** repairs an existing server without touching channels: adds missing roles (Helper, colors, level rewards), wires them, and puts the hierarchy in order. Optional `color_panel_channel` posts the color picker. Owners can also just tell the bot *fix the role order*.
* After building, drag the bot's role to the **top** of the role list in Server Settings → Roles.
* `/create_channel`, `/create_category`, `/delete_category` — Manual tweaks.

### 🎉 Community & Engagement
* `/poll question:Best snack? options:Pizza | Chips | Fruit hours:24`
* `/giveaway start prize:Nitro duration:1d winners:1` — Members press 🎉 Enter; winners are picked automatically.
* `/remind when:2h30m text:Start the stream` • `/afk reason:Sleeping` • `/suggest idea:...`
* `/levels reward level:10 role:@Regular` — Auto-role at a level. `/rank`, `/leaderboard`.
* `/roles panel channel:#roles role1:@Gamer role2:@Artist` — Self-role buttons.

---

## 🤗 Hosting on Hugging Face Spaces (current setup)

The Space uses the **Gradio SDK**: `app.py` starts the bot in the background and serves a small status page on port 7860.

1. **Secrets, not files.** In *Space Settings → Variables and secrets*, add `DISCORD_TOKEN`, `GEMINI_API_KEY`, `GROQ_API_KEY` and (optionally) `TEST_GUILD_ID`. Never upload `.env` to the Space. If it was ever uploaded to a public Space, reset all of those keys.
2. **Keep data across restarts.** A Space's disk is wiped on every restart/rebuild. Add two more secrets and the bot mirrors `data/` (levels, warnings, giveaways, reminders, settings, persona) to a private dataset:
   * `HF_TOKEN`: create at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) with **Write** access
   * `DATA_REPO`: e.g. `your-username/kralveth-bot-data` (created automatically as **private**)

   It restores on startup, uploads changes every 5 minutes, and saves once more when the Space shuts down. The logs show `Restored ...` / `Synced ...` lines.
3. **Stop it from sleeping.** Free Spaces go to sleep when nobody opens the web page for a while, which takes the bot offline. A free uptime monitor (e.g. UptimeRobot) pinging `https://YOUR-USERNAME-YOUR-SPACE.hf.space` every 15–30 minutes keeps it awake.
4. `/chatter set_api_key` only lasts until the next restart on Spaces; change keys in the Space secrets instead.

---

## ☁️ Free 24/7 Hosting (alternative: Oracle Cloud Always Free)

The bot stores levels, warnings, giveaways and the AI persona in `data/`, so it needs a host with a **persistent disk**. A free Linux VM is the best fit; hosts that sleep or wipe files on redeploy (Render/Replit free tiers) are not.

1. **Create the VM:** Sign up at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/) (a card is needed for identity checks; Always Free resources are not charged). Create a **Compute Instance** → image **Ubuntu 24.04**, shape **VM.Standard.A1.Flex** (Ampere, 1 OCPU / 6 GB is plenty) or **VM.Standard.E2.1.Micro**. Download the SSH key it offers. If you get "out of capacity", try another availability domain or retry later.
   *Alternative:* Google Cloud's free **e2-micro** in a US region works the same way.
2. **Upload the bot** from PowerShell on your PC (replace the key path and IP):
   ```powershell
   scp -i C:\path\to\key.key -r C:\Projects\discord_server_bot ubuntu@YOUR_VM_IP:~/
   ```
   This includes your `.env` — it goes only to your own server. No ports need to be opened; the bot only makes outgoing connections.
3. **Install and start** it on the VM:
   ```bash
   ssh -i C:\path\to\key.key ubuntu@YOUR_VM_IP
   cd ~/discord_server_bot && bash deploy/setup.sh
   ```
   It installs Python, the dependencies, and a `systemd` service that starts on boot and restarts on crashes.
4. **Stop the copy on your PC.** Two running copies with the same token make the bot answer everything twice.

**Updating later:** re-upload the changed files (not `data/`, or you'll overwrite live levels/warnings), then run `sudo systemctl restart discord-bot`. Logs: `journalctl -u discord-bot -f`.
