"""
collector.py
============
Zbiera pozycje GPS pojazdów ZTM Warszawa i oblicza opóźnienia
dla linii obsługujących okolice ul. Kameralnej 3.

Uruchamiany co 5 minut przez GitHub Actions.
Wyniki dopisuje do data/delays.csv i commituje do repo.

Wymagane zmienne środowiskowe:
  ZTM_API_KEY  — klucz z api.um.warszawa.pl (darmowy, wymaga rejestracji)
"""

import os
import csv
import sys
import math
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path
from stops import STOPS, ALL_LINES, RESOURCE_IDS

# ─── KONFIGURACJA ─────────────────────────────────────────────────────────────

API_KEY   = os.environ.get("ZTM_API_KEY", "")
BASE_URL  = "https://api.um.warszawa.pl/api/action"
DATA_FILE = Path(__file__).parent / "data" / "delays.csv"

WARSAW_TZ       = timezone(timedelta(hours=2))
NEARBY_RADIUS_KM = 0.8
CENTER_LAT      = 52.2601
CENTER_LON      = 21.0456

CSV_HEADERS = [
    "timestamp", "timestamp_local", "line", "vehicle_type",
    "brigade", "lat", "lon", "distance_km",
    "scheduled_min", "delay_min", "stop_name", "stop_id",
]

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def fetch_all_vehicles(vehicle_type: str) -> list[dict]:
    """
    Pobiera WSZYSTKIE pojazdy danego typu jednym zapytaniem.
    Znacznie szybsze niż pytanie o każdą linię osobno.
    """
    resource_id = (RESOURCE_IDS["trams_gps"] if vehicle_type == "tram"
                   else RESOURCE_IDS["buses_gps"])
    type_code   = "1" if vehicle_type == "tram" else "2"

    try:
        resp = httpx.get(
            f"{BASE_URL}/busestrams_get",
            params={
                "resource_id": resource_id,
                "apikey":      API_KEY,
                "type":        type_code,
            },
            timeout=30,  # jedno zapytanie, można dać więcej czasu
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for v in data.get("result", []):
            try:
                results.append({
                    "line":    str(v.get("Lines", "")).strip(),
                    "brigade": str(v.get("Brigade", "")).strip(),
                    "lat":     float(v.get("Lat", 0)),
                    "lon":     float(v.get("Lon", 0)),
                    "time":    str(v.get("Time", "")),
                    "type":    vehicle_type,
                })
            except (ValueError, TypeError):
                continue

        return results

    except httpx.TimeoutException:
        print(f"  ⚠️  Timeout przy pobieraniu {vehicle_type} — API ZTM nie odpowiada")
        return []
    except httpx.HTTPError as e:
        print(f"  ⚠️  Błąd HTTP {vehicle_type}: {e}")
        return []


def fetch_timetable_departures(busstop_id, busstop_nr, line) -> list[str]:
    """Pobiera rozkładowe godziny odjazdów dla przystanku i linii."""
    try:
        resp = httpx.get(
            f"{BASE_URL}/dbtimetable_get",
            params={
                "id":        RESOURCE_IDS["timetable"],
                "busstopId": busstop_id,
                "busstopNr": busstop_nr,
                "line":      line,
                "apikey":    API_KEY,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

        departures = []
        for item in data.get("result", []):
            values = {v["key"]: v["value"] for v in item.get("values", [])}
            t = values.get("czas", "")
            if t:
                departures.append(t)
        return sorted(departures)

    except httpx.HTTPError:
        return []


def calculate_delay(now_local, departures) -> float | None:
    """Oblicza opóźnienie w minutach względem najbliższego kursu (±30 min)."""
    if not departures:
        return None

    now_min = now_local.hour * 60 + now_local.minute
    best    = None

    for dep_str in departures:
        parts = dep_str.split(":")
        if len(parts) < 2:
            continue
        try:
            dep_min = int(parts[0]) * 60 + int(parts[1])
            diff    = now_min - dep_min
            if abs(diff) <= 30 and (best is None or abs(diff) < abs(best)):
                best = diff
        except ValueError:
            continue

    return best


def find_nearest_stop(line):
    """Zwraca pierwszy pasujący przystanek dla danej linii."""
    for stop in STOPS:
        if line in stop["lines"]:
            return stop
    return None


def ensure_csv():
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=CSV_HEADERS).writeheader()
        print(f"  📄 Utworzono nowy plik: {DATA_FILE}")


def append_rows(rows):
    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=CSV_HEADERS).writerows(rows)

# ─── GŁÓWNA LOGIKA ────────────────────────────────────────────────────────────

def collect():
    if not API_KEY:
        print("❌ Brak ZTM_API_KEY — ustaw zmienną środowiskową")
        sys.exit(1)

    now_utc   = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(WARSAW_TZ)
    ts_utc    = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    ts_local  = now_local.strftime("%Y-%m-%d %H:%M")

    print(f"\n🚌 Kolektor ZTM — {ts_local}")
    ensure_csv()

    new_rows = []

    for vehicle_type in ("tram", "bus"):
        # Jedno zapytanie po WSZYSTKIE pojazdy
        all_vehicles = fetch_all_vehicles(vehicle_type)
        print(f"  📡 {vehicle_type.upper()}: pobrano {len(all_vehicles)} pojazdów łącznie")

        # Filtruj: tylko linie które nas interesują + w pobliżu Kameralnej
        nearby = 0
        for v in all_vehicles:
            if v["line"] not in ALL_LINES:
                continue

            dist = haversine_km(v["lat"], v["lon"], CENTER_LAT, CENTER_LON)
            if dist > NEARBY_RADIUS_KM:
                continue

            nearby += 1
            nearest_stop = find_nearest_stop(v["line"])
            delay_min    = None
            stop_name    = ""
            stop_id      = ""

            if nearest_stop:
                stop_name  = nearest_stop["name"]
                stop_id    = nearest_stop["busstopId"]
                departures = fetch_timetable_departures(
                    nearest_stop["busstopId"],
                    nearest_stop["busstopNr"],
                    v["line"],
                )
                delay_min = calculate_delay(now_local, departures)

            new_rows.append({
                "timestamp":       ts_utc,
                "timestamp_local": ts_local,
                "line":            v["line"],
                "vehicle_type":    vehicle_type,
                "brigade":         v["brigade"],
                "lat":             round(v["lat"], 6),
                "lon":             round(v["lon"], 6),
                "distance_km":     round(dist, 3),
                "scheduled_min":   "",
                "delay_min":       round(delay_min, 1) if delay_min is not None else "",
                "stop_name":       stop_name,
                "stop_id":         stop_id,
            })

        print(f"  🎯 W pobliżu Kameralnej ({NEARBY_RADIUS_KM}km): {nearby} pojazdów")

    if new_rows:
        append_rows(new_rows)
        print(f"  ✅ Zapisano {len(new_rows)} rekordów do CSV")
    else:
        print("  ℹ️  Brak pojazdów naszych linii w pobliżu Kameralnej")

    size = DATA_FILE.stat().st_size / 1024 if DATA_FILE.exists() else 0
    print(f"  📊 Rozmiar CSV: {size:.1f} KB")
    return len(new_rows)


if __name__ == "__main__":
    collect()
