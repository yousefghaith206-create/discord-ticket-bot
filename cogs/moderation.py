"""Moderation: warn, warnings, clearwarns, kick, ban, unban, timeout, untimeout, purge, slowmode, lock, unlock."""

import datetime

import discord
from discord import app_commands
from discord.ext import commands

from core import COLOR, GREEN, RED, cfg, fmt_duration, now, parse_duration, send_log, store


def hierarchy_problem(interaction: discord.Interaction, target: discord.Member) -> str | None:
    guild, mod = interaction.guild, interaction.user
    if target == mod:
        return "ما تقدر تسويها على نفسك."
    if target == guild.owner:
        return "ما تقدر تسويها على صاحب السيرفر."
    if target == guild.me:
        return "Nice try 😄"
    if mod != guild.owner and target.top_role >= mod.top_role:
        return "رتبة العضو أعلى منك أو نفسك."
    if target.top_role >= guild.me.top_role:
        return "رتبتي تحت، ارفع رتبة البوت فوق."
    return None


async def mod_log(guild, action: str, target, moderator, reason: str | None, color=RED, extra: str | None = None):
    e = discord.Embed(title=f"🔨 {action}", color=color, timestamp=now())
    e.add_field(name="Member", value=f"{target.mention if hasattr(target, 'mention') else target} (`{target.id}`)")
    e.add_field(name="Moderator", value=moderator.mention)
    if extra:
        e.add_field(name="Details", value=extra)
    e.add_field(name="Reason", value=reason or "No reason given", inline=False)
    await send_log(guild, e, mod=True)


async def try_dm(user, guild, action: str, reason: str | None, extra: str = ""):
    e = discord.Embed(title=f"تم {action} في {guild.name}",
                      description=f"**السبب:** {reason or 'بدون سبب'}{extra}\n\n"
                                  "تشوف إنه ظلم؟ افتح تذكرة.", color=RED)
    try:
        await user.send(embed=e)
    except discord.HTTPException:
        pass


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── warnings ──
    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        problem = hierarchy_problem(interaction, member)
        if problem:
            return await interaction.response.send_message(problem, ephemeral=True)
        warns = cfg(interaction.guild)["warnings"].setdefault(str(member.id), [])
        warns.append({"reason": reason, "mod": interaction.user.id, "time": now().isoformat()})
        await store.save()
        await try_dm(member, interaction.guild, "تحذيرك", reason, f"\nصار عندك **{len(warns)}** تحذير.")
        await mod_log(interaction.guild, "Warn", member, interaction.user, reason, discord.Color.orange(),
                      f"Total warnings: {len(warns)}")
        tip = "\n💡 عنده ٣ تحذيرات أو أكثر — يمكن وقته `/timeout`." if len(warns) >= 3 else ""
        await interaction.response.send_message(
            f"⚠️ تم تحذير {member.mention}. صار عنده **{len(warns)}** تحذير.{tip}")

    @app_commands.command(name="warnings", description="See a member's warnings")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        warns = cfg(interaction.guild)["warnings"].get(str(member.id), [])
        e = discord.Embed(title=f"⚠️ Warnings for {member.display_name}", color=COLOR)
        if not warns:
            e.description = "Clean record ✅"
        for i, w in enumerate(warns[-15:], max(1, len(warns) - 14)):
            when = discord.utils.format_dt(datetime.datetime.fromisoformat(w["time"]), "d")
            e.add_field(name=f"#{i} — {when}", value=f"{w['reason'][:200]}\nby <@{w['mod']}>", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="clearwarns", description="Remove all warnings from a member")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def clearwarns(self, interaction: discord.Interaction, member: discord.Member):
        removed = cfg(interaction.guild)["warnings"].pop(str(member.id), [])
        await store.save()
        await mod_log(interaction.guild, "Warnings cleared", member, interaction.user, None, GREEN,
                      f"Removed {len(removed)}")
        await interaction.response.send_message(f"🧹 Cleared {len(removed)} warning(s) from {member.mention}.",
                                                ephemeral=True)

    # ── kick / ban ──
    @app_commands.command(name="kick", description="Kick a member from the Discord")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None):
        problem = hierarchy_problem(interaction, member)
        if problem:
            return await interaction.response.send_message(problem, ephemeral=True)
        await try_dm(member, interaction.guild, "طردك", reason)
        await member.kick(reason=f"{interaction.user}: {reason or 'No reason'}")
        await mod_log(interaction.guild, "Kick", member, interaction.user, reason)
        await interaction.response.send_message(f"👢 تم طرد {member}.")

    @app_commands.command(name="ban", description="Ban a member from the Discord")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.guild_only()
    @app_commands.describe(delete_days="Delete their messages from the last X days (0-7)")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None,
                  delete_days: app_commands.Range[int, 0, 7] = 0):
        problem = hierarchy_problem(interaction, member)
        if problem:
            return await interaction.response.send_message(problem, ephemeral=True)
        await try_dm(member, interaction.guild, "حظرك", reason)
        await member.ban(reason=f"{interaction.user}: {reason or 'No reason'}",
                         delete_message_seconds=delete_days * 86400)
        await mod_log(interaction.guild, "Ban", member, interaction.user, reason)
        await interaction.response.send_message(f"🔨 تم حظر {member}.")

    @app_commands.command(name="unban", description="Unban a user by their ID")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.guild_only()
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str | None = None):
        if not user_id.strip().isdigit():
            return await interaction.response.send_message("That's not a valid user ID.", ephemeral=True)
        user = discord.Object(id=int(user_id))
        try:
            await interaction.guild.unban(user, reason=f"{interaction.user}: {reason or 'No reason'}")
        except discord.NotFound:
            return await interaction.response.send_message("That user isn't banned.", ephemeral=True)
        await mod_log(interaction.guild, "Unban", user, interaction.user, reason, GREEN)
        await interaction.response.send_message(f"✅ <@{user_id}> was unbanned.")

    # ── timeout ──
    @app_commands.command(name="timeout", description="Mute a member for a while (e.g. 10m, 2h, 1d)")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str,
                      reason: str | None = None):
        problem = hierarchy_problem(interaction, member)
        if problem:
            return await interaction.response.send_message(problem, ephemeral=True)
        td = parse_duration(duration)
        if td is None:
            return await interaction.response.send_message("اكتب المدة مثل `10m` أو `2h` أو `1d`.", ephemeral=True)
        td = min(td, datetime.timedelta(days=28))
        await member.timeout(td, reason=f"{interaction.user}: {reason or 'No reason'}")
        await try_dm(member, interaction.guild, "إسكاتك", reason, f"\n**المدة:** {fmt_duration(td)}")
        await mod_log(interaction.guild, "Timeout", member, interaction.user, reason, discord.Color.orange(),
                      f"Duration: {fmt_duration(td)}")
        await interaction.response.send_message(f"🔇 تم إسكات {member.mention} لمدة **{fmt_duration(td)}**.")

    @app_commands.command(name="untimeout", description="Remove a member's timeout")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member):
        await member.timeout(None, reason=f"Removed by {interaction.user}")
        await mod_log(interaction.guild, "Timeout removed", member, interaction.user, None, GREEN)
        await interaction.response.send_message(f"🔊 {member.mention} يقدر يتكلم مرة ثانية.")

    # ── channel tools ──
    @app_commands.command(name="purge", description="Delete recent messages in this channel")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.guild_only()
    @app_commands.describe(amount="How many messages to check (1-100)", member="Only delete this member's messages")
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100],
                    member: discord.Member | None = None):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(
            limit=amount, check=(lambda m: m.author == member) if member else (lambda m: True))
        await interaction.followup.send(f"🧹 تم حذف {len(deleted)} رسالة.")

    @app_commands.command(name="slowmode", description="Set slowmode for this channel (0 = off)")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.response.send_message("🐢 Slowmode off." if seconds == 0
                                                else f"🐢 Slowmode set to {seconds}s.")

    async def _set_lock(self, interaction: discord.Interaction, locked: bool, reason: str | None):
        role = interaction.guild.default_role
        overwrite = interaction.channel.overwrites_for(role)
        overwrite.send_messages = False if locked else None
        await interaction.channel.set_permissions(role, overwrite=overwrite,
                                                  reason=f"{interaction.user}: {reason or ''}")
        e = discord.Embed(description=("🔒 تم قفل الروم." if locked else "🔓 تم فتح الروم.")
                          + (f"\n**السبب:** {reason}" if reason else ""), color=RED if locked else GREEN)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="lock", description="Stop everyone from talking in this channel")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def lock(self, interaction: discord.Interaction, reason: str | None = None):
        await self._set_lock(interaction, True, reason)

    @app_commands.command(name="unlock", description="Let everyone talk in this channel again")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def unlock(self, interaction: discord.Interaction):
        await self._set_lock(interaction, False, None)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
