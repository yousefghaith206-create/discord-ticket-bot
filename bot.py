"""
GTA Server Bot — tickets, live server status, whitelist applications,
moderation, giveaways and more.  Run:  python bot.py
"""

import os

import discord
from discord import app_commands
from discord.ext import commands

import core  # noqa: F401  (loads .env and the data file)

EXTENSIONS = [
    "cogs.settings",
    "cogs.tickets",
    "cogs.server",
    "cogs.community",
    "cogs.moderation",
    "cogs.utility",
    "cogs.fun",
]


class GTABot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True  # welcome messages, roles, member lookups
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        for ext in EXTENSIONS:
            await self.load_extension(ext)
        synced = await self.tree.sync()
        print(f"Synced {len(synced)} slash commands")

    async def on_ready(self):
        print(f"✅ Logged in as {self.user} — in {len(self.guilds)} server(s)")


bot = GTABot()


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        message = "You don't have permission to use this."
    elif isinstance(error, app_commands.BotMissingPermissions):
        message = f"I'm missing permissions: {', '.join(error.missing_permissions)}"
    elif isinstance(error, app_commands.CommandOnCooldown):
        message = f"Slow down! Try again in {error.retry_after:.0f}s."
    else:
        original = getattr(error, "original", error)
        if isinstance(original, discord.Forbidden):
            message = "I don't have permission to do that. Check that my role is high enough."
        else:
            message = f"Something went wrong: {original}"
            print(f"Error in /{interaction.command.qualified_name if interaction.command else '?'}: {original!r}")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is missing. Add it as a Codespaces secret, env variable or .env file.")
    bot.run(token)
