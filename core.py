"""Shared storage and helpers used by every module."""

import asyncio
import copy
import datetime
import json
import os
import re

import discord

try:  # optional: load DISCORD_TOKEN from a .env file
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATA_FILE = os.getenv("DATA_FILE", "data.json")

COLOR = discord.Color(0xF5A623)   # GTA orange
GREEN = discord.Color.green()
RED = discord.Color.red()

GUILD_DEFAULTS = {
    # tickets
    "support_role": None, "log_channel": None, "category": None, "autoclose_hours": 0,
    "counter": 0, "blacklist": [], "tickets": {},
    "stats": {"opened": 0, "closed": 0, "ratings": [], "handled": {}},
    # moderation
    "mod_log": None, "warnings": {},
    # GTA server
    "server_ip": None, "connect_link": None, "status_channel": None, "status_message": None,
    # community
    "welcome_channel": None, "verify_role": None, "app_channel": None, "whitelist_role": None,
    "suggestion_channel": None, "pending_apps": [],
    # fun
    "giveaways": {},
}


class Store:
    def __init__(self, path: str):
        self.path = path
        self.lock = asyncio.Lock()
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {"guilds": {}}

    def guild(self, guild_id: int) -> dict:
        g = self.data["guilds"].setdefault(str(guild_id), {})
        for key, value in GUILD_DEFAULTS.items():
            g.setdefault(key, copy.deepcopy(value))
        for key, value in GUILD_DEFAULTS["stats"].items():
            g["stats"].setdefault(key, copy.deepcopy(value))
        return g

    async def save(self):
        async with self.lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)


store = Store(DATA_FILE)


def cfg(guild: discord.Guild) -> dict:
    return store.guild(guild.id)


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def is_staff(member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    perms = member.guild_permissions
    if perms.manage_channels or perms.moderate_members or perms.administrator:
        return True
    role_id = cfg(member.guild)["support_role"]
    return role_id is not None and any(r.id == role_id for r in member.roles)


async def send_log(guild: discord.Guild, embed: discord.Embed, file: discord.File | None = None, mod=False):
    """mod=True sends to the moderation log (falls back to the normal log channel)."""
    g = cfg(guild)
    channel_id = (g["mod_log"] or g["log_channel"]) if mod else g["log_channel"]
    channel = guild.get_channel(channel_id) if channel_id else None
    if isinstance(channel, discord.TextChannel):
        try:
            if file:
                await channel.send(embed=embed, file=file)
            else:
                await channel.send(embed=embed)
        except discord.HTTPException:
            pass


_DURATION = re.compile(r"(\d+)\s*([smhdw])", re.I)
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(text: str) -> datetime.timedelta | None:
    """'10m', '2h30m', '1d' → timedelta"""
    parts = _DURATION.findall(text or "")
    seconds = sum(int(n) * _UNITS[u.lower()] for n, u in parts)
    return datetime.timedelta(seconds=seconds) if seconds > 0 else None


def fmt_duration(td: datetime.timedelta) -> str:
    secs, out = int(td.total_seconds()), []
    for name, size in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if secs >= size:
            out.append(f"{secs // size}{name}")
            secs %= size
    return " ".join(out) or "0s"


def mention_role(role_id) -> str:
    return f"<@&{role_id}>" if role_id else "Not set"


def mention_channel(channel_id) -> str:
    return f"<#{channel_id}>" if channel_id else "Not set"
