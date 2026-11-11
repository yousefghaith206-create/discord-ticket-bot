"""Utility: help, ping, userinfo, serverinfo, avatar, poll."""

import discord
from discord import app_commands
from discord.ext import commands

from core import COLOR, cfg, now

CATEGORIES = {  # cog name → Arabic title, in display order
    "Tickets": "🎫 التذاكر", "Community": "👥 المجتمع", "Fun": "🎲 ترفيه", "Utility": "🧰 أدوات",
    "Server": "🟢 السيرفر", "Moderation": "🔨 الإدارة", "Settings": "⚙️ الإعدادات",
}
AR, EN = "🇸🇦", "🇬🇧"
# command → (Arabic description, language of its replies)
HELP = {
    "ticket-panel": ("ينشر لوحة التذاكر في الروم", AR),
    "close": ("يقفل التذكرة (تقدر تكتب سبب)", AR),
    "claim": ("الستاف يستلم التذكرة", AR),
    "add": ("يضيف عضو للتذكرة", AR),
    "remove": ("يشيل عضو من التذكرة", AR),
    "rename": ("يغيّر اسم روم التذكرة", AR),
    "blacklist": ("يمنع/يسمح لعضو يفتح تذاكر", AR),
    "ticket-stats": ("إحصائيات التذاكر وأفضل الستاف", AR),
    "verify-panel": ("ينشر القوانين مع زر الموافقة", AR),
    "apply-panel": ("ينشر لوحة طلبات الوايت لست (للرول بلاي)", EN),
    "suggest": ("ترسل اقتراح للسيرفر مع تصويت", AR),
    "car": ("يعطيك سيارة GTA عشوائية", AR),
    "wanted": ("يشوف مستوى المطلوبية ⭐", AR),
    "giveaway start": ("يبدأ قيف أواي (مثال: 1h)", AR),
    "giveaway end": ("ينهي القيف أواي الحين", AR),
    "giveaway reroll": ("يختار فائز جديد", AR),
    "help": ("يعرض كل الأوامر", AR),
    "ping": ("يشوف إذا البوت شغّال وسرعته", AR),
    "userinfo": ("معلومات عن عضو", AR),
    "serverinfo": ("معلومات عن السيرفر", AR),
    "avatar": ("يعرض صورة عضو", AR),
    "poll": ("يسوي تصويت (الخيارات بينها |)", AR),
    "status": ("حالة سيرفر FiveM وعدد اللاعبين", AR),
    "players": ("قائمة اللاعبين في السيرفر", AR),
    "connect": ("طريقة الدخول للسيرفر", AR),
    "status-panel": ("رسالة حالة تتحدّث كل دقيقة", AR),
    "restart": ("يعلن عن ريستارت للسيرفر", AR),
    "announce": ("ينشر إعلان", AR),
    "warn": ("يحذّر عضو", AR),
    "warnings": ("يعرض تحذيرات عضو", EN),
    "clearwarns": ("يمسح كل تحذيرات عضو", EN),
    "kick": ("يطرد عضو", AR),
    "ban": ("يحظر عضو", AR),
    "unban": ("يفك الحظر بالآيدي", EN),
    "timeout": ("يسكت عضو لمدة (مثال: 10m)", AR),
    "untimeout": ("يفك الإسكات", AR),
    "purge": ("يحذف رسائل من الروم", AR),
    "slowmode": ("يحط سلو مود للروم", EN),
    "lock": ("يقفل الروم", AR),
    "unlock": ("يفتح الروم", AR),
    "config support-role": ("رتبة الستاف", EN),
    "config log-channel": ("روم لوق التذاكر", EN),
    "config mod-log": ("روم لوق العقوبات", EN),
    "config category": ("الكاتيقوري اللي تنفتح فيه التذاكر", EN),
    "config autoclose": ("قفل التذاكر الميتة تلقائياً", EN),
    "config server": ("عنوان سيرفر FiveM", EN),
    "config welcome-channel": ("روم الترحيب", EN),
    "config verify-role": ("رتبة التوثيق", EN),
    "config applications-channel": ("روم طلبات الوايت لست", EN),
    "config whitelist-role": ("رتبة الوايت لست", EN),
    "config suggestion-channel": ("روم الاقتراحات", EN),
    "config view": ("يعرض كل الإعدادات", EN),
}
NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="يعرض كل الأوامر")
    async def help(self, interaction: discord.Interaction):
        e = discord.Embed(title="📖 الأوامر", color=COLOR,
                          description=f"{AR} = الرد بالعربي   ·   {EN} = الرد بالإنجليزي\n"
                                      "للأدمن: ابدأ بـ `/config view` عشان تشوف وش باقي يحتاج إعداد.")
        total = 0
        order = list(CATEGORIES) + [n for n in self.bot.cogs if n not in CATEGORIES]
        for name in order:
            cog = self.bot.cogs.get(name)
            if cog is None:
                continue
            lines = []
            for cmd in cog.get_app_commands():
                subs = list(cmd.walk_commands()) if isinstance(cmd, app_commands.Group) else [cmd]
                for c in subs:
                    desc, lang = HELP.get(c.qualified_name, (c.description, EN))
                    lines.append(f"{lang} `/{c.qualified_name}` — {desc}")
            if lines:
                total += len(lines)
                value = "\n".join(lines)
                e.add_field(name=CATEGORIES.get(name, name),
                            value=value if len(value) <= 1024 else value[:1020] + "…", inline=False)
        e.set_footer(text=f"{total} أمر")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="ping", description="Check if the bot is alive")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🏓 بونق! {round(self.bot.latency * 1000)}ms")

    @app_commands.command(name="userinfo", description="Info about a member")
    @app_commands.guild_only()
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        e = discord.Embed(title=str(member), color=member.color if member.color.value else COLOR)
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="الاسم", value=member.display_name)
        e.add_field(name="الآيدي", value=f"`{member.id}`")
        e.add_field(name="إنشاء الحساب", value=discord.utils.format_dt(member.created_at, "R"))
        if member.joined_at:
            e.add_field(name="دخل السيرفر", value=discord.utils.format_dt(member.joined_at, "R"))
        warns = len(cfg(interaction.guild)["warnings"].get(str(member.id), []))
        e.add_field(name="التحذيرات", value=str(warns))
        roles = [r.mention for r in reversed(member.roles) if r != interaction.guild.default_role]
        e.add_field(name=f"الرتب ({len(roles)})", value=" ".join(roles[:15]) or "ما فيه", inline=False)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="serverinfo", description="Info about this Discord server")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        e = discord.Embed(title=g.name, color=COLOR, timestamp=now())
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        e.add_field(name="المالك", value=g.owner.mention if g.owner else "?")
        e.add_field(name="الأعضاء", value=str(g.member_count))
        e.add_field(name="تاريخ الإنشاء", value=discord.utils.format_dt(g.created_at, "R"))
        e.add_field(name="الرومات", value=f"{len(g.text_channels)} كتابي · {len(g.voice_channels)} صوتي")
        e.add_field(name="الرتب", value=str(len(g.roles)))
        e.add_field(name="البوستات", value=f"{g.premium_subscription_count} (لفل {g.premium_tier})")
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="avatar", description="Show someone's profile picture")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        e = discord.Embed(title=f"صورة {member.display_name}", color=COLOR)
        e.set_image(url=member.display_avatar.with_size(1024).url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="poll", description="Make a poll. Options separated by |  (e.g. Cars | Bikes | Boats)")
    @app_commands.guild_only()
    async def poll(self, interaction: discord.Interaction, question: str, options: str | None = None):
        choices = [o.strip() for o in (options or "").split("|") if o.strip()][:10]
        e = discord.Embed(title=f"📊 {question}", color=COLOR, timestamp=now())
        e.set_footer(text=f"تصويت من {interaction.user.display_name}")
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
