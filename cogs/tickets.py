"""Ticket system: panel with GTA ticket types, forms, claim/close, transcripts, ratings."""

import asyncio
import datetime
import io

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core import COLOR, GREEN, RED, cfg, is_staff, now, send_log, store

# question format: (question ≤45 chars, required?, "short" | "long") — max 5 per type
TICKET_TYPES = {
    "addon": {
        "label": "Addon Not Working", "emoji": "🛠️", "description": "Help installing or fixing an addon",
        "questions": [
            ("Which addon? (name / channel)", True, "short"),
            ("What's the problem?", True, "long"),
            ("What did you already try?", False, "long"),
            ("Screenshot / video link", False, "short"),
        ],
    },
    "download": {
        "label": "Download Problem", "emoji": "📥", "description": "Broken link or file won't download",
        "questions": [
            ("Which file / addon?", True, "short"),
            ("What happens when you download it?", True, "long"),
        ],
    },
    "buy": {
        "label": "Buy an Addon", "emoji": "💳", "description": "Paid addons, payments and orders",
        "questions": [
            ("Which addon do you want?", True, "short"),
            ("Payment method / order ID (if paid)", False, "short"),
            ("Anything else we should know?", False, "long"),
        ],
    },
    "request": {
        "label": "Request an Addon", "emoji": "💡", "description": "Ask for a new pack, sound or mod",
        "questions": [
            ("What do you want us to make or add?", True, "long"),
            ("Example link (video / picture)", False, "short"),
        ],
    },
    "partner": {
        "label": "Partnership", "emoji": "🤝", "description": "Partner your server with us",
        "questions": [
            ("Your server name + invite link", True, "short"),
            ("How many members?", True, "short"),
            ("What is your server about?", True, "long"),
        ],
    },
    "report": {
        "label": "Report a Member", "emoji": "🚨", "description": "Someone breaking the rules",
        "questions": [
            ("Who? (name or ID)", True, "short"),
            ("What happened?", True, "long"),
            ("Proof (screenshot / link)", False, "short"),
        ],
    },
    "support": {
        "label": "General Support", "emoji": "💬", "description": "Anything else",
        "questions": [("How can we help?", True, "long")],
    },
}

CLOSE_DELAY = 5
closing: set[int] = set()


def get_ticket(channel) -> dict | None:
    if channel is None or getattr(channel, "guild", None) is None:
        return None
    return cfg(channel.guild)["tickets"].get(str(channel.id))


def open_ticket_of(guild: discord.Guild, user_id: int):
    for cid, t in cfg(guild)["tickets"].items():
        if t["owner"] == user_id and guild.get_channel(int(cid)):
            return guild.get_channel(int(cid))
    return None


async def get_category(guild: discord.Guild) -> discord.CategoryChannel:
    g = cfg(guild)
    cat = guild.get_channel(g["category"]) if g["category"] else None
    if not isinstance(cat, discord.CategoryChannel):
        cat = discord.utils.get(guild.categories, name="Tickets") or await guild.create_category("Tickets")
        g["category"] = cat.id
        await store.save()
    return cat


async def build_transcript(channel: discord.TextChannel, t: dict) -> bytes:
    info = TICKET_TYPES.get(t["type"], {"label": t["type"]})
    lines = [f"Transcript — #{channel.name} ({channel.guild.name})",
             f"Type: {info['label']}   Opened: {t['created'][:16].replace('T', ' ')} UTC", "=" * 60]
    async for msg in channel.history(limit=None, oldest_first=True):
        text = msg.content or ""
        for e in msg.embeds:
            parts = [e.title or "", e.description or ""] + [f"{f.name}: {f.value}" for f in e.fields]
            text += " [embed] " + " | ".join(p for p in parts if p)
        for a in msg.attachments:
            text += f" [file: {a.url}]"
        lines.append(f"[{msg.created_at:%Y-%m-%d %H:%M}] {msg.author}: {text}")
    return "\n".join(lines).encode("utf-8")


# ─────────── opening ───────────

class TypeSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=v["label"], value=k, emoji=v["emoji"], description=v["description"][:100])
                   for k, v in list(TICKET_TYPES.items())[:25]]
        super().__init__(placeholder="🎫 Choose a ticket type…", options=options, custom_id="ticket:type")

    async def callback(self, interaction: discord.Interaction):
        g = cfg(interaction.guild)
        if interaction.user.id in g["blacklist"]:
            return await interaction.response.send_message("You are blocked from opening tickets.", ephemeral=True)
        existing = open_ticket_of(interaction.guild, interaction.user.id)
        if existing:
            return await interaction.response.send_message(f"You already have an open ticket: {existing.mention}",
                                                           ephemeral=True)
        await interaction.response.send_modal(TicketForm(self.values[0]))
        try:
            await interaction.message.edit(view=PanelView())  # reset the dropdown
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
                label=question[:45], required=required, max_length=1000,
                style=discord.TextStyle.paragraph if style == "long" else discord.TextStyle.short))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        existing = open_ticket_of(interaction.guild, interaction.user.id)
        if existing:
            return await interaction.followup.send(f"You already have an open ticket: {existing.mention}")
        answers = [(item.label, item.value or "—") for item in self.children]
        try:
            channel = await create_ticket(interaction.guild, interaction.user, self.type_key, answers)
        except discord.Forbidden:
            return await interaction.followup.send("I can't create channels. Ask an admin to check my permissions.")
        await interaction.followup.send(f"✅ Your ticket is ready: {channel.mention}")


async def create_ticket(guild: discord.Guild, user: discord.Member, type_key: str, answers) -> discord.TextChannel:
    g = cfg(guild)
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
        name=f"{type_key}-{number:04d}", category=await get_category(guild), overwrites=overwrites,
        topic=f"{info['label']} ticket #{number} for {user} ({user.id})")
    g["tickets"][str(channel.id)] = {"owner": user.id, "type": type_key, "number": number,
                                     "claimed_by": None, "created": now().isoformat()}
    g["stats"]["opened"] += 1
    await store.save()

    embed = discord.Embed(
        title=f"{info['emoji']} {info['label']} — Ticket #{number:04d}",
        description=f"Hi {user.mention}, thanks for reaching out! Staff will be with you soon.\n"
                    "Add any extra details or screenshots below.",
        color=COLOR, timestamp=now())
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

    log = discord.Embed(title="🟢 Ticket opened", color=GREEN, timestamp=now())
    log.add_field(name="Ticket", value=channel.mention)
    log.add_field(name="Type", value=info["label"])
    log.add_field(name="By", value=user.mention)
    await send_log(guild, log)
    return channel


# ─────────── inside a ticket ───────────

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
    g = cfg(interaction.guild)
    t["claimed_by"] = interaction.user.id
    handled = g["stats"]["handled"]
    handled[str(interaction.user.id)] = handled.get(str(interaction.user.id), 0) + 1
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
        super().__init__(timeout=86400)
        self.guild_id = guild_id
        self.ticket_name = ticket_name
        for n in range(1, 6):
            button = discord.ui.Button(label=str(n), emoji="⭐", style=discord.ButtonStyle.secondary)
            button.callback = self._make_callback(n)
            self.add_item(button)

    def _make_callback(self, stars: int):
        async def callback(interaction: discord.Interaction):
            await interaction.response.edit_message(content=f"Thanks for your feedback! {'⭐' * stars}", view=None)
            guild = interaction.client.get_guild(self.guild_id)
            if guild:
                cfg(guild)["stats"]["ratings"].append(stars)
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
    g = cfg(guild)
    info = TICKET_TYPES.get(t["type"], {"label": t["type"]})
    try:
        await channel.send(embed=discord.Embed(
            description=f"🔒 Closed by {closed_by.mention}" + (f"\n**Reason:** {reason}" if reason else "")
                        + f"\nThis channel will be deleted in {CLOSE_DELAY} seconds.", color=RED))
        transcript = await build_transcript(channel, t)
        filename = f"{channel.name}-transcript.txt"

        log = discord.Embed(title="🔴 Ticket closed", color=RED, timestamp=now())
        log.add_field(name="Ticket", value=f"#{channel.name}")
        log.add_field(name="Type", value=info["label"])
        log.add_field(name="Opened by", value=f"<@{t['owner']}>")
        log.add_field(name="Claimed by", value=f"<@{t['claimed_by']}>" if t["claimed_by"] else "Nobody")
        log.add_field(name="Closed by", value=closed_by.mention)
        log.add_field(name="Reason", value=reason or "—", inline=False)
        await send_log(guild, log, discord.File(io.BytesIO(transcript), filename=filename))

        owner = guild.get_member(t["owner"])
        if owner:
            dm = discord.Embed(title=f"Your ticket in {guild.name} was closed",
                               description=f"**Ticket:** #{channel.name}\n**Reason:** {reason or '—'}\n\n"
                                           "A copy of the conversation is attached. How was your support?",
                               color=COLOR)
            try:
                await owner.send(embed=dm, file=discord.File(io.BytesIO(transcript), filename=filename),
                                 view=RatingView(guild.id, f"#{channel.name}"))
            except discord.HTTPException:
                pass

        g["tickets"].pop(str(channel.id), None)
        g["stats"]["closed"] += 1
        await store.save()
        await asyncio.sleep(CLOSE_DELAY)
        await channel.delete(reason=f"Ticket closed by {closed_by}")
    finally:
        closing.discard(channel.id)


# ─────────── commands ───────────

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(PanelView())
        self.bot.add_view(TicketView())
        self.autoclose_loop.start()

    async def cog_unload(self):
        self.autoclose_loop.cancel()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        g = cfg(channel.guild)
        if g["tickets"].pop(str(channel.id), None):
            await store.save()

    @tasks.loop(minutes=15)
    async def autoclose_loop(self):
        for guild in self.bot.guilds:
            g = cfg(guild)
            hours = g["autoclose_hours"]
            if not hours:
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
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _require(self, interaction: discord.Interaction, staff_only=False) -> dict | None:
        t = get_ticket(interaction.channel)
        if t is None:
            await interaction.response.send_message("Use this inside a ticket.", ephemeral=True)
            return None
        allowed = is_staff(interaction.user) or (not staff_only and interaction.user.id == t["owner"])
        if not allowed:
            await interaction.response.send_message("You can't do that here.", ephemeral=True)
            return None
        return t

    @app_commands.command(name="ticket-panel", description="Post the ticket panel in this channel")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def ticket_panel(self, interaction: discord.Interaction,
                           title: str = "📩 Support Tickets",
                           description: str = "Need help with an addon? Pick a category below and a private ticket "
                                              "will be opened with staff."):
        embed = discord.Embed(title=title, description=description, color=COLOR)
        embed.add_field(name="Categories", inline=False, value="\n".join(
            f"{v['emoji']} **{v['label']}** — {v['description']}" for v in TICKET_TYPES.values()))
        embed.set_footer(text="Opening troll tickets = punishment.")
        await interaction.channel.send(embed=embed, view=PanelView())
        await interaction.response.send_message("Ticket panel posted ✅", ephemeral=True)

    @app_commands.command(name="close", description="Close this ticket")
    @app_commands.guild_only()
    async def close(self, interaction: discord.Interaction, reason: str | None = None):
        if await self._require(interaction):
            await interaction.response.send_message("Closing…", ephemeral=True)
            await close_ticket(interaction.channel, interaction.user, reason)

    @app_commands.command(name="claim", description="Claim this ticket (staff)")
    @app_commands.guild_only()
    async def claim(self, interaction: discord.Interaction):
        await claim_ticket(interaction)

    @app_commands.command(name="add", description="Add a member to this ticket")
    @app_commands.guild_only()
    async def add(self, interaction: discord.Interaction, member: discord.Member):
        if await self._require(interaction):
            await interaction.channel.set_permissions(member, view_channel=True, send_messages=True,
                                                      attach_files=True, read_message_history=True)
            await interaction.response.send_message(f"➕ Added {member.mention} to the ticket.")

    @app_commands.command(name="remove", description="Remove a member from this ticket (staff)")
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, member: discord.Member):
        t = await self._require(interaction, staff_only=True)
        if t:
            if member.id == t["owner"]:
                return await interaction.response.send_message("You can't remove the ticket owner.", ephemeral=True)
            await interaction.channel.set_permissions(member, overwrite=None)
            await interaction.response.send_message(f"➖ Removed {member.mention} from the ticket.")

    @app_commands.command(name="rename", description="Rename this ticket (staff)")
    @app_commands.guild_only()
    async def rename(self, interaction: discord.Interaction, name: str):
        if await self._require(interaction, staff_only=True):
            await interaction.channel.edit(name=name[:90])
            await interaction.response.send_message(f"✏️ Renamed to **{interaction.channel.name}**")

    @app_commands.command(name="blacklist", description="Block or unblock a member from opening tickets")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def blacklist(self, interaction: discord.Interaction, member: discord.Member):
        bl = cfg(interaction.guild)["blacklist"]
        if member.id in bl:
            bl.remove(member.id)
            text = f"{member.mention} can open tickets again."
        else:
            bl.append(member.id)
            text = f"{member.mention} is now blocked from opening tickets."
        await store.save()
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="ticket-stats", description="Ticket numbers, average rating and top staff")
    @app_commands.guild_only()
    async def ticket_stats(self, interaction: discord.Interaction):
        g = cfg(interaction.guild)
        s = g["stats"]
        ratings = s["ratings"]
        e = discord.Embed(title="📊 Ticket stats", color=COLOR)
        e.add_field(name="Opened", value=str(s["opened"]))
        e.add_field(name="Closed", value=str(s["closed"]))
        e.add_field(name="Open now", value=str(len(g["tickets"])))
        e.add_field(name="Average rating", inline=False,
                    value=f"{sum(ratings) / len(ratings):.1f} ⭐ ({len(ratings)} ratings)" if ratings else "No ratings yet")
        top = sorted(s["handled"].items(), key=lambda kv: kv[1], reverse=True)[:5]
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        e.add_field(name="Top staff (claimed tickets)", inline=False,
                    value="\n".join(f"{medals[i]} <@{uid}> — {n}" for i, (uid, n) in enumerate(top)) or "Nobody yet")
        await interaction.response.send_message(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
