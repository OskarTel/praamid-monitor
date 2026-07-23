#!/usr/bin/env python3
"""
Praamid.ee car-ticket monitor: Kuivastu -> Virtsu, 26 July 2026,
departures between 14:00 and 18:10.

Checks the praamid.ee schedule API every 5 minutes. When a departure in the
configured time window shows available small-vehicle (car) capacity, sends
an email alert via Gmail SMTP.

Usage:
  python3 praamid_monitor.py --test    # send a test email and exit
  python3 praamid_monitor.py --probe   # print raw API response and exit
  python3 praamid_monitor.py           # run the monitor loop

Requires two environment variables (see README):
  GMAIL_ADDRESS       your Gmail address (sender AND recipient)
  GMAIL_APP_PASSWORD  16-character Gmail app password
"""

import json
import os
import smtplib
import ssl
import sys
import time
import urllib.request
from datetime import datetime
from email.message import EmailMessage

# ---------------------------------------------------------------- settings
DIRECTION = "KV"            # Kuivastu -> Virtsu
DATE = "2026-07-26"
TIME_FROM = "14:00"         # only alert for departures in this window
TIME_TO = "18:10"           # (inclusive of both ends)
CHECK_INTERVAL_SEC = 300    # 5 minutes
STATE_FILE = "alerted_departures.json"

API_URL = (
    "https://www.praamid.ee/online/events"
    f"?direction={DIRECTION}&departure-date={DATE}&time-shift=180"
)

ROUTE_LABELS = {
    "HR": "Heltermaa -> Rohuküla",
    "RH": "Rohuküla -> Heltermaa",
    "KV": "Kuivastu -> Virtsu",
    "VK": "Virtsu -> Kuivastu",
}
ROUTE_LABEL = ROUTE_LABELS.get(DIRECTION, DIRECTION)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.praamid.ee/portal/ticket/departure?direction=HR",
    "Accept-Language": "et,en;q=0.9",
}

EMAIL_TO = "oskar.telgmaa@gmail.com"


# ---------------------------------------------------------------- email
def send_email(subject: str, body: str) -> None:
    sender = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        sys.exit(
            "Missing GMAIL_ADDRESS or GMAIL_APP_PASSWORD environment variable. "
            "See README for setup."
        )

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.set_content(body)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
    log(f"Email sent: {subject}")


# ---------------------------------------------------------------- API
def fetch_events() -> dict:
    req = urllib.request.Request(API_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_departures(data: dict) -> list[dict]:
    """
    Normalise the API response into a list of:
      {"id": ..., "time": "HH:MM", "cars": <int or None>}

    The praamid API has historically returned items with a 'capacities'
    object whose 'sv' key is the small-vehicle count. This parser tries
    the known field names but degrades gracefully; run --probe to see
    the actual structure if nothing is found.
    """
    items = data.get("items") or data.get("events") or []
    out = []
    for it in items:
        caps = it.get("capacities") or {}
        cars = None
        for key in ("sv", "smallVehicles", "small-vehicles", "cars"):
            if key in caps:
                cars = caps[key]
                break
        dtstart = it.get("dtstart") or it.get("departure") or ""
        time_str = dtstart[11:16] if len(dtstart) >= 16 else str(dtstart)
        out.append(
            {
                "id": it.get("uid") or it.get("id") or f"{DATE}T{time_str}",
                "time": time_str,
                "cars": cars,
            }
        )
    return out


# ---------------------------------------------------------------- state
def load_alerted() -> set:
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_alerted(alerted: set) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(alerted), f)


# ---------------------------------------------------------------- main loop
def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def check_once(alerted: set) -> None:
    data = fetch_events()
    departures = extract_departures(data)

    if not departures:
        log("WARNING: no departures parsed from API response. "
            "Run with --probe and check the structure.")
        return

    in_window = [d for d in departures if TIME_FROM <= d["time"] <= TIME_TO]
    open_now = [
        d for d in in_window
        if isinstance(d["cars"], (int, float)) and d["cars"] > 0
    ]
    summary = ", ".join(f"{d['time']}={d['cars']}" for d in departures)
    log(f"Car capacity per departure: {summary} "
        f"(watching {TIME_FROM}-{TIME_TO})")

    new_openings = [d for d in open_now if d["id"] not in alerted]
    if new_openings:
        lines = [
            f"  {d['time']}  ->  {d['cars']} car place(s) available"
            for d in new_openings
        ]
        body = (
            f"Car ticket availability found for {ROUTE_LABEL} "
            f"on {DATE} (window {TIME_FROM}-{TIME_TO}):\n\n" +
            "\n".join(lines) +
            f"\n\nBook now: https://www.praamid.ee/portal/ticket/departure?direction={DIRECTION}"
        )
        send_email(
            f"Praamid ALERT: car spots open {DATE} "
            f"({', '.join(d['time'] for d in new_openings)})",
            body,
        )
        alerted.update(d["id"] for d in new_openings)
        save_alerted(alerted)


def main() -> None:
    if "--test" in sys.argv:
        send_email(
            "Praamid monitor: test email",
            "This is a test. If you can read this, alerts will arrive the "
            f"same way when car tickets open up for {ROUTE_LABEL} "
            f"on {DATE}, for departures between {TIME_FROM} and {TIME_TO}."
            "\n\nSent from your own Gmail account via SMTP, so it "
            "will not be spam-filtered.",
        )
        return

    if "--once" in sys.argv:
        # Single check, for scheduled runners like GitHub Actions.
        alerted = load_alerted()
        check_once(alerted)
        return

    if "--probe" in sys.argv:
        data = fetch_events()
        print(json.dumps(data, indent=2, ensure_ascii=False)[:8000])
        print("\n--- parsed ---")
        for d in extract_departures(data):
            print(d)
        return

    log(f"Monitoring {API_URL} every {CHECK_INTERVAL_SEC // 60} min. Ctrl-C to stop.")
    alerted = load_alerted()
    while True:
        try:
            check_once(alerted)
        except Exception as e:  # keep the loop alive on transient errors
            log(f"ERROR: {e!r}")
        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
