"""Fun: /car, /wanted, and giveaways (/giveaway start | end | reroll)."""

import datetime
import random

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core import COLOR, GREEN, cfg, fmt_duration, now, parse_duration, store

CARS = [
    ("Truffade Adder", "Super"), ("Pegassi Zentorno", "Super"), ("Progen T20", "Super"),
    ("Pegassi Osiris", "Super"), ("Grotti Turismo R", "Super"), ("Pfister Comet", "Sports"),
    ("Obey 9F", "Sports"), ("Bravado Banshee", "Sports"), ("Dinka Jester", "Sports"),
    ("Karin Sultan", "Sports"), ("Annis Elegy RH8", "Sports"), ("Karin Kuruma", "Sports"),
    ("Vapid Dominator", "Muscle"), ("Bravado Gauntlet", "Muscle"), ("Declasse Sabre Turbo", "Muscle"),
    ("Imponte Dukes", "Muscle"), ("Albany Emperor", "Sedan"), ("Benefactor Schafter", "Sedan"),
    ("Vapid Sandking", "Off-Road"), ("Canis Mesa", "Off-Road"), ("Pegassi Bati 801", "Motorcycle"),
    ("Shitzu Hakuchou", "Motorcycle"), ("Western Daemon", "Motorcycle"), ("Brute Stockade", "Armored"),
    ("Vapid Police Cruiser", "Emergency"),
]
PAINTS = ["أسود ميتاليك", "أحمر مطفي", "كروم", "أبيض لؤلؤي", "أخضر ليموني", "أزرق ليلي",
          "وردي فاقع", "ذهبي", "زيتي مطفي", "بنفسجي لامع"]
CAR_LINES = ["مثالية للهروب من الشرطة 🚓", "الميكانيكي يقول إنها قانونية… تقريباً.",
             "لقيتها واقفة في Legion Square والمفتاح فيها.", "ريحتها من داخل Burger Shot.",
             "صاحبها الأول؟ مجهول. لا تسأل.", "طالعة توها من Los Santos Customs."]
CRIMES = ["سرق Zentorno من المعرض", "سرق بقالة 24/7 على طريق 68",
          "دعم مهرج في شاطئ Vespucci", "سرعة جنونية في نفق Del Perro",
          "قطع الشارع قدام مركز الشرطة", "حاول يسرق البنك بعصا",
          "وقّف دبابة في Legion Square", "سوّى مضاربة في Vanilla Unicorn",
          "سرق طيارة من المطار", "ما دفع حساب Burger Shot"]

def giveaway_embed(gw: dict, ended=False, winners: list[int] | None = None) -> discord.Embed:
    ends = datetime.datetime.fromisoformat(gw["ends"])
    e = discord.Embed(title=f"🎉 قيف أواي: {gw['prize']}", color=GREEN if ended else COLOR)
    if ended:
        e.description = ("**الفائز:** " + ", ".join(f"<@{w}>" for w in winners)) if winners else "ما أحد شارك 😢"
    else:
        e.description = f"اضغط **🎉 دخول** عشان تشارك!\nينتهي {discord.utils.format_dt(ends, 'R')}"
    e.add_field(name="عدد الفائزين", value=str(gw["winners"]))
    e.add_field(name="المشاركين", value=str(len(gw["entries"])))
    e.add_field(name="المقدّم", value=f"<@{gw['host']}>")
    e.set_footer(text="انتهى" if ended else "ينتهي")
    e.timestamp = ends
    return e


class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="دخول", emoji="🎉", style=discord.ButtonStyle.success, custom_id="giveaway:join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        gw = cfg(interaction.guild)["giveaways"].get(str(interaction.message.id))
        if gw is None or gw["ended"]:
            return await interaction.response.send_message("القيف أواي انتهى.", ephemeral=True)
        uid = interaction.user.id
        if uid in gw["entries"]:
            gw["entries"].remove(uid)
            text = "طلعت من القيف أواي."
        else:
            gw["entries"].append(uid)
            text = "🎉 دخلت! بالتوفيق."
        await store.save()
        await interaction.response.edit_message(embed=giveaway_embed(gw))
        await interaction.followup.send(text, ephemeral=True)


class Fun(commands.Cog):
    giveaway = app_commands.Group(name="giveaway", description="Run giveaways",
                                  default_permissions=discord.Permissions(manage_guild=True), guild_only=True)

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(GiveawayView())
        self.giveaway_loop.start()

    async def cog_unload(self):
        self.giveaway_loop.cancel()

    # ── fun commands ──
    @app_commands.command(name="car", description="سيارة GTA عشوائية لك 🚗")
    async def car(self, interaction: discord.Interaction):
        name, cls = random.choice(CARS)
        e = discord.Embed(title=f"🚗 سيارتك: {name}", description=random.choice(CAR_LINES), color=COLOR)
        e.add_field(name="الفئة", value=cls)
        e.add_field(name="اللون", value=random.choice(PAINTS))
        e.add_field(name="السرعة القصوى", value=f"{random.randint(180, 350)} كم/س")
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="wanted", description="شوف مستوى المطلوبية لأحد ⭐")
    async def wanted(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        stars = random.randint(0, 5)
        e = discord.Embed(title=f"🚨 مستوى المطلوبية: {member.display_name}",
                          description=("⭐" * stars + "☆" * (5 - stars)) + "\n" +
                                      ("سجله نظيف… مشبوه 🤨" if stars == 0 else
                                       f"**الجريمة:** {random.choice(CRIMES)}"),
                          color=discord.Color.red() if stars >= 3 else COLOR)
        e.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=e)

    # ── giveaways ──
    async def _end(self, guild: discord.Guild, msg_id: str, reroll=False) -> list[int] | None:
        g = cfg(guild)
        gw = g["giveaways"].get(msg_id)
        if gw is None:
            return None
        entries = [u for u in gw["entries"] if guild.get_member(u)]
        winners = random.sample(entries, min(gw["winners"], len(entries))) if entries else []
        gw["ended"] = True
        gw["last_winners"] = winners
        await store.save()
        channel = guild.get_channel(gw["channel"])
        if channel:
            try:
                await channel.get_partial_message(int(msg_id)).edit(
                    embed=giveaway_embed(gw, ended=True, winners=winners), view=None)
            except discord.HTTPException:
                pass
            text = (f"🎉 {'فائز جديد' if reroll else 'مبروك'} " + ", ".join(f"<@{w}>" for w in winners)
                    + f"! فزت بـ **{gw['prize']}**!") if winners else f"ما أحد شارك في قيف أواي **{gw['prize']}** 😢"
            try:
                await channel.send(text, allowed_mentions=discord.AllowedMentions(users=True))
            except discord.HTTPException:
                pass
        return winners

    @tasks.loop(seconds=20)
    async def giveaway_loop(self):
        for guild in self.bot.guilds:
            g = cfg(guild)
            for msg_id, gw in list(g["giveaways"].items()):
                ends = datetime.datetime.fromisoformat(gw["ends"])
                if not gw["ended"] and ends <= now():
                    await self._end(guild, msg_id)
                elif gw["ended"] and now() - ends > datetime.timedelta(days=7):
                    g["giveaways"].pop(msg_id)  # clean up old ones
                    await store.save()

    @giveaway_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    @giveaway.command(name="start", description="Start a giveaway (duration like 30m, 2h, 1d)")
    async def gw_start(self, interaction: discord.Interaction, prize: str, duration: str,
                       winners: app_commands.Range[int, 1, 20] = 1, channel: discord.TextChannel | None = None):
        td = parse_duration(duration)
        if td is None:
            return await interaction.response.send_message("Use a duration like `30m`, `2h` or `1d`.", ephemeral=True)
        target = channel or interaction.channel
        gw = {"prize": prize, "winners": winners, "host": interaction.user.id, "channel": target.id,
              "ends": (now() + td).isoformat(), "entries": [], "ended": False}
        msg = await target.send(embed=giveaway_embed(gw), view=GiveawayView())
        cfg(interaction.guild)["giveaways"][str(msg.id)] = gw
        await store.save()
        await interaction.response.send_message(
            f"✅ Giveaway started in {target.mention} for {fmt_duration(td)}.\nMessage ID: `{msg.id}`", ephemeral=True)

    @giveaway.command(name="end", description="End a giveaway now")
    async def gw_end(self, interaction: discord.Interaction, message_id: str):
        gw = cfg(interaction.guild)["giveaways"].get(message_id.strip())
        if gw is None or gw["ended"]:
            return await interaction.response.send_message("No running giveaway with that message ID.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self._end(interaction.guild, message_id.strip())
        await interaction.followup.send("✅ Giveaway ended.")

    @giveaway.command(name="reroll", description="Pick new winner(s) for an ended giveaway")
    async def gw_reroll(self, interaction: discord.Interaction, message_id: str):
        gw = cfg(interaction.guild)["giveaways"].get(message_id.strip())
        if gw is None or not gw["ended"]:
            return await interaction.response.send_message("No ended giveaway with that message ID.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self._end(interaction.guild, message_id.strip(), reroll=True)
        await interaction.followup.send("✅ Rerolled.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
