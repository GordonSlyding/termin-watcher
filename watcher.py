#!/usr/bin/env python3
"""
Doctolib Multi-Arzt Termin-Watcher
----------------------------------
Prueft MEHRERE Aerzte gleichzeitig und schickt eine ntfy-Push, sobald bei
einem davon ein passender Termin frei wird. Die Aerzte-Liste kommt als JSON
aus dem Secret WATCH_CONFIG. Es wird nichts automatisch gebucht - du bekommst
nur die Meldung und buchst selbst.
"""

import os
import json
import time
import datetime as dt
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests

NTFY_TOPIC = os.environ["NTFY_TOPIC"]
DOCTORS = json.loads(os.environ["WATCH_CONFIG"])   # Liste von Aerzten (JSON)

# Wie lange dieser eine Lauf prueft. 48 Runden x 5 Min = ~4 Std,
# sicher unter dem 6-Stunden-Limit von GitHub Actions.
ROUNDS = int(os.environ.get("ROUNDS", "48"))
INTERVAL_SECONDS = int(os.environ.get("INTERVAL_SECONDS", "300"))

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
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
    if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
        print(f"   ! Keine JSON-Antwort (Status {r.status_code}) - "
              f"Token abgelaufen oder Bot-Schutz?")
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


def notify(doc_name: str, slot: dt.datetime, booking_url: str) -> None:
    """Schickt eine ntfy-Push fuer einen gefundenen Termin."""
    msg = f"{doc_name}: Termin frei am {slot:%a %d.%m.} um {slot:%H:%M} Uhr"
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=msg.encode("utf-8"),
        headers={
            "Title": "Doctolib: Termin frei!",
            "Priority": "urgent",
            "Tags": "calendar",
            "Click": booking_url,
        },
        timeout=20,
    )


def check_doctor(doc: dict, seen: set) -> None:
    """Prueft einen einzelnen Arzt und benachrichtigt bei neuen Treffern."""
    slots = fetch_slots(doc["url"])

    # deadline = null  -> JEDER Termin zaehlt
    # deadline = Datum -> nur Termine VOR diesem Zeitpunkt
    deadline_raw = doc.get("deadline")
    if deadline_raw:
        deadline = dt.datetime.fromisoformat(deadline_raw)
        slots = [s for s in slots if s < deadline]

    new = [s for s in slots if s not in seen]
    if new:
        best = min(new)
        print(f"   TREFFER bei {doc['name']}: {best:%d.%m. %H:%M} -> Push gesendet")
        notify(doc["name"], best, doc.get("booking_url", ""))
        seen.update(new)
    else:
        print(f"   {doc['name']}: nichts Passendes frei.")


def main() -> None:
    # pro Arzt eine eigene "schon gemeldet"-Liste, damit dich derselbe Slot
    # nicht in jeder Runde erneut anpingt.
    seen = {i: set() for i in range(len(DOCTORS))}
    print(f"Watcher gestartet fuer {len(DOCTORS)} Arzt/Aerzte. "
          f"{ROUNDS} Runden alle {INTERVAL_SECONDS // 60} Min.")

    for r in range(1, ROUNDS + 1):
        print(f"--- Runde {r}/{ROUNDS} ({dt.datetime.now():%H:%M}) ---")
        for i, doc in enumerate(DOCTORS):
            try:
                check_doctor(doc, seen[i])
            except Exception as e:
                print(f"   Fehler bei {doc.get('name', '?')}: {e}")
        if r < ROUNDS:
            time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
