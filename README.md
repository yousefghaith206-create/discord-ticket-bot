# Ticket Bot — setup (works fully from an iPad)

## 1. Create the bot (Safari on iPad is fine)
1. Open https://discord.com/developers/applications → **New Application** → give it a name.
2. **Bot** tab → **Reset Token** → copy the token. Never share it.
3. Same tab → turn ON **Server Members Intent** → Save.
4. **OAuth2 → URL Generator** → tick `bot` and `applications.commands`.
   Bot permissions: **Administrator** (simplest), or: Manage Channels, Manage Roles,
   Manage Messages, View Channels, Send Messages, Embed Links, Attach Files, Read Message History.
5. Open the generated link → pick your friend's server → Authorize.
   (Your friend must do this step, or give you Manage Server.)

## 2. Host it 24/7
An iPad can't keep a bot running — iPadOS pauses apps in the background.
Use a bot host with a web panel (works from Safari):
1. Sign up, create a **Python** server.
2. Upload `bot.py` and `requirements.txt` (Files tab / file manager).
3. Set the startup file to `bot.py`.
4. Add an environment / startup variable: `DISCORD_TOKEN` = your token
   (or upload a `.env` file containing `DISCORD_TOKEN=your-token`).
5. Press **Start**. The console should say `✅ Logged in as ...`.

## 3. Configure in Discord (admins)
```
/config support-role  @Staff
/config log-channel   #ticket-logs
/config category      Tickets        (optional — made automatically)
/config autoclose     48             (optional, hours; 0 = off)
/config view
```
Then go to the channel for the panel (e.g. #support) and type `/setup`.

Important: in Server Settings → Roles, drag the **bot's role above** the staff role.

## Commands
| Command | Who | What |
|---|---|---|
| `/setup [title] [description]` | Admins | Post the ticket panel |
| `/config ...` | Admins | Settings |
| `/blacklist @user` | Admins | Block/unblock from opening tickets |
| `/stats` | Anyone | Opened/closed counts + average rating |
| `/claim` | Staff | Take ownership of a ticket |
| `/close [reason]` | Owner / staff | Close the ticket |
| `/add @user` | Owner / staff | Add someone to the ticket |
| `/remove @user` | Staff | Remove someone |
| `/rename name` | Staff | Rename the ticket channel |

## Customize ticket types
Edit `TICKET_TYPES` at the top of `bot.py` (labels, emojis, form questions), then restart.

`data.json` is created automatically and stores settings and open tickets — don't delete it.
