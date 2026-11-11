"""/config … — every setting is changed from Discord."""

import discord
from discord import app_commands
from discord.ext import commands

from core import COLOR, cfg, mention_channel, mention_role, store


class Settings(commands.Cog):
    config = app_commands.Group(name="config", description="Bot settings (admins only)",
                                default_permissions=discord.Permissions(manage_guild=True), guild_only=True)

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _set(self, interaction: discord.Interaction, key: str, value, text: str):
        cfg(interaction.guild)[key] = value
        await store.save()
        await interaction.response.send_message(f"✅ {text}", ephemeral=True)

    @config.command(name="support-role", description="Staff role that handles tickets and applications")
    async def support_role(self, interaction: discord.Interaction, role: discord.Role):
        await self._set(interaction, "support_role", role.id, f"Staff role set to {role.mention}")

    @config.command(name="log-channel", description="Channel for ticket logs and transcripts")
    async def log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._set(interaction, "log_channel", channel.id, f"Ticket logs → {channel.mention}")

    @config.command(name="mod-log", description="Channel for warns, kicks, bans and timeouts")
    async def mod_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._set(interaction, "mod_log", channel.id, f"Moderation logs → {channel.mention}")

    @config.command(name="category", description="Category where new tickets are created")
    async def category(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await self._set(interaction, "category", category.id, f"Tickets will be created in **{category.name}**")

    @config.command(name="autoclose", description="Auto-close tickets after X hours without messages (0 = off)")
    async def autoclose(self, interaction: discord.Interaction, hours: app_commands.Range[int, 0, 720]):
        await self._set(interaction, "autoclose_hours", hours,
                        "Auto-close turned off" if hours == 0 else f"Tickets auto-close after {hours}h of silence")

    @config.command(name="server", description="Your FiveM server address for /status (e.g. 123.45.67.89:30120)")
    @app_commands.describe(address="IP:port of the FiveM server",
                           connect_link="Optional cfx.re/join link shown to players")
    async def server(self, interaction: discord.Interaction, address: str, connect_link: str | None = None):
        address = address.strip().removeprefix("http://").removeprefix("https://").rstrip("/")
        if ":" not in address:
            address += ":30120"
        g = cfg(interaction.guild)
        g["server_ip"] = address
        g["connect_link"] = connect_link
        await store.save()
        await interaction.response.send_message(
            f"✅ Server set to `{address}`. Try `/status` now.", ephemeral=True)

    @config.command(name="welcome-channel", description="Channel for welcome messages")
    async def welcome_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._set(interaction, "welcome_channel", channel.id, f"Welcome messages → {channel.mention}")

    @config.command(name="verify-role", description="Role given when someone accepts the rules")
    async def verify_role(self, interaction: discord.Interaction, role: discord.Role):
        await self._set(interaction, "verify_role", role.id, f"Verify role set to {role.mention}")

    @config.command(name="applications-channel", description="Staff channel where whitelist applications arrive")
    async def applications_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._set(interaction, "app_channel", channel.id, f"Applications → {channel.mention}")

    @config.command(name="whitelist-role", description="Role given when an application is approved")
    async def whitelist_role(self, interaction: discord.Interaction, role: discord.Role):
        await self._set(interaction, "whitelist_role", role.id, f"Whitelist role set to {role.mention}")

    @config.command(name="suggestion-channel", description="Channel where /suggest posts go")
    async def suggestion_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._set(interaction, "suggestion_channel", channel.id, f"Suggestions → {channel.mention}")

    @config.command(name="view", description="Show all current settings")
    async def view(self, interaction: discord.Interaction):
        g = cfg(interaction.guild)
        e = discord.Embed(title="⚙️ Bot settings", color=COLOR)
        e.add_field(name="Staff role", value=mention_role(g["support_role"]))
        e.add_field(name="Ticket logs", value=mention_channel(g["log_channel"]))
        e.add_field(name="Mod logs", value=mention_channel(g["mod_log"]))
        e.add_field(name="Ticket category", value=mention_channel(g["category"]) if g["category"] else "Auto")
        e.add_field(name="Auto-close", value=f"{g['autoclose_hours']}h" if g["autoclose_hours"] else "Off")
        e.add_field(name="FiveM server", value=f"`{g['server_ip']}`" if g["server_ip"] else "Not set")
        e.add_field(name="Welcome channel", value=mention_channel(g["welcome_channel"]))
        e.add_field(name="Verify role", value=mention_role(g["verify_role"]))
        e.add_field(name="Applications", value=mention_channel(g["app_channel"]))
        e.add_field(name="Whitelist role", value=mention_role(g["whitelist_role"]))
        e.add_field(name="Suggestions", value=mention_channel(g["suggestion_channel"]))
        e.add_field(name="Status panel", value=mention_channel(g["status_channel"]))
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
