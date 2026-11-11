"""
Discord Ticket Bot — full version (discord.py 2.x)

Members:
  • Pick a ticket type from a dropdown, answer a short form, get a private channel
  • One open ticket at a time, rate the support (1–5 ⭐) by DM after closing
  • Get a copy of the conversation (transcript) by DM

Staff:
  • Claim / Close / Close-with-reason buttons in every ticket
  • /add /remove /rename /claim /close /blacklist /stats
  • Logs channel: opened / claimed / closed (+ transcript) / ratings
  • Optional auto-close for inactive tickets

Setup (all from Discord, no file editing except the token):
  /config support-role, /config log-channel, /config category, /config autoclose, /config view
  /setup  → posts the ticket panel

Everything is saved in data.json, so restarts don't lose tickets, settings or buttons.
"""

import asyncio
import copy
import datetime
import io
import json
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

try:  # optional: load DISCORD_TOKEN from a .env file
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = os.getenv("DATA_FILE", "data.json")

# ─────────────────────────────────────────────────────────────
# Ticket types — edit freely (max 25 types, max 5 questions each)
# question format: (question text ≤45 chars, required?, "short" | "long")
# ─────────────────────────────────────────────────────────────
TICKET_TYPES = {
    "support": {
        "label": "General Support", "emoji": "🛠️",
        "description": "Questions or help with anything",
        "questions": [("What do you need help with?", True, "long")],
    },
    "report": {
        "label": "Report a Member", "emoji": "🚨",
        "description": "Report rule-breaking or abuse",
        "questions": [
            ("Who are you reporting? (name / ID)", True, "short"),
            ("What happened?", True, "long"),
            ("Proof (links to screenshots)", False, "long"),
        ],
    },
    "billing": {
        "label": "Purchases & Billing", "emoji": "💳",
        "description": "Payments, ranks, store issues",
        "questions": [
            ("Order / transaction ID", False, "short"),
            ("Describe the problem", True, "long"),
        ],
    },
    "appeal": {
        "label": "Ban / Mute Appeal", "emoji": "⚖️",
        "description": "Appeal a punishment",
        "questions": [
            ("What punishment did you get?", True, "short"),
            ("Why should it be removed?", True, "long"),
        ],
    },
    "other": {
        "label": "Other", "emoji": "💬",
        "description": "Anything else",
        "questions": [("How can we help?", True, "long")],
    },
}

COLOR = discord.Color.blurple()
CLOSE_DELAY = 5  # seconds before a closed ticket is deleted


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ─────────────────────────── storage ───────────────────────────

GUILD_DEFAULTS = {
    "support_role": None,
    "log_channel": None,
    "category": None,
    "autoclose_hours": 0,
    "counter": 0,
    "blacklist": [],
    "tickets": {},          # channel_id -> ticket info
    "stats": {"opened": 0, "closed": 0, "ratings": []},
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
        return g

    async def save(self):
        async with self.lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)


store = Store(DATA_FILE)
closing: set[int] = set()  # channels currently being closed


def get_ticket(channel) -> dict | None:
    if channel is None or channel.guild is None:
        return None
    return store.guild(channel.guild.id)["tickets"].get(str(channel.id))


def is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.manage_channels:
        return True
    role_id = store.guild(member.guild.id)["support_role"]
    return role_id is not None and any(r.id == role_id for r in member.roles)


async def send_log(guild: discord.Guild, embed: discord.Embed, file: discord.File | None = None):
    channel_id = store.guild(guild.id)["log_channel"]
    channel = guild.get_channel(channel_id) if channel_id else None
    if isinstance(channel, discord.TextChannel):
        try:
            await channel.send(embed=embed, file=file) if file else await channel.send(embed=embed)
        except discord.HTTPException:
            pass


async def get_category(guild: discord.Guild) -> discord.CategoryChannel:
    g = store.guild(guild.id)
    cat = guild.get_channel(g["category"]) if g["category"] else None
    if not isinstance(cat, discord.CategoryChannel):
        cat = discord.utils.get(guild.categories, name="Tickets") or await guild.create_category("Tickets")
        g["category"] = cat.id
        await store.save()
    return cat


def open_ticket_of(guild: discord.Guild, user_id: int) -> discord.TextChannel | None:
    for cid, t in store.guild(guild.id)["tickets"].items():
        if t["owner"] == user_id:
            ch = guild.get_channel(int(cid))
            if ch:
                return ch
    return None


async def build_transcript(channel: discord.TextChannel, t: dict) -> bytes:
    info = TICKET_TYPES.get(t["type"], {"label": t["type"]})
    lines = [
        f"Transcript — #{channel.name} ({channel.guild.name})",
        f"Type: {info['label']}   Opened: {t['created'][:16].replace('T', ' ')} UTC",
        "=" * 60,
    ]
    async for msg in channel.history(limit=None, oldest_first=True):
        text = msg.content or ""
        for e in msg.embeds:
            parts = [e.title or "", e.description or ""] + [f"{f.name}: {f.value}" for f in e.fields]
            text += " [embed] " + " | ".join(p for p in parts if p)
        for a in msg.attachments:
            text += f" [file: {a.url}]"
        lines.append(f"[{msg.created_at:%Y-%m-%d %H:%M}] {msg.author}: {text}")
    return "\n".join(lines).encode("utf-8")


# ─────────────────────────── opening tickets ───────────────────────────

class TypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=v["label"], value=k, emoji=v["emoji"], description=v["description"][:100])
            for k, v in list(TICKET_TYPES.items())[:25]
        ]
        super().__init__(placeholder="🎫 Choose a ticket type…", options=options, custom_id="ticket:type")

    async def callback(self, interaction: discord.Interaction):
        g = store.guild(interaction.guild.id)
        if interaction.user.id in g["blacklist"]:
            return await interaction.response.send_message("You are blocked from opening tickets.", ephemeral=True)
        existing = open_ticket_of(interaction.guild, interaction.user.id)
        if existing:
            return await interaction.response.send_message(
                f"You already have an open ticket: {existing.mention}", ephemeral=True)

        await interaction.response.send_modal(TicketForm(self.values[0]))
        try:  # reset the dropdown so the next person sees a clean menu
            await interaction.message.edit(view=PanelView())
        except discord.HTTPException:
            pass


class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TypeSelect())


class TicketForm(discord.ui.Modal):
    def __init__(self, type_key: str):
        info = TICKET_TYPES[type_key]
        super().__init__(title=f"{info['label']} ticket"[:45])
        self.type_key = type_key
        for question, required, style in info["questions"][:5]:
            self.add_item(discord.ui.TextInput(
                label=question[:45],
                required=required,
                style=discord.TextStyle.paragraph if style == "long" else discord.TextStyle.short,
                max_length=1000,
            ))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        existing = open_ticket_of(interaction.guild, interaction.user.id)
        if existing:
            return await interaction.followup.send(f"You already have an open ticket: {existing.mention}")
        answers = [(item.label, item.value or "—") for item in self.children]
        try:
            channel = await create_ticket(interaction.guild, interaction.user, self.type_key, answers)
        except discord.Forbidden:
            return await interaction.followup.send(
                "I don't have permission to create channels. Ask an admin to check my role.")
        await interaction.followup.send(f"✅ Your ticket is ready: {channel.mention}")


async def create_ticket(guild: discord.Guild, user: discord.Member, type_key: str, answers) -> discord.TextChannel:
    g = store.guild(guild.id)
    info = TICKET_TYPES[type_key]
    g["counter"] += 1
    number = g["counter"]

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True,
                                          embed_links=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True,
                                              manage_messages=True, read_message_history=True,
                                              embed_links=True, attach_files=True),
    }
    support_role = guild.get_role(g["support_role"]) if g["support_role"] else None
    if support_role:
        overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                               attach_files=True, read_message_history=True)

    channel = await guild.create_text_channel(
        name=f"{type_key}-{number:04d}",
        category=await get_category(guild),
        overwrites=overwrites,
        topic=f"{info['label']} ticket #{number} for {user} ({user.id})",
    )
    g["tickets"][str(channel.id)] = {
        "owner": user.id, "type": type_key, "number": number,
        "claimed_by": None, "created": now().isoformat(),
    }
    g["stats"]["opened"] += 1
    await store.save()

    embed = discord.Embed(
        title=f"{info['emoji']} {info['label']} — Ticket #{number:04d}",
        description=f"Hi {user.mention}, thanks for reaching out! A staff member will be with you soon.\n"
                    "Add any extra details or screenshots below.",
        color=COLOR, timestamp=now(),
    )
    for question, answer in answers:
        embed.add_field(name=question, value=answer[:1024], inline=False)
    embed.set_footer(text=f"User ID: {user.id}")

    ping = user.mention + (f" {support_role.mention}" if support_role else "")
    msg = await channel.send(content=ping, embed=embed, view=TicketView(),
                             allowed_mentions=discord.AllowedMentions(users=True, roles=True))
    try:
        await msg.pin()
    except discord.HTTPException:
        pass

    log = discord.Embed(title="🟢 Ticket opened", color=discord.Color.green(), timestamp=now())
    log.add_field(name="Ticket", value=channel.mention)
    log.add_field(name="Type", value=info["label"])
    log.add_field(name="By", value=user.mention)
    await send_log(guild, log)
    return channel


# ─────────────────────────── inside a ticket ───────────────────────────

class TicketView(discord.ui.View):
    def __init__(self, claimed_by: str | None = None):
        super().__init__(timeout=None)
        if claimed_by:
            self.claim.disabled = True
            self.claim.label = f"Claimed by {claimed_by}"[:80]

    @discord.ui.button(label="Claim", emoji="🙋", style=discord.ButtonStyle.success, custom_id="ticket:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await claim_ticket(interaction):
            await interaction.message.edit(view=TicketView(interaction.user.display_name))

    @discord.ui.button(label="Close", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await can_close(interaction):
            await interaction.response.send_message("Close this ticket?", view=ConfirmClose(), ephemeral=True)

    @discord.ui.button(label="Close with reason", emoji="📝", style=discord.ButtonStyle.secondary,
                       custom_id="ticket:close_reason")
    async def close_reason(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await can_close(interaction):
            await interaction.response.send_modal(CloseReasonForm())


async def can_close(interaction: discord.Interaction) -> bool:
    t = get_ticket(interaction.channel)
    if t is None:
        await interaction.response.send_message("This isn't an open ticket.", ephemeral=True)
        return False
    if interaction.user.id != t["owner"] and not is_staff(interaction.user):
        await interaction.response.send_message("You can't close this ticket.", ephemeral=True)
        return False
    return True


async def claim_ticket(interaction: discord.Interaction) -> bool:
    t = get_ticket(interaction.channel)
    if t is None:
        await interaction.response.send_message("This isn't an open ticket.", ephemeral=True)
        return False
    if not is_staff(interaction.user):
        await interaction.response.send_message("Only staff can claim tickets.", ephemeral=True)
        return False
    if t["claimed_by"]:
        await interaction.response.send_message(f"Already claimed by <@{t['claimed_by']}>.", ephemeral=True)
        return False
    t["claimed_by"] = interaction.user.id
    await store.save()
    await interaction.response.send_message(f"🙋 {interaction.user.mention} is now handling this ticket.")
    log = discord.Embed(title="🟡 Ticket claimed", color=discord.Color.gold(), timestamp=now())
    log.add_field(name="Ticket", value=interaction.channel.mention)
    log.add_field(name="By", value=interaction.user.mention)
    await send_log(interaction.guild, log)
    return True


class ConfirmClose(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Yes, close it", style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Closing…", view=None)
        await close_ticket(interaction.channel, interaction.user)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None)


class CloseReasonForm(discord.ui.Modal, title="Close ticket"):
    reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("Closing…", ephemeral=True)
        await close_ticket(interaction.channel, interaction.user, self.reason.value)


class RatingView(discord.ui.View):
    def __init__(self, guild_id: int, ticket_name: str):
        super().__init__(timeout=86400)  # 24h to rate
        self.guild_id = guild_id
        self.ticket_name = ticket_name
        for n in range(1, 6):
            button = discord.ui.Button(label=str(n), emoji="⭐", style=discord.ButtonStyle.secondary)
            button.callback = self._make_callback(n)
            self.add_item(button)

    def _make_callback(self, stars: int):
        async def callback(interaction: discord.Interaction):
            await interaction.response.edit_message(content=f"Thanks for your feedback! {'⭐' * stars}", view=None)
            guild = bot.get_guild(self.guild_id)
            if guild:
                store.guild(guild.id)["stats"]["ratings"].append(stars)
                await store.save()
                log = discord.Embed(title="⭐ Ticket rated", color=discord.Color.gold(), timestamp=now())
                log.add_field(name="Ticket", value=self.ticket_name)
                log.add_field(name="By", value=interaction.user.mention)
                log.add_field(name="Rating", value="⭐" * stars)
                await send_log(guild, log)
        return callback


async def close_ticket(channel: discord.TextChannel, closed_by: discord.abc.User, reason: str | None = None):
    t = get_ticket(channel)
    if t is None or channel.id in closing:
        return
    closing.add(channel.id)
    guild = channel.guild
    g = store.guild(guild.id)
    info = TICKET_TYPES.get(t["type"], {"label": t["type"]})

    try:
        await channel.send(embed=discord.Embed(
            description=f"🔒 Closed by {closed_by.mention}" + (f"\n**Reason:** {reason}" if reason else "")
                        + f"\nThis channel will be deleted in {CLOSE_DELAY} seconds.",
            color=discord.Color.red()))
        transcript = await build_transcript(channel, t)
        filename = f"{channel.name}-transcript.txt"

        log = discord.Embed(title="🔴 Ticket closed", color=discord.Color.red(), timestamp=now())
        log.add_field(name="Ticket", value=f"#{channel.name}")
        log.add_field(name="Type", value=info["label"])
        log.add_field(name="Opened by", value=f"<@{t['owner']}>")
        log.add_field(name="Claimed by", value=f"<@{t['claimed_by']}>" if t["claimed_by"] else "Nobody")
        log.add_field(name="Closed by", value=closed_by.mention)
        log.add_field(name="Reason", value=reason or "—", inline=False)
        await send_log(guild, log, discord.File(io.BytesIO(transcript), filename=filename))

        owner = guild.get_member(t["owner"])
        if owner:
            dm = discord.Embed(
                title=f"Your ticket in {guild.name} was closed",
                description=(f"**Ticket:** #{channel.name}\n**Reason:** {reason or '—'}\n\n"
                             "A copy of the conversation is attached. How was your support?"),
                color=COLOR)
            try:
                await owner.send(embed=dm, file=discord.File(io.BytesIO(transcript), filename=filename),
                                 view=RatingView(guild.id, f"#{channel.name}"))
            except discord.HTTPException:
                pass  # DMs closed

        g["tickets"].pop(str(channel.id), None)
        g["stats"]["closed"] += 1
        await store.save()

        await asyncio.sleep(CLOSE_DELAY)
        await channel.delete(reason=f"Ticket closed by {closed_by}")
    finally:
        closing.discard(channel.id)


# ─────────────────────────── bot ───────────────────────────

class TicketBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(PanelView())
        self.add_view(TicketView())
        self.tree.add_command(config_group)
        await self.tree.sync()
        autoclose_loop.start()

    async def on_ready(self):
        print(f"✅ Logged in as {self.user} — in {len(self.guilds)} server(s)")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="tickets 🎫"))

    async def on_guild_channel_delete(self, channel):
        # someone deleted a ticket channel by hand → forget it
        g = store.guild(channel.guild.id)
        if g["tickets"].pop(str(channel.id), None):
            await store.save()


bot = TicketBot()


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    message = ("You don't have permission to use this." if isinstance(error, app_commands.MissingPermissions)
               else f"Something went wrong: {getattr(error, 'original', error)}")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass
    if not isinstance(error, app_commands.MissingPermissions):
        raise error


@tasks.loop(minutes=15)
async def autoclose_loop():
    for gid, g in list(store.data["guilds"].items()):
        hours = g.get("autoclose_hours", 0)
        guild = bot.get_guild(int(gid))
        if not hours or guild is None:
            continue
        for cid, t in list(g["tickets"].items()):
            channel = guild.get_channel(int(cid))
            if channel is None:
                continue
            last = (discord.utils.snowflake_time(channel.last_message_id) if channel.last_message_id
                    else datetime.datetime.fromisoformat(t["created"]))
            if now() - last > datetime.timedelta(hours=hours):
                await close_ticket(channel, guild.me, f"No activity for {hours} hours")


@autoclose_loop.before_loop
async def _wait_ready():
    await bot.wait_until_ready()


# ─────────────────────────── admin commands ───────────────────────────

config_group = app_commands.Group(name="config", description="Ticket bot settings",
                                  default_permissions=discord.Permissions(manage_guild=True), guild_only=True)


@config_group.command(name="support-role", description="Role that can see and handle all tickets")
async def cfg_role(interaction: discord.Interaction, role: discord.Role):
    store.guild(interaction.guild.id)["support_role"] = role.id
    await store.save()
    await interaction.response.send_message(f"Support role set to {role.mention}", ephemeral=True)


@config_group.command(name="log-channel", description="Channel for ticket logs and transcripts")
async def cfg_log(interaction: discord.Interaction, channel: discord.TextChannel):
    store.guild(interaction.guild.id)["log_channel"] = channel.id
    await store.save()
    await interaction.response.send_message(f"Logs will go to {channel.mention}", ephemeral=True)


@config_group.command(name="category", description="Category where new tickets are created")
async def cfg_category(interaction: discord.Interaction, category: discord.CategoryChannel):
    store.guild(interaction.guild.id)["category"] = category.id
    await store.save()
    await interaction.response.send_message(f"Tickets will be created in **{category.name}**", ephemeral=True)


@config_group.command(name="autoclose", description="Auto-close tickets after X hours without messages (0 = off)")
async def cfg_autoclose(interaction: discord.Interaction, hours: app_commands.Range[int, 0, 720]):
    store.guild(interaction.guild.id)["autoclose_hours"] = hours
    await store.save()
    await interaction.response.send_message(
        f"Auto-close {'turned off' if hours == 0 else f'after {hours}h of inactivity'}.", ephemeral=True)


@config_group.command(name="view", description="Show current settings")
async def cfg_view(interaction: discord.Interaction):
    g = store.guild(interaction.guild.id)
    e = discord.Embed(title="Ticket bot settings", color=COLOR)
    e.add_field(name="Support role", value=f"<@&{g['support_role']}>" if g["support_role"] else "Not set ⚠️")
    e.add_field(name="Log channel", value=f"<#{g['log_channel']}>" if g["log_channel"] else "Not set")
    e.add_field(name="Category", value=f"<#{g['category']}>" if g["category"] else "Auto (\"Tickets\")")
    e.add_field(name="Auto-close", value=f"{g['autoclose_hours']}h" if g["autoclose_hours"] else "Off")
    e.add_field(name="Open tickets", value=str(len(g["tickets"])))
    e.add_field(name="Blacklisted", value=str(len(g["blacklist"])))
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="setup", description="Post the ticket panel in this channel")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def setup(interaction: discord.Interaction,
                title: str = "📩 Support Tickets",
                description: str = "Need help? Choose a category below and a private ticket will be opened for you."):
    embed = discord.Embed(title=title, description=description, color=COLOR)
    embed.add_field(name="Categories",
                    value="\n".join(f"{v['emoji']} **{v['label']}** — {v['description']}" for v in TICKET_TYPES.values()),
                    inline=False)
    embed.set_footer(text="Please don't open tickets for no reason.")
    await interaction.channel.send(embed=embed, view=PanelView())
    await interaction.response.send_message("Panel posted ✅", ephemeral=True)


@bot.tree.command(name="blacklist", description="Block or unblock a member from opening tickets")
@app_commands.default_permissions(manage_guild=True)
@app_commands.guild_only()
async def blacklist(interaction: discord.Interaction, member: discord.Member):
    bl = store.guild(interaction.guild.id)["blacklist"]
    if member.id in bl:
        bl.remove(member.id)
        text = f"{member.mention} can open tickets again."
    else:
        bl.append(member.id)
        text = f"{member.mention} is now blocked from opening tickets."
    await store.save()
    await interaction.response.send_message(text, ephemeral=True)


@bot.tree.command(name="stats", description="Ticket statistics")
@app_commands.guild_only()
async def stats(interaction: discord.Interaction):
    g = store.guild(interaction.guild.id)
    ratings = g["stats"]["ratings"]
    avg = f"{sum(ratings) / len(ratings):.1f} ⭐ ({len(ratings)} ratings)" if ratings else "No ratings yet"
    e = discord.Embed(title="📊 Ticket stats", color=COLOR)
    e.add_field(name="Opened", value=str(g["stats"]["opened"]))
    e.add_field(name="Closed", value=str(g["stats"]["closed"]))
    e.add_field(name="Open now", value=str(len(g["tickets"])))
    e.add_field(name="Average rating", value=avg, inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True)


# ─────────────────────────── ticket commands ───────────────────────────

async def require_ticket(interaction: discord.Interaction, staff_only=False) -> dict | None:
    t = get_ticket(interaction.channel)
    if t is None:
        await interaction.response.send_message("Use this inside a ticket.", ephemeral=True)
        return None
    if staff_only and not is_staff(interaction.user):
        await interaction.response.send_message("Only staff can do that.", ephemeral=True)
        return None
    if not staff_only and interaction.user.id != t["owner"] and not is_staff(interaction.user):
        await interaction.response.send_message("You can't do that here.", ephemeral=True)
        return None
    return t


@bot.tree.command(name="close", description="Close this ticket")
@app_commands.guild_only()
async def close_cmd(interaction: discord.Interaction, reason: str | None = None):
    if await require_ticket(interaction):
        await interaction.response.send_message("Closing…", ephemeral=True)
        await close_ticket(interaction.channel, interaction.user, reason)


@bot.tree.command(name="claim", description="Claim this ticket")
@app_commands.guild_only()
async def claim_cmd(interaction: discord.Interaction):
    await claim_ticket(interaction)


@bot.tree.command(name="add", description="Add a member to this ticket")
@app_commands.guild_only()
async def add(interaction: discord.Interaction, member: discord.Member):
    if await require_ticket(interaction):
        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True,
                                                  attach_files=True, read_message_history=True)
        await interaction.response.send_message(f"➕ Added {member.mention} to the ticket.")


@bot.tree.command(name="remove", description="Remove a member from this ticket")
@app_commands.guild_only()
async def remove(interaction: discord.Interaction, member: discord.Member):
    t = await require_ticket(interaction, staff_only=True)
    if t:
        if member.id == t["owner"]:
            return await interaction.response.send_message("You can't remove the ticket owner.", ephemeral=True)
        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"➖ Removed {member.mention} from the ticket.")


@bot.tree.command(name="rename", description="Rename this ticket channel")
@app_commands.guild_only()
async def rename(interaction: discord.Interaction, name: str):
    if await require_ticket(interaction, staff_only=True):
        await interaction.channel.edit(name=name[:90])
        await interaction.response.send_message(f"✏️ Renamed to **{interaction.channel.name}**")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is missing. Set it in your host's environment variables or a .env file.")
    bot.run(TOKEN)
