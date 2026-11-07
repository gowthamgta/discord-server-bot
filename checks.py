import discord
from discord import app_commands


class NotGuildOwner(app_commands.CheckFailure):
    """Raised when a non-owner tries to use an owner-only command."""
    pass


def is_guild_owner():
    """Restricts a slash command to the server owner only."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None or interaction.user.id != interaction.guild.owner_id:
            raise NotGuildOwner("Only the server owner can use this command.")
        return True
    return app_commands.check(predicate)
