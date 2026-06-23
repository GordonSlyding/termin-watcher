#!/usr/bin/env python3
"""
Doctolib Termin-Watcher - GitHub-Actions-Version.
Prueft EINMAL pro Lauf, ob ein Termin vor dem eigenen frei ist, und schickt
bei einem Treffer eine Push-Nachricht via ntfy. Die Konfiguration kommt aus
Umgebungsvariablen (GitHub Secrets) - es steht KEIN persoenliches Token in
dieser Datei.
"""

import os
import datetime as dt
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests

# --- Konfiguration kommt aus den GitHub Secrets (Umgebungsvariablen) ---
AVAILABILITIES_URL = os.environ["AVAILABILITIES_URL"]
BOOKING_URL = os.environ.get("BOOKING_URL", "")
MY_APPOINTMENT = os.environ["MY_APPOINTMENT"]   # z.B. 2026-08-12T09:30
NTFY_TOPIC = os.environ["NTFY_TOPIC"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def todays_url(url: str) -> str:
    """Setzt start_date auf heute, damit ab jetzt gesucht wird."""
    parts = urlparse(url)
    q = parse_qs(parts.query)
    q["start_date"] = [dt.date.today().isoformat()]
    return urlunparse(parts._replace(query=urlencode(q, doseq=True)))


def fetch_slots(url: str) -> list[dt.datetime]:
    """Holt alle freien Slot-Zeitpunkte als Liste von datetime-Objekten."""
    r = requests.get(todays_url(url), headers=HEADERS, timeout=20)
    ctype = r.headers.get("content-type", "")
    if r.status_code != 200 or "json" not in ctype:
        print(f"Keine JSON-Antwort (Status {r.status_code}) - "
              f"evtl. Bot-Schutz/Captcha oder Token abgelaufen.")
        return []

    data = r.json()
    slots: list[dt.datetime] = []
    for day in data.get("availabilities", []):
        for s in day.get("slots", []):
            value = s if isinstance(s, str) else s.get("start_date")
            if value:
                slots.append(dt.datetime.fromisoformat(value).replace(tzinfo=None))

    nxt = data.get("next_slot")
    if nxt:
        slots.append(dt.datetime.fromisoformat(nxt).replace(tzinfo=None))

    return slots


def notify(slot: dt.datetime) -> None:
    """Schickt eine Push-Nachricht via ntfy."""
    msg = f"Frueherer Termin frei: {slot:%a %d.%m.} um {slot:%H:%M} Uhr"
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=msg.encode("utf-8"),
        headers={
            "Title": "Doctolib: Termin frei!",
            "Priority": "urgent",
            "Tags": "calendar",
            "Click": BOOKING_URL,
        },
        timeout=20,
    )


def main() -> None:
    deadline = dt.datetime.fromisoformat(MY_APPOINTMENT)
    earlier = [s for s in fetch_slots(AVAILABILITIES_URL) if s < deadline]
    if earlier:
        best = min(earlier)
        print(f"TREFFER: {best:%d.%m. %H:%M} - Push wird gesendet.")
        notify(best)
    else:
        print(f"[{dt.datetime.now():%Y-%m-%d %H:%M}] Nichts Frueheres frei.")


if __name__ == "__main__":
    main()
