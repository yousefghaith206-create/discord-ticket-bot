"""Welcome messages, rules verification, whitelist applications, suggestions."""

import re

import discord
from discord import app_commands
from discord.ext import commands

from core import COLOR, GREEN, RED, cfg, is_staff, now, store

DEFAULT_RULES = (
    "1. Respect everyone — no racism, harassment or hate.\n"
    "2. No spam, self-promo or advertising without a partnership.\n"
    "3. Don't re-upload or sell our addons as your own.\n"
    "4. Use the right channels — help goes in a ticket.\n"
    "5. No NSFW, scams or harmful files.\n"
    "6. Staff decisions are final."
)


# ─────────── verify ───────────

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="I accept the rules", emoji="✅", style=discord.ButtonStyle.success,
                       custom_id="verify:accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        role_id = cfg(interaction.guild)["verify_role"]
        role = interaction.guild.get_role(role_id) if role_id else None
        if role is None:
            return await interaction.response.send_message(
                "Verification isn't set up yet. Ask an admin to run `/config verify-role`.", ephemeral=True)
        if role in interaction.user.roles:
            return await interaction.response.send_message("You're already verified ✅", ephemeral=True)
        try:
            await interaction.user.add_roles(role, reason="Accepted the rules")
        except discord.Forbidden:
            return await interaction.response.send_message(
                "I can't give that role — my role must be above it.", ephemeral=True)
        await interaction.response.send_message(f"Welcome to the city! You got {role.mention} 🎉", ephemeral=True)


# ─────────── whitelist applications ───────────

class ApplyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Apply for whitelist", emoji="📝", style=discord.ButtonStyle.primary,
                       custom_id="apply:start")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = cfg(interaction.guild)
        if not g["app_channel"]:
            return await interaction.response.send_message(
                "Applications aren't open yet. Ask an admin to run `/config applications-channel`.", ephemeral=True)
        role = interaction.guild.get_role(g["whitelist_role"]) if g["whitelist_role"] else None
        if role and role in interaction.user.roles:
            return await interaction.response.send_message("You're already whitelisted ✅", ephemeral=True)
        if interaction.user.id in g["pending_apps"]:
            return await interaction.response.send_message(
                "You already have an application waiting. Staff will review it soon!", ephemeral=True)
        await interaction.response.send_modal(ApplicationForm())


class ApplicationForm(discord.ui.Modal, title="Whitelist application"):
    character = discord.ui.TextInput(label="Character name", max_length=60, placeholder="e.g. Tony Romano")
    age = discord.ui.TextInput(label="Your real age", max_length=3)
    experience = discord.ui.TextInput(label="Roleplay experience", style=discord.TextStyle.paragraph,
                                      max_length=500, placeholder="Servers you played on, how long…")
    backstory = discord.ui.TextInput(label="Character backstory", style=discord.TextStyle.paragraph,
                                     max_length=1000, min_length=50)
    why = discord.ui.TextInput(label="Why do you want to join?", style=discord.TextStyle.paragraph, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        g = cfg(interaction.guild)
        channel = interaction.guild.get_channel(g["app_channel"])
        if channel is None:
            return await interaction.response.send_message("The applications channel is missing.", ephemeral=True)
        user = interaction.user
        e = discord.Embed(title="📝 New whitelist application", color=COLOR, timestamp=now())
        e.set_author(name=str(user), icon_url=user.display_avatar.url)
        e.add_field(name="Discord", value=user.mention)
        e.add_field(name="Character", value=self.character.value)
        e.add_field(name="Age", value=self.age.value)
        e.add_field(name="Account created", value=discord.utils.format_dt(user.created_at, "R"))
        e.add_field(name="RP experience", value=self.experience.value, inline=False)
        e.add_field(name="Backstory", value=self.backstory.value[:1024], inline=False)
        e.add_field(name="Why join", value=self.why.value, inline=False)
        e.set_footer(text=f"Applicant ID: {user.id}")
        await channel.send(embed=e, view=ReviewView())
        g["pending_apps"].append(user.id)
        await store.save()
        await interaction.response.send_message(
            "✅ Application sent! You'll get a DM when staff review it.", ephemeral=True)


def applicant_id(message: discord.Message) -> int | None:
    if not message.embeds or not message.embeds[0].footer.text:
        return None
    match = re.search(r"(\d{15,21})", message.embeds[0].footer.text)
    return int(match.group(1)) if match else None


async def finish_application(interaction: discord.Interaction, message: discord.Message,
                             approved: bool, reason: str | None = None):
    guild = interaction.guild
    g = cfg(guild)
    uid = applicant_id(message)
    member = guild.get_member(uid) if uid else None

    embed = message.embeds[0]
    embed.color = GREEN if approved else RED
    embed.title = "✅ Application approved" if approved else "❌ Application denied"
    embed.add_field(name="Reviewed by", value=interaction.user.mention + (f"\n**Reason:** {reason}" if reason else ""),
                    inline=False)

    note = ""
    if approved and member:
        role = guild.get_role(g["whitelist_role"]) if g["whitelist_role"] else None
        if role is None:
            note = "\n⚠️ No whitelist role set — use `/config whitelist-role`."
        else:
            try:
                await member.add_roles(role, reason=f"Whitelist approved by {interaction.user}")
            except discord.Forbidden:
                note = "\n⚠️ I couldn't give the role — move my role above it."
    if not member:
        note += "\n⚠️ The applicant has left the server."

    if uid in g["pending_apps"]:
        g["pending_apps"].remove(uid)
        await store.save()

    await message.edit(embed=embed, view=None)
    await interaction.response.send_message(("Approved ✅" if approved else "Denied ❌") + note, ephemeral=True)

    if member:
        dm = discord.Embed(
            title=f"Your whitelist application for {guild.name}",
            description=("🎉 **Approved!** Welcome to the city — see you in game." if approved
                         else f"❌ **Denied.**\n**Reason:** {reason or '—'}\nYou can apply again later."),
            color=GREEN if approved else RED)
        try:
            await member.send(embed=dm)
        except discord.HTTPException:
            pass


class ReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Approve", emoji="✅", style=discord.ButtonStyle.success, custom_id="app:approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("Only staff can review applications.", ephemeral=True)
        await finish_application(interaction, interaction.message, approved=True)

    @discord.ui.button(label="Deny", emoji="❌", style=discord.ButtonStyle.danger, custom_id="app:deny")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("Only staff can review applications.", ephemeral=True)
        await interaction.response.send_modal(DenyForm(interaction.message))


class DenyForm(discord.ui.Modal, title="Deny application"):
    reason = discord.ui.TextInput(label="Reason (sent to the applicant)", style=discord.TextStyle.paragraph,
                                  max_length=500)

    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        await finish_application(interaction, self.message, approved=False, reason=self.reason.value)


# ─────────── cog ───────────

class Community(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(VerifyView())
        self.bot.add_view(ApplyView())
        self.bot.add_view(ReviewView())

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel_id = cfg(member.guild)["welcome_channel"]
        channel = member.guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            return
        e = discord.Embed(
            title=f"Welcome to {member.guild.name}! 👋",
            description=f"Hey {member.mention}, welcome!\n"
                        "Read the rules, check out the addons, and open a ticket if you need help.",
            color=COLOR)
        e.set_thumbnail(url=member.display_avatar.url)
        e.set_footer(text=f"You are member #{member.guild.member_count}")
        try:
            await channel.send(content=member.mention, embed=e)
        except discord.HTTPException:
            pass

    @app_commands.command(name="verify-panel", description="Post the rules with an 'I accept' button")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.describe(rules="Your rules (use \\n for new lines). Leave empty for default GTA RP rules.")
    async def verify_panel(self, interaction: discord.Interaction, rules: str | None = None):
        e = discord.Embed(title="📜 Server rules", color=COLOR,
                          description=(rules.replace("\\n", "\n") if rules else DEFAULT_RULES)
                          + "\n\nPress the button below to accept and unlock the server.")
        await interaction.channel.send(embed=e, view=VerifyView())
        await interaction.response.send_message("✅ Verify panel posted.", ephemeral=True)

    @app_commands.command(name="apply-panel", description="Post the whitelist application panel")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def apply_panel(self, interaction: discord.Interaction):
        e = discord.Embed(title="📝 Whitelist applications",
                          description="Want to join the city? Press the button and fill in the form.\n"
                                      "Take your time on the backstory — low-effort applications get denied.\n"
                                      "You'll get a DM with the result.",
                          color=COLOR)
        await interaction.channel.send(embed=e, view=ApplyView())
        await interaction.response.send_message("✅ Application panel posted.", ephemeral=True)

    @app_commands.command(name="suggest", description="Suggest something for the server")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 60)
    async def suggest(self, interaction: discord.Interaction, idea: app_commands.Range[str, 10, 1000]):
        channel_id = cfg(interaction.guild)["suggestion_channel"]
        channel = interaction.guild.get_channel(channel_id) if channel_id else interaction.channel
        e = discord.Embed(title="💡 New suggestion", description=idea, color=COLOR, timestamp=now())
        e.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        e.set_footer(text="Vote below!")
        msg = await channel.send(embed=e)
        for emoji in ("✅", "❌"):
            await msg.add_reaction(emoji)
        await interaction.response.send_message(f"✅ Suggestion posted in {channel.mention}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Community(bot))
