# Praamid car-ticket monitor — GitHub Actions setup

Watches **Kuivastu → Virtsu** on **26 July 2026**, for departures between
**14:00 and 18:10**, and emails you when one of those sailings shows open
car (small vehicle) capacity. Checks roughly every 5 minutes, runs entirely
on GitHub's servers — your computer can be off.

## 1. Create a Gmail app password (2 minutes)

The alert is sent **from your own Gmail to itself**, so it won't be
spam-filtered and the sender address is `oskar.telgmaa@gmail.com`.

1. Go to https://myaccount.google.com/apppasswords
   (requires 2-step verification on the account).
2. Create an app password named e.g. `praamid-monitor`.
3. Copy the 16-character password.

*(Skip this step if you already have an app password saved from a previous
run of this monitor — you can reuse it.)*

## 2. Create the repository

1. On github.com, click the **+** top-right → **New repository**.
2. Name it e.g. `praamid-monitor`, set it to **Private**, tick **Add a
   README file**, click **Create repository**.
3. **Add file → Create new file**, name it exactly `praamid_monitor.py`,
   paste in the script below, **Commit changes**.
4. **Add file → Create new file** again, name it exactly
   `.github/workflows/monitor.yml` (the slashes create the folders
   automatically), paste in the workflow file, **Commit changes**.

## 3. Add the two secrets

Repo → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**:

- `GMAIL_ADDRESS` = `oskar.telgmaa@gmail.com`
- `GMAIL_APP_PASSWORD` = the 16-character app password (spaces are fine)

Names must match exactly, all caps.

*(If reusing an existing repo from a previous run, these are likely already
set — check under Settings before re-adding them.)*

## 4. Send the test email

**Actions** tab → **praamid-monitor** (left sidebar) → **Run workflow**
dropdown → mode **`test-email`** → **Run workflow**. After ~1 minute check
for "Praamid monitor: test email" in your inbox.

## 5. Run the probe and check the log

**Run workflow** again with mode **`probe`**. Open the finished run → the
`check` job → expand **Run monitor**. You should see the raw API response
and parsed lines like `{'time': '14:20', 'cars': 0}`. If every line shows
`cars: None`, or you see an HTTP error, copy the output and send it to me.

## 6. Let it run

That's it — the schedule takes over, checking every 5–15 minutes (GitHub's
cron is best-effort, not exact). You'll get one email per departure that
opens up in the 14:00–18:10 window, not a repeat email for the same
departure. Alert memory lives in `alerted_departures.json`, committed back
to the repo automatically.

## Stopping it

- **Pause, can resume later:** Actions tab → praamid-monitor → **"..."**
  menu top-right → **Disable workflow** (same menu re-enables it).
- **Done for good:** repo → Settings → bottom of page, **Danger Zone** →
  **Delete this repository**.

## How the code works, step by step

The script is one file with four parts: settings, email, API handling, and
run modes. In execution order:

1. **Settings (top of file).** `DIRECTION` (`"KV"` = Kuivastu → Virtsu),
   `DATE` (`"2026-07-26"`), and `TIME_FROM` / `TIME_TO` (`"14:00"` /
   `"18:10"`) define what's being watched. These four constants are the
   only thing you edit to reuse the script for a different sailing — see
   below.

2. **Building the request.** `API_URL` points at praamid.ee's schedule
   endpoint — the same one the booking page itself calls to fill in the
   timetable. `HEADERS` makes the request look like a normal browser on
   the booking page (User-Agent, Referer), since the site rejects obvious
   bot traffic.

3. **`fetch_events()`** sends that request and returns the parsed JSON: a
   list of departures for the chosen date and direction, with capacity
   numbers.

4. **`extract_departures()`** normalises each departure into an `id`
   (unique per sailing), the departure `time`, and `cars` — the
   small-vehicle capacity, i.e. the number behind the car-column symbol in
   your screenshot. It tries several possible field names for the car
   count since the API isn't publicly documented; if none match, `cars`
   stays `None` and `--probe` mode shows the real structure so I can fix
   it.

5. **State: `load_alerted()` / `save_alerted()`.** A JSON file
   (`alerted_departures.json`) records which sailings you were already
   emailed about, so a departure with one open spot doesn't trigger an
   identical email on every check. GitHub Actions commits this file back
   to the repo so the memory survives between runs.

6. **`check_once()`** is one full check: fetch → parse → log every
   departure's car count → keep only departures inside the
   `TIME_FROM`–`TIME_TO` window → of those, pick the ones with `cars > 0`
   that aren't already in the state file → if any, send one email listing
   them and record their ids.

7. **`send_email()`** connects to Gmail's SMTP server over TLS, logs in
   with your address + app password from the environment variables, and
   sends the message from your address to your address.

8. **`main()`** picks the run mode from the command-line flag:
   - `--test` — send a test email and exit.
   - `--probe` — print the raw API response and parsed result, then exit.
   - `--once` — run `check_once()` a single time. This is what GitHub
     Actions calls on each scheduled run.
   - no flag — loop forever, checking every 5 minutes. For running on your
     own always-on machine instead of Actions.

   Errors inside the loop are caught and logged so one failed request
   doesn't kill the monitor.

The workflow file (`monitor.yml`) is the scheduler around this: it defines
the cron trigger and the manual Run-workflow menu, checks out the repo,
runs the script in the chosen mode with the secrets injected as
environment variables, and commits `alerted_departures.json` back if it
changed.

## Reusing it for other dates, directions, or time windows

Edit the four constants near the top of `praamid_monitor.py` (in GitHub:
open the file → pencil icon → edit → Commit changes):

```python
DIRECTION = "KV"
DATE = "2026-07-26"
TIME_FROM = "14:00"
TIME_TO = "18:10"
```

Direction codes are letter pairs, departure → arrival:

| Code | Route |
|------|-------|
| `HR` | Heltermaa → Rohuküla (Hiiumaa to mainland) |
| `RH` | Rohuküla → Heltermaa (mainland to Hiiumaa) |
| `KV` | Kuivastu → Virtsu (Muhu/Saaremaa to mainland) |
| `VK` | Virtsu → Kuivastu (mainland to Muhu/Saaremaa) |

You can confirm a code by opening praamid.ee, choosing the route, and
checking the address bar: `...?direction=XX`. To watch the whole day
instead of a window, set `TIME_FROM = "00:00"` and `TIME_TO = "23:59"`.

Whenever you change any of these four values, also delete
`alerted_departures.json` from the repo if it exists (open it → trash icon
→ commit), so old alert memory from the previous watch doesn't linger.
Then run `probe` once to confirm parsing still looks right.

One script instance watches one date + direction + window. To watch two
sailings at once (e.g. an outbound and a return), the simplest route is a
second repo — or ask me and I'll extend the script to take a list.
