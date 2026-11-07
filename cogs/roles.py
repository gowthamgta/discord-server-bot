import discord
from discord.ext import commands
from discord import app_commands
from config import EMBED_COLOR_DEFAULT, EMBED_COLOR_SUCCESS
import data_manager

# Permissions that must never be handed out through a self-service button
DANGEROUS_PERMS = discord.Permissions(
    administrator=True, manage_guild=True, manage_roles=True, manage_channels=True,
    kick_members=True, ban_members=True, manage_messages=True, moderate_members=True,
    mention_everyone=True, manage_webhooks=True, manage_nicknames=True, view_audit_log=True
)


def is_safe_self_role(role: discord.Role, bot_member: discord.Member) -> bool:
    """A role is safe for self-assignment if it grants no staff powers and the bot can assign it."""
    return (
        not role.is_default()
        and not role.managed
        and role < bot_member.top_role
        and (role.permissions.value & DANGEROUS_PERMS.value) == 0
    )


class SelfRoleButton(discord.ui.DynamicItem[discord.ui.Button], template=r"selfrole:(?P<role_id>\d+)"):
    """Persistent toggle button. The role ID lives in the custom_id, so it survives bot restarts."""

    def __init__(self, role_id: int, label: str = "Role"):
        super().__init__(discord.ui.Button(label=label[:80], style=discord.ButtonStyle.secondary, custom_id=f"selfrole:{role_id}"))
        self.role_id = role_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(int(match["role_id"]))

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            return await interaction.response.send_message("❌ This role no longer exists.", ephemeral=True)
        if not is_safe_self_role(role, interaction.guild.me):
            return await interaction.response.send_message("❌ I can't assign this role (it is above me or has staff permissions).", ephemeral=True)

        member = interaction.user
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Self-role panel")
                await interaction.response.send_message(f"➖ Removed {role.mention}.", ephemeral=True)
            else:
                await member.add_roles(role, reason="Self-role panel")
                await interaction.response.send_message(f"➕ Added {role.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to manage that role.", ephemeral=True)


class ColorRoleButton(discord.ui.DynamicItem[discord.ui.Button], template=r"colorrole:(?P<role_id>\d+)"):
    """Name-color picker: a member holds at most one color role from the server's color list."""

    def __init__(self, role_id: int, label: str = "Color"):
        super().__init__(discord.ui.Button(label=label[:80], style=discord.ButtonStyle.secondary, custom_id=f"colorrole:{role_id}"))
        self.role_id = role_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(int(match["role_id"]))

    async def callback(self, interaction: discord.Interaction):
        guild, member = interaction.guild, interaction.user
        role = guild.get_role(self.role_id)
        if not role or not is_safe_self_role(role, guild.me):
            return await interaction.response.send_message("❌ That color isn't available anymore.", ephemeral=True)
        color_ids = set(data_manager.get_guild_data(guild.id).get("color_role_ids", [])) | {role.id}
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Color picker")
                return await interaction.response.send_message("🎨 Color removed.", ephemeral=True)
            old = [r for r in member.roles if r.id in color_ids and r.id != role.id]
            if old:
                await member.remove_roles(*old, reason="Color picker: swap")
            await member.add_roles(role, reason="Color picker")
            await interaction.response.send_message(f"🎨 Your name color is now {role.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to manage that role.", ephemeral=True)


def build_color_view(roles: list[discord.Role]) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for role in roles[:25]:
        view.add_item(ColorRoleButton(role.id, role.name))
    return view


def build_selfrole_view(roles: list[discord.Role]) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for role in roles[:25]:
        view.add_item(SelfRoleButton(role.id, role.name))
    return view


class VerifyView(discord.ui.View):
    """Persistent verify button that grants the configured verified role."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_verify")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = data_manager.get_guild_data(interaction.guild.id)
        role_id = cfg.get("verify_role_id")
        role = interaction.guild.get_role(int(role_id)) if role_id else None
        if not role:
            return await interaction.response.send_message("⚠️ Verification is not configured. Ask an admin to run `/verify setup`.", ephemeral=True)
        if role in interaction.user.roles:
            return await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
        try:
            await interaction.user.add_roles(role, reason="Verified via button")
            await interaction.response.send_message(f"🎉 You're verified! Welcome to **{interaction.guild.name}**.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I can't assign the verified role — my role must be above it.", ephemeral=True)


class Roles(commands.Cog):
    """Self-assignable role panels, verification gate, and staff role management."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_dynamic_items(SelfRoleButton, ColorRoleButton)
        self.bot.add_view(VerifyView())

    async def cog_unload(self):
        self.bot.remove_dynamic_items(SelfRoleButton, ColorRoleButton)

    roles_group = app_commands.Group(name="roles", description="Self-assignable role panels")

    @roles_group.command(name="panel", description="Post a button panel that lets members pick their own roles.")
    @app_commands.describe(channel="Where to post the panel", title="Panel title", description="Panel description")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def panel(self, interaction: discord.Interaction, channel: discord.TextChannel, role1: discord.Role,
                    role2: discord.Role = None, role3: discord.Role = None, role4: discord.Role = None,
                    role5: discord.Role = None, role6: discord.Role = None, role7: discord.Role = None,
                    role8: discord.Role = None, title: str = "🎭 Pick Your Roles",
                    description: str = "Click a button to add or remove a role."):
        roles = [r for r in (role1, role2, role3, role4, role5, role6, role7, role8) if r]
        unsafe = [r for r in roles if not is_safe_self_role(r, interaction.guild.me)]
        if unsafe:
            return await interaction.response.send_message(
                f"❌ These roles can't be self-assigned (staff permissions, managed, or above my role): {', '.join(r.mention for r in unsafe)}",
                ephemeral=True
            )
        embed = discord.Embed(title=title, description=description + "\n\n" + "\n".join(f"• {r.mention}" for r in roles), color=EMBED_COLOR_DEFAULT)
        await channel.send(embed=embed, view=build_selfrole_view(roles))
        await interaction.response.send_message(f"✅ Role panel posted in {channel.mention}.", ephemeral=True)

    # --- VERIFICATION ---
    verify_group = app_commands.Group(name="verify", description="Member verification gate")

    @verify_group.command(name="setup", description="Post a verify button that grants a role (e.g. Member).")
    @app_commands.describe(channel="Where to post the verify button", role="Role given after verifying")
    @app_commands.checks.has_permissions(administrator=True)
    async def verify_setup(self, interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
        if not is_safe_self_role(role, interaction.guild.me):
            return await interaction.response.send_message("❌ That role has staff permissions or is above my highest role.", ephemeral=True)
        data_manager.update_guild_data(interaction.guild.id, "verify_role_id", role.id)
        embed = discord.Embed(
            title="✅ Verification",
            description=f"Welcome to **{interaction.guild.name}**!\nRead the rules, then press the button below to unlock the server.",
            color=EMBED_COLOR_SUCCESS
        )
        await channel.send(embed=embed, view=VerifyView())
        await interaction.response.send_message(
            f"✅ Verify panel posted in {channel.mention}. Members get {role.mention}.\n"
            "Tip: hide your other channels from `@everyone` and allow them for this role.",
            ephemeral=True
        )

    # --- STAFF ROLE MANAGEMENT ---
    role_group = app_commands.Group(name="role", description="Give or take roles from members")

    def _can_manage(self, interaction: discord.Interaction, role: discord.Role) -> str | None:
        if role >= interaction.guild.me.top_role:
            return "❌ That role is above or equal to my highest role."
        if interaction.user.id != interaction.guild.owner_id and role >= interaction.user.top_role:
            return "❌ You can't manage a role equal to or above your own highest role."
        if role.managed or role.is_default():
            return "❌ That role is managed by an integration and can't be assigned."
        return None

    @role_group.command(name="give", description="Give a role to a member.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_give(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if err := self._can_manage(interaction, role):
            return await interaction.response.send_message(err, ephemeral=True)
        await member.add_roles(role, reason=f"Given by {interaction.user}")
        await interaction.response.send_message(f"✅ Gave {role.mention} to {member.mention}.", allowed_mentions=discord.AllowedMentions.none())

    @role_group.command(name="take", description="Remove a role from a member.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_take(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if err := self._can_manage(interaction, role):
            return await interaction.response.send_message(err, ephemeral=True)
        await member.remove_roles(role, reason=f"Removed by {interaction.user}")
        await interaction.response.send_message(f"✅ Removed {role.mention} from {member.mention}.", allowed_mentions=discord.AllowedMentions.none())

    @role_group.command(name="set_mod", description="[Admin] Set the moderator role (gets access to tickets).")
    @app_commands.checks.has_permissions(administrator=True)
    async def role_set_mod(self, interaction: discord.Interaction, role: discord.Role):
        data_manager.update_guild_data(interaction.guild.id, "mod_role_id", role.id)
        await interaction.response.send_message(f"✅ {role.mention} is now the moderator role.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
