# marketplace-watcher

Scans your shopping list against second-hand marketplaces twice a day, tracks
price history in SQLite, and sends new listings / price drops to Telegram.

## Sites covered

- **Vinted** (FR/BE) — works via Vinted's internal catalog API, no login needed.
- **AutoScout24** (FR/BE/DE) — works via the site's embedded JSON data, no login needed.
- **Leboncoin, Leboncoin Auto, La Centrale — not included.** All three sit
  behind DataDome anti-bot and return a CAPTCHA challenge on the very first
  unauthenticated request, even to the plain HTML page. Getting past that
  reliably needs a stealth headless browser or a paid unblocking proxy —
  not worth it for a twice-a-day personal scan. If this becomes a priority,
  say so and we can revisit with one of those approaches.

## Setup

### 1. Telegram bot (one-time, ~2 minutes)

1. In Telegram, message **@BotFather** → `/newbot` → follow the prompts.
   You'll get a token that looks like `123456789:AA...`.
2. Message your new bot anything (e.g. "hi") so it can message you back.
3. Get your chat ID: message **@userinfobot** and it will reply with your ID.
4. Copy `.env.example` to `.env` and fill in both values:
   ```
   cp .env.example .env
   # edit .env with your token and chat id
   ```

### 2. Dependencies

Already installed on this machine (`requests`, `pyyaml`, via
`pip3 install --break-system-packages --user`, since `python3-venv` wasn't
installed and sudo wasn't available non-interactively during setup).

If you'd prefer an isolated virtualenv instead:
```
sudo apt install python3.12-venv
python3 -m venv venv
./venv/bin/pip install requests pyyaml
```
and adjust `run_cron.sh` to call `venv/bin/python3` instead of `python3`.

### 3. Edit your shopping list

Edit `config.yaml`. Each item has:
- `keywords` — search terms
- `exclude_keywords` — substrings that disqualify a match (accessories, games, wrong models, etc.)
- `price_min` / `price_max`
- adapter-specific fields (cars have `year_min`/`year_max`/`mileage_max_km`, etc.)

Tune `exclude_keywords` over the first week or two — marketplace search is
fuzzy and will surface false positives (a game instead of a console, a
calculator instead of a watch) until the exclusion list catches them.

### 4. Test manually before scheduling

```
python3 run.py --dry-run
```
Prints what *would* be sent without touching Telegram or marking listings as seen.

```
python3 run.py
```
Real run — sends Telegram messages and updates the database.

### 5. Schedule with cron

Runs morning and evening, ~15 min budget each:
```
crontab -e
```
Add:
```
0 8  * * * /home/callex/marketplace-watcher/run_cron.sh
0 20 * * * /home/callex/marketplace-watcher/run_cron.sh
```
Only fires if the laptop is on and awake at that time. Logs land in `logs/`.

## How it decides what to notify about

- First time a listing is seen → notified as "new".
- If a previously-seen listing's price drops → notified as "price drop".
- Everything else (unchanged price, already notified) is silent.
- A listing that stops appearing in search results is marked inactive
  internally (sold/delisted) — no notification for that, just stops being
  tracked for price drops.

## Known limitations

- **Car search** currently uses AutoScout24 only. It's cross-border by
  nature (BMW 330i F30 LCI in your budget is genuinely scarce right now —
  first live test found only 2 matches in the €15-19k / <100k km / 2017-19
  range, both in Germany). Worth widening the mileage/price band if matches
  stay rare.
- **Xbox/watch matching** relies on keyword + exclusion-list filtering, not
  true categorization — expect occasional false positives until the
  exclude lists are tuned from real notifications.
- Runs only when the laptop is on (cron). See project chat history for the
  plan to migrate to GitHub Actions (free, true 24/7) once this is proven
  out for a week or two.
