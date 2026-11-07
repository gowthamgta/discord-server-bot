import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import time
from config import EMBED_COLOR_TICKET, EMBED_COLOR_DEFAULT
import data_manager
from utils import parse_duration


def _giveaway_embed(gw: dict, ended: bool = False, winners: list[int] | None = None) -> discord.Embed:
    if ended:
        winner_text = ", ".join(f"<@{w}>" for w in winners) if winners else "No valid entries 😢"
        desc = f"**Winner(s):** {winner_text}\n**Hosted by:** <@{gw['host_id']}>\n**Entries:** {len(gw['entrants'])}"
        color = EMBED_COLOR_DEFAULT
    else:
        desc = (
            f"Click **🎉 Enter** to join!\n\n"
            f"**Ends:** <t:{int(gw['end'])}:R> (<t:{int(gw['end'])}:f>)\n"
            f"**Winners:** {gw['winners']}\n**Hosted by:** <@{gw['host_id']}>\n**Entries:** {len(gw['entrants'])}"
        )
        color = EMBED_COLOR_TICKET
    embed = discord.Embed(title=f"🎁 {gw['prize']}", description=desc, color=color)
    embed.set_footer(text="Giveaway ended" if ended else "Good luck!")
    return embed


class GiveawayView(discord.ui.View):
    """Persistent entry button. Giveaway state is looked up by the message ID."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enter", style=discord.ButtonStyle.success, emoji="🎉", custom_id="btn_giveaway_enter")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = data_manager.get_guild_data(interaction.guild.id)
        gw = cfg["giveaways"].get(str(interaction.message.id))
        if not gw or gw.get("ended"):
            return await interaction.response.send_message("❌ This giveaway has ended.", ephemeral=True)

        uid = interaction.user.id
        if uid in gw["entrants"]:
            gw["entrants"].remove(uid)
            msg = "↩️ You left the giveaway."
        else:
            gw["entrants"].append(uid)
            msg = "🎉 You're in! Good luck."
        data_manager.save()
        await interaction.response.send_message(msg, ephemeral=True)
        try:
            await interaction.message.edit(embed=_giveaway_embed(gw))
        except discord.HTTPException:
            pass


class Giveaways(commands.Cog):
    """Button-based giveaways with automatic ending, reroll, and persistence across restarts."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(GiveawayView())
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    async def _finish(self, guild: discord.Guild, message_id: str, gw: dict, reroll: bool = False) -> list[int]:
        entrants = [uid for uid in gw["entrants"] if guild.get_member(uid)]
        winners = random.sample(entrants, min(gw["winners"], len(entrants)))
        gw["ended"] = True
        data_manager.save()

        channel = guild.get_channel(gw["channel_id"])
        if not channel:
            return winners
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.edit(embed=_giveaway_embed(gw, ended=True, winners=winners), view=None)
        except discord.HTTPException:
            msg = None
        if winners:
            text = f"🎉 {'New winner' if reroll else 'Congratulations'} {', '.join(f'<@{w}>' for w in winners)}! You won **{gw['prize']}**!"
        else:
            text = f"😢 Nobody entered the giveaway for **{gw['prize']}**."
        await channel.send(text, reference=msg if msg else None)
        return winners

    @tasks.loop(seconds=15)
    async def check_giveaways(self):
        now = time.time()
        for guild in self.bot.guilds:
            giveaways = data_manager.get_guild_data(guild.id).get("giveaways", {})
            # Forget giveaways that ended over 14 days ago (rerolls only make sense shortly after)
            stale = [mid for mid, gw in giveaways.items() if gw.get("ended") and gw["end"] < now - 14 * 86400]
            for mid in stale:
                del giveaways[mid]
            if stale:
                data_manager.save()
            for message_id, gw in list(giveaways.items()):
                if not gw.get("ended") and gw["end"] <= now:
                    try:
                        await self._finish(guild, message_id, gw)
                    except Exception:
                        gw["ended"] = True
                        data_manager.save()

    @check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    giveaway_group = app_commands.Group(name="giveaway", description="Run giveaways")

    @giveaway_group.command(name="start", description="Start a giveaway with an Enter button.")
    @app_commands.describe(prize="What are you giving away?", duration="e.g. 30m, 2h, 1d", winners="Number of winners", channel="Where to post it")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def start(self, interaction: discord.Interaction, prize: str, duration: str,
                    winners: app_commands.Range[int, 1, 20] = 1, channel: discord.TextChannel = None):
        seconds = parse_duration(duration)
        if not seconds or seconds < 30 or seconds > 30 * 86400:
            return await interaction.response.send_message("❌ Duration must be between 30s and 30d, e.g. `30m`, `2h`, `1d12h`.", ephemeral=True)

        target = channel or interaction.channel
        gw = {"channel_id": target.id, "prize": prize[:200], "end": time.time() + seconds,
              "winners": winners, "host_id": interaction.user.id, "entrants": [], "ended": False}
        msg = await target.send(embed=_giveaway_embed(gw), view=GiveawayView())
        data_manager.get_guild_data(interaction.guild.id)["giveaways"][str(msg.id)] = gw
        data_manager.save()
        await interaction.response.send_message(f"✅ Giveaway started in {target.mention}!", ephemeral=True)

    @giveaway_group.command(name="end", description="End a giveaway early.")
    @app_commands.describe(message_id="Message ID of the giveaway")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def end(self, interaction: discord.Interaction, message_id: str):
        gw = data_manager.get_guild_data(interaction.guild.id)["giveaways"].get(message_id.strip())
        if not gw or gw.get("ended"):
            return await interaction.response.send_message("❌ No running giveaway with that message ID.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self._finish(interaction.guild, message_id.strip(), gw)
        await interaction.followup.send("✅ Giveaway ended.", ephemeral=True)

    @giveaway_group.command(name="reroll", description="Pick new winner(s) for an ended giveaway.")
    @app_commands.describe(message_id="Message ID of the giveaway")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reroll(self, interaction: discord.Interaction, message_id: str):
        gw = data_manager.get_guild_data(interaction.guild.id)["giveaways"].get(message_id.strip())
        if not gw or not gw.get("ended"):
            return await interaction.response.send_message("❌ That giveaway doesn't exist or hasn't ended yet.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self._finish(interaction.guild, message_id.strip(), gw, reroll=True)
        await interaction.followup.send("🔄 Rerolled.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))
