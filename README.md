# marketplace-watcher

Scans your shopping list against second-hand marketplaces, tracks price
history in SQLite, and sends new listings / price drops to Telegram.
Runs on a schedule via GitHub Actions — no need for your laptop to be on.

Repo: https://github.com/Call3x/marketplace-watcher (private)

## Sites covered

- **Vinted** (FR/BE) — works via Vinted's internal catalog API, no login needed.
- **AutoScout24** (FR/BE/DE) — works via the site's embedded JSON data, no login needed.
- **Leboncoin, Leboncoin Auto, La Centrale — not included.** All three sit
  behind DataDome anti-bot and return a CAPTCHA challenge on the very first
  unauthenticated request, even to the plain HTML page. Getting past that
  reliably needs a stealth headless browser or a paid unblocking proxy —
  not worth it for a twice-a-day personal scan.

## How scheduling works now

The scraper runs on **GitHub Actions**, not this laptop — see
`.github/workflows/watch.yml`. It fires roughly twice a day (around 8am and
8pm Europe/Paris, scheduled at :17 past the hour rather than :00 since
GitHub's free tier queues on-the-hour jobs together and can delay them by
hours; :17 usually starts within a few minutes of the scheduled time — but
GitHub does not guarantee exact timing, treat it as "sometime around" rather
than a precise alarm).

After each run, the workflow commits the updated `data/watcher.db` (price
history) back to the `main` branch, so state persists across runs even
though each GitHub Actions run starts on a fresh machine.

There is **no local cron job** on this laptop anymore — it was removed once
GitHub Actions was confirmed working, to avoid duplicate notifications.

You can also trigger a run manually any time from the GitHub UI (Actions tab
→ marketplace-watch → Run workflow) or via `gh workflow run watch.yml`.

## Editing your shopping list

### Option A: the GUI (recommended for day-to-day changes)

```
./run_gui.sh
```
or double-click the **ShoppingAgent** icon on the Desktop / in the app menu
(installed via `./install_desktop_shortcut.sh`, one-time setup — copies an
icon and a `.desktop` launcher into `~/.local/share/applications/` and
`~/Desktop/`). Opens http://localhost:5000 in your browser automatically.

Add/edit/delete items with a form — fields adapt per category
(electronics/watches vs. cars). **Saving commits and pushes `config.yaml`
to GitHub automatically** — the next scheduled Actions run picks up the
new filters, no extra step needed.

Requires `flask` and `ruamel.yaml` (already installed on this machine via
`pip3 install --break-system-packages --user -r requirements-gui.txt`).

The GUI uses `ruamel.yaml` specifically (not plain PyYAML) so that editing
one item doesn't strip the explanatory comments on the others.

### Option B: edit config.yaml directly

Each item has:
- `keywords` — search terms
- `exclude_keywords` — substrings that disqualify a match (accessories, games, wrong models, etc.)
- `price_min` / `price_max`
- adapter-specific fields (cars have `year_min`/`year_max`/`mileage_max_km`, etc.)

After a manual edit, commit and push yourself so GitHub Actions sees it:
```
git add config.yaml && git commit -m "update shopping list" && git push
```

Tune `exclude_keywords` over time — marketplace search is fuzzy and will
surface false positives (a game instead of a console, a calculator instead
of a watch) until the exclusion list catches them.

## Testing manually

```
python3 run.py --dry-run
```
Prints what *would* be sent without touching Telegram or marking listings as seen.

```
python3 run.py
```
Real run — sends Telegram messages and updates the database (needs `.env`
with `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` set locally, or run via
`./run_cron.sh` which loads `.env` automatically).

## How it decides what to notify about

- First time a listing is seen → notified as "new".
- If a previously-seen listing's price drops → notified as "price drop".
- Everything else (unchanged price, already notified) is silent.
- A listing that stops appearing in search results is marked inactive
  internally (sold/delisted) — no notification for that, just stops being
  tracked for price drops.

## Secrets

`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` live in **GitHub repo secrets**
(Settings → Secrets and variables → Actions) for the scheduled runs, and in
the local `.env` file (gitignored) for manual local runs.

## Known limitations

- **Car search** currently uses AutoScout24 only. It's cross-border by
  nature (BMW 330i F30 LCI in your budget is genuinely scarce — first live
  test found only 2 matches in the €15-19k / <100k km / 2017-19 range, both
  in Germany). Worth widening the mileage/price band if matches stay rare.
- **Xbox/watch matching** relies on keyword + exclusion-list filtering, not
  true categorization — expect occasional false positives until the
  exclude lists are tuned from real notifications.
- GitHub Actions free-tier scheduled runs are not guaranteed to fire exactly
  on time — see "How scheduling works now" above.
- If the GUI's save and a scheduled Actions run push to `main` at nearly the
  same time, both retry with a rebase-and-retry loop rather than failing
  outright, but it's still possible (rare) for a save to need a manual retry
  if you see a git error in the GUI's flash message.
