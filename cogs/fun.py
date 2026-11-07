import discord
from discord.ext import commands
from discord import app_commands
import random
import re
from typing import Literal
from config import EMBED_COLOR_DEFAULT, EMBED_COLOR_AI
from rate_limiter import gemini_queue

EIGHT_BALL = [
    "It is certain.", "Without a doubt.", "You may rely on it.", "Yes, definitely.", "Most likely.",
    "Outlook good.", "Signs point to yes.", "Reply hazy, try again.", "Ask again later.",
    "Better not tell you now.", "Cannot predict now.", "Don't count on it.", "My reply is no.",
    "My sources say no.", "Outlook not so good.", "Very doubtful."
]


class Fun(commands.Cog):
    """Games, random tools, and AI-powered helpers (summarize, translate)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="8ball", description="Ask the magic 8-ball a yes/no question.")
    async def eight_ball(self, interaction: discord.Interaction, question: app_commands.Range[str, 1, 300]):
        embed = discord.Embed(title="🎱 Magic 8-Ball", color=EMBED_COLOR_DEFAULT)
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=random.choice(EIGHT_BALL), inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coinflip", description="Flip a coin.")
    async def coinflip(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🪙 **{random.choice(['Heads', 'Tails'])}!**")

    @app_commands.command(name="roll", description="Roll dice, e.g. 1d20, 2d6+3.")
    async def roll(self, interaction: discord.Interaction, dice: str = "1d6"):
        match = re.fullmatch(r"(\d{0,2})d(\d{1,4})([+-]\d{1,4})?", dice.replace(" ", "").lower())
        if not match:
            return await interaction.response.send_message("❌ Use dice notation like `1d20`, `2d6`, or `3d8+2`.", ephemeral=True)
        count, sides, mod = int(match.group(1) or 1), int(match.group(2)), int(match.group(3) or 0)
        if not (1 <= count <= 50 and 2 <= sides <= 1000):
            return await interaction.response.send_message("❌ 1–50 dice with 2–1000 sides.", ephemeral=True)
        rolls = [random.randint(1, sides) for _ in range(count)]
        mod_text = f" {'+' if mod >= 0 else '-'} {abs(mod)}" if mod else ""
        await interaction.response.send_message(f"🎲 `{dice}` → {', '.join(map(str, rolls))}{mod_text} = **{sum(rolls) + mod}**")

    @app_commands.command(name="choose", description="Let the bot pick for you. Separate options with |")
    async def choose(self, interaction: discord.Interaction, options: str):
        choices = [o.strip() for o in options.split("|") if o.strip()]
        if len(choices) < 2:
            return await interaction.response.send_message("❌ Give me at least 2 options separated by `|`.", ephemeral=True)
        await interaction.response.send_message(f"🤔 I choose: **{random.choice(choices)}**")

    @app_commands.command(name="rps", description="Play rock-paper-scissors against the bot.")
    async def rps(self, interaction: discord.Interaction, choice: Literal["rock", "paper", "scissors"]):
        bot_choice = random.choice(["rock", "paper", "scissors"])
        emoji = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
        beats = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
        if choice == bot_choice:
            result = "It's a **tie**!"
        elif beats[choice] == bot_choice:
            result = "You **win**! 🎉"
        else:
            result = "I **win**! 😎"
        await interaction.response.send_message(f"{emoji[choice]} vs {emoji[bot_choice]} — {result}")

    @app_commands.command(name="avatar", description="Show a member's avatar in full size.")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        embed = discord.Embed(title=f"🖼️ {target.display_name}'s Avatar", color=EMBED_COLOR_DEFAULT)
        embed.set_image(url=target.display_avatar.with_size(1024).url)
        await interaction.response.send_message(embed=embed)

    # --- AI HELPERS (share the 13 RPM Gemini queue) ---
    async def _ai(self, interaction: discord.Interaction, prompt: str, title: str):
        if not gemini_queue.is_gemini_active:
            return await interaction.response.send_message("❌ Gemini AI is not configured.", ephemeral=True)
        remaining = gemini_queue.check_user_cooldown(interaction.user.id)
        if remaining > 0:
            return await interaction.response.send_message(f"⏳ Please wait **{remaining:.1f}s** before another AI request.", ephemeral=True)
        await interaction.response.defer(thinking=True)
        try:
            answer = await gemini_queue.ask_gemini(prompt)
        except Exception as e:
            msg = "❌ Rate limit reached. Please try again shortly." if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) else "❌ The AI could not answer right now."
            return await interaction.followup.send(msg)
        embed = discord.Embed(title=title, description=answer[:4000], color=EMBED_COLOR_AI)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="summarize", description="AI summary of the recent messages in this channel.")
    @app_commands.describe(messages="How many recent messages to summarize (10-100)")
    async def summarize(self, interaction: discord.Interaction, messages: app_commands.Range[int, 10, 100] = 50):
        lines = []
        async for m in interaction.channel.history(limit=messages):
            if m.content and not m.author.bot:
                lines.append(f"{m.author.display_name}: {m.clean_content[:300]}")
        if len(lines) < 3:
            return await interaction.response.send_message("Not enough conversation here to summarize.", ephemeral=True)
        lines.reverse()
        prompt = (
            "Summarize this Discord conversation in 3-6 short bullet points. Mention who said what when useful. "
            "Be neutral and concise.\n\n" + "\n".join(lines)
        )
        await self._ai(interaction, prompt, f"📝 Summary of the last {messages} messages")

    @app_commands.command(name="translate", description="Translate text into another language with AI.")
    async def translate(self, interaction: discord.Interaction, text: app_commands.Range[str, 1, 1500], language: str = "English"):
        prompt = f"Translate the following text into {language}. Reply with only the translation.\n\n{text}"
        await self._ai(interaction, prompt, f"🌐 Translation → {language}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
