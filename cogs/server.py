"""FiveM server: live status, player list, connect info, restart & announcements."""

import re

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from core import COLOR, GREEN, RED, cfg, now, store

COLOR_CODES = re.compile(r"\^[0-9]")


async def fetch_server(address: str) -> dict:
    """Ask the FiveM server for its info. Returns {'online': False} if unreachable."""
    base = f"http://{address}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as session:
            async with session.get(f"{base}/dynamic.json") as r:
                dynamic = await r.json(content_type=None)
            players = None
            try:
                async with session.get(f"{base}/players.json") as r:
                    players = await r.json(content_type=None)
            except Exception:
                pass
    except Exception:
        return {"online": False}
    players = players if isinstance(players, list) else None
    return {
        "online": True,
        "hostname": COLOR_CODES.sub("", str(dynamic.get("hostname", "GTA Server"))).strip(),
        "clients": int(dynamic.get("clients", len(players or [])) or 0),
        "max": int(dynamic.get("sv_maxclients", 0) or 0),
        "players": players,
    }


def status_embed(guild: discord.Guild, info: dict) -> discord.Embed:
    g = cfg(guild)
    if info["online"]:
        e = discord.Embed(title=f"🟢 {info['hostname'][:200] or 'السيرفر شغّال'}", color=GREEN, timestamp=now())
        e.add_field(name="الحالة", value="شغّال 🟢")
        e.add_field(name="اللاعبين", value=f"{info['clients']}/{info['max'] or '?'}")
    else:
        e = discord.Embed(title="🔴 السيرفر طافي", description="السيرفر طافي أو يسوي ريستارت. انتظر شوي!",
                          color=RED, timestamp=now())
    if g["connect_link"]:
        e.add_field(name="دخول", value=g["connect_link"], inline=False)
    e.add_field(name="F8 console", value=f"`connect {g['server_ip']}`", inline=False)
    e.set_footer(text="آخر تحديث")
    return e


class Server(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.status_loop.start()

    async def cog_unload(self):
        self.status_loop.cancel()

    async def _server_or_warn(self, interaction: discord.Interaction) -> str | None:
        address = cfg(interaction.guild)["server_ip"]
        if not address:
            await interaction.response.send_message(
                "ما فيه سيرفر محدد. الأدمن يقدر يسوي `/config server 1.2.3.4:30120`.", ephemeral=True)
        return address

    # ── live status panel + bot activity ──
    @tasks.loop(minutes=1)
    async def status_loop(self):
        presence_done = False
        for guild in self.bot.guilds:
            g = cfg(guild)
            if not g["server_ip"]:
                continue
            info = await fetch_server(g["server_ip"])
            if not presence_done:
                text = f"{info['clients']}/{info['max'] or '?'} players" if info["online"] else "Server offline"
                await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=text))
                presence_done = True
            channel = guild.get_channel(g["status_channel"]) if g["status_channel"] else None
            if channel and g["status_message"]:
                try:
                    await channel.get_partial_message(g["status_message"]).edit(embed=status_embed(guild, info))
                except discord.NotFound:
                    g["status_channel"] = g["status_message"] = None
                    await store.save()
                except discord.HTTPException:
                    pass

    @status_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    # ── commands ──
    @app_commands.command(name="status", description="Is the GTA server online? How many players?")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 10)
    async def status(self, interaction: discord.Interaction):
        address = await self._server_or_warn(interaction)
        if address:
            await interaction.response.defer()
            await interaction.followup.send(embed=status_embed(interaction.guild, await fetch_server(address)))

    @app_commands.command(name="players", description="List players in the city right now")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 10)
    async def players(self, interaction: discord.Interaction):
        address = await self._server_or_warn(interaction)
        if not address:
            return
        await interaction.response.defer()
        info = await fetch_server(address)
        if not info["online"]:
            return await interaction.followup.send("🔴 السيرفر طافي الحين.")
        e = discord.Embed(title=f"👥 اللاعبين الحين — {info['clients']}/{info['max'] or '?'}", color=COLOR,
                          timestamp=now())
        if info["players"] is None:
            e.description = "السيرفر مخفي قائمة اللاعبين."
        elif not info["players"]:
            e.description = "السيرفر فاضي الحين. كن أول واحد يدخل!"
        else:
            rows = [f"`{p.get('id', '?'):>3}` {p.get('name', 'Unknown')[:30]} — {p.get('ping', '?')}ms"
                    for p in sorted(info["players"], key=lambda p: p.get("id", 0))]
            e.description = "\n".join(rows[:50]) + (f"\n…و {len(rows) - 50} غيرهم" if len(rows) > 50 else "")
        await interaction.followup.send(embed=e)

    @app_commands.command(name="connect", description="How to join the GTA server")
    @app_commands.guild_only()
    async def connect(self, interaction: discord.Interaction):
        g = cfg(interaction.guild)
        if not g["server_ip"] and not g["connect_link"]:
            return await interaction.response.send_message("عنوان السيرفر ما انحدد بعد.", ephemeral=True)
        e = discord.Embed(title="🎮 طريقة الدخول", color=COLOR)
        steps = ["افتح **FiveM**"]
        if g["connect_link"]:
            steps.append(f"اضغط: {g['connect_link']}")
        if g["server_ip"]:
            steps.append(f"أو اضغط **F8** واكتب `connect {g['server_ip']}`")
        e.description = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="status-panel", description="Post a status message that updates every minute")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def status_panel(self, interaction: discord.Interaction):
        address = await self._server_or_warn(interaction)
        if not address:
            return
        await interaction.response.defer(ephemeral=True)
        msg = await interaction.channel.send(embed=status_embed(interaction.guild, await fetch_server(address)))
        g = cfg(interaction.guild)
        g["status_channel"], g["status_message"] = interaction.channel.id, msg.id
        await store.save()
        await interaction.followup.send("✅ Live status panel posted. It updates every minute.")

    @app_commands.command(name="restart", description="Announce a server restart")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    @app_commands.describe(minutes="Minutes until restart (0 = now)", ping="Ping @everyone?")
    async def restart(self, interaction: discord.Interaction, minutes: app_commands.Range[int, 0, 180],
                      reason: str = "ريستارت مجدول", ping: bool = False):
        when = "**الحين**" if minutes == 0 else f"بعد **{minutes} دقيقة**"
        ts = int(now().timestamp()) + minutes * 60
        e = discord.Embed(title="🔄 ريستارت السيرفر", color=discord.Color.orange(),
                          description=f"السيرفر بيسوي ريستارت {when} (<t:{ts}:t>).\n**السبب:** {reason}\n\n"
                                      "وقّف سيارتك وروح مكان آمن! 🚗")
        e.set_footer(text=f"الإعلان من {interaction.user.display_name}")
        await interaction.response.send_message(
            content="@everyone" if ping else None, embed=e,
            allowed_mentions=discord.AllowedMentions(everyone=ping))

    @app_commands.command(name="announce", description="Post an announcement embed")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def announce(self, interaction: discord.Interaction, title: str, message: str,
                       channel: discord.TextChannel | None = None, ping: bool = False):
        target = channel or interaction.channel
        e = discord.Embed(title=f"📢 {title}", description=message.replace("\\n", "\n"), color=COLOR, timestamp=now())
        e.set_footer(text=f"— {interaction.user.display_name}")
        await target.send(content="@everyone" if ping else None, embed=e,
                          allowed_mentions=discord.AllowedMentions(everyone=ping))
        await interaction.response.send_message(f"✅ تم النشر في {target.mention}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Server(bot))
