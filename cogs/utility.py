"""Utility: help, ping, userinfo, serverinfo, avatar, poll."""

import discord
from discord import app_commands
from discord.ext import commands

from core import COLOR, cfg, now

CATEGORY_EMOJI = {"Tickets": "🎫", "Server": "🟢", "Community": "👥", "Moderation": "🔨",
                  "Utility": "🧰", "Fun": "🎲", "Settings": "⚙️"}
NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show every command")
    async def help(self, interaction: discord.Interaction):
        e = discord.Embed(title="📖 Commands", color=COLOR,
                          description="Admins: start with `/config view` to see what still needs setting up.")
        total = 0
        for name, cog in self.bot.cogs.items():
            lines = []
            for cmd in cog.get_app_commands():
                subs = list(cmd.walk_commands()) if isinstance(cmd, app_commands.Group) else [cmd]
                for c in subs:
                    lines.append(f"`/{c.qualified_name}` — {c.description}")
            if lines:
                total += len(lines)
                value = "\n".join(lines)
                e.add_field(name=f"{CATEGORY_EMOJI.get(name, '•')} {name}",
                            value=value if len(value) <= 1024 else value[:1020] + "…", inline=False)
        e.set_footer(text=f"{total} commands")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="ping", description="Check if the bot is alive")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🏓 Pong! {round(self.bot.latency * 1000)}ms")

    @app_commands.command(name="userinfo", description="Info about a member")
    @app_commands.guild_only()
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        e = discord.Embed(title=str(member), color=member.color if member.color.value else COLOR)
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="Nickname", value=member.display_name)
        e.add_field(name="ID", value=f"`{member.id}`")
        e.add_field(name="Account created", value=discord.utils.format_dt(member.created_at, "R"))
        if member.joined_at:
            e.add_field(name="Joined server", value=discord.utils.format_dt(member.joined_at, "R"))
        warns = len(cfg(interaction.guild)["warnings"].get(str(member.id), []))
        e.add_field(name="Warnings", value=str(warns))
        roles = [r.mention for r in reversed(member.roles) if r != interaction.guild.default_role]
        e.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles[:15]) or "None", inline=False)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="serverinfo", description="Info about this Discord server")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        e = discord.Embed(title=g.name, color=COLOR, timestamp=now())
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        e.add_field(name="Owner", value=g.owner.mention if g.owner else "?")
        e.add_field(name="Members", value=str(g.member_count))
        e.add_field(name="Created", value=discord.utils.format_dt(g.created_at, "R"))
        e.add_field(name="Channels", value=f"{len(g.text_channels)} text · {len(g.voice_channels)} voice")
        e.add_field(name="Roles", value=str(len(g.roles)))
        e.add_field(name="Boosts", value=f"{g.premium_subscription_count} (level {g.premium_tier})")
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="avatar", description="Show someone's profile picture")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        e = discord.Embed(title=f"{member.display_name}'s avatar", color=COLOR)
        e.set_image(url=member.display_avatar.with_size(1024).url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="poll", description="Make a poll. Options separated by |  (e.g. Cars | Bikes | Boats)")
    @app_commands.guild_only()
    async def poll(self, interaction: discord.Interaction, question: str, options: str | None = None):
        choices = [o.strip() for o in (options or "").split("|") if o.strip()][:10]
        e = discord.Embed(title=f"📊 {question}", color=COLOR, timestamp=now())
        e.set_footer(text=f"Poll by {interaction.user.display_name}")
        if len(choices) >= 2:
            e.description = "\n".join(f"{NUMBERS[i]} {c}" for i, c in enumerate(choices))
            reactions = NUMBERS[:len(choices)]
        else:
            reactions = ["👍", "👎"]
        await interaction.response.send_message(embed=e)
        msg = await interaction.original_response()
        for r in reactions:
            await msg.add_reaction(r)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
