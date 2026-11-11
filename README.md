# GTA Server Bot

An all-in-one Discord bot for a GTA / FiveM roleplay server:
tickets, live server status, whitelist applications, moderation, giveaways and more. **50+ commands.**

## Run it (GitHub Codespaces, works on iPad)
1. Add a Codespaces secret `DISCORD_TOKEN` (github.com/settings/codespaces).
2. Open the repo → **Code → Codespaces → Create codespace**.
3. In the terminal:
```
pip install -r requirements.txt
python bot.py
```
Wait for `✅ Logged in as ...`. Stop it at github.com/codespaces when you're done.

## Create & invite the bot
1. https://discord.com/developers/applications → New Application → **Bot** → Reset Token (copy it).
2. Turn ON **Server Members Intent**.
3. OAuth2 → URL Generator → `bot` + `applications.commands` → permission **Administrator** → open link → add to server.
4. Server Settings → Roles: drag the bot's role **near the top** (above staff, whitelist and verify roles).

## First-time setup (in Discord)
```
/config support-role        @Staff
/config log-channel         #ticket-logs
/config mod-log             #mod-logs
/config server              123.45.67.89:30120   (connect_link optional)
/config welcome-channel     #welcome
/config verify-role         @Citizen
/config applications-channel #applications   (staff-only channel)
/config whitelist-role      @Whitelisted
/config suggestion-channel  #suggestions
/config view
```
Then post the panels in their channels:
`/ticket-panel` in #support · `/verify-panel` in #rules · `/apply-panel` in #whitelist · `/status-panel` in #server-status

## Commands
**🎫 Tickets** — `/ticket-panel` `/close` `/claim` `/add` `/remove` `/rename` `/blacklist` `/ticket-stats`
Ticket types: Addon Not Working, Download Problem, Buy an Addon, Request an Addon, Partnership, Report a Member, General.
Claim/close buttons, transcripts to logs + DM, 1–5 ⭐ ratings, auto-close, top staff leaderboard.

**🟢 Server** (optional — only if you run your own FiveM server) — `/status` `/players` `/connect` `/status-panel` (auto-updates every minute) `/restart` `/announce`
The bot's activity shows live player count.

**👥 Community** — `/verify-panel` (rules + accept button) `/apply-panel` (optional, roleplay whitelist form → staff Approve/Deny →
role + DM) `/suggest` · automatic welcome messages

**🔨 Moderation** — `/warn` `/warnings` `/clearwarns` `/kick` `/ban` `/unban` `/timeout` `/untimeout`
`/purge` `/slowmode` `/lock` `/unlock` — all logged, members get a DM

**🧰 Utility** — `/help` `/ping` `/userinfo` `/serverinfo` `/avatar` `/poll`

**🎲 Fun** — `/car` `/wanted` `/giveaway start|end|reroll`

**⚙️ Settings** — `/config …` (13 settings)

## Customize
- Ticket types & form questions: `TICKET_TYPES` in `cogs/tickets.py`
- Default rules: `DEFAULT_RULES` in `cogs/community.py`
- Colors: `core.py`

`data.json` is created automatically and stores settings, tickets, warnings and giveaways — don't delete it.
In Codespaces it's kept as long as you don't delete the codespace.
