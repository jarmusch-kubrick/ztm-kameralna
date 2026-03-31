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

# Strefa czasowa Warszawa
WARSAW_TZ = timezone(timedelta(hours=2))  # CEST (lato); zimą zmień na +1

# Promień wokół Kameralnej 3 — pojazdy w tym promieniu liczymy jako "przy przystanku"
# Większy promień = więcej danych, mniej precyzji
NEARBY_RADIUS_KM = 0.8  # 800 metrów

# Współrzędne centrum obszaru (Kameralna 3, Praga Północ)
CENTER_LAT = 52.2601
CENTER_LON = 21.0456

# Nagłówki CSV
CSV_HEADERS = [
    "timestamp",        # ISO8601, czas UTC
    "timestamp_local",  # czas lokalny Warszawa (czytelny)
    "line",             # numer linii (np. "4", "102")
    "vehicle_type",     # "tram" lub "bus"
    "brigade",          # numer brygady (identyfikator pojazdu)
    "lat",              # szerokość GPS pojazdu
    "lon",              # długość GPS pojazdu
    "distance_km",      # odległość od centrum Kameralnej
    "scheduled_min",    # rozkładowy czas do przystanku (minuty) — jeśli dostępny
    "delay_min",        # opóźnienie w minutach (+ = spóźniony, - = przed czasem)
    "stop_name",        # nazwa najbliższego przystanku z naszej listy
    "stop_id",          # busstopId
]

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Odległość między dwoma punktami GPS w kilometrach."""
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def fetch_vehicles(vehicle_type: str) -> list[dict]:
    """
    Pobiera aktualne pozycje GPS pojazdów z API UM Warszawa.
    vehicle_type: "bus" lub "tram"
    Zwraca listę słowników z polami: line, brigade, lat, lon, time
    """
    resource_id = (RESOURCE_IDS["buses_gps"] if vehicle_type == "bus"
                   else RESOURCE_IDS["trams_gps"])

    # Filtrujemy po liniach — mniejsza odpowiedź, szybsze przetwarzanie
    # API pozwala filtrować po jednej linii naraz, więc robimy pętlę
    results = []
    relevant_lines = [
        line for line in ALL_LINES
        if any(line in stop["lines"] and stop["type"] == vehicle_type
               for stop in STOPS)
    ]

    for line in relevant_lines:
        try:
            resp = httpx.get(
                f"{BASE_URL}/busestrams_get",
                params={
                    "resource_id": resource_id,
                    "apikey": API_KEY,
                    "type": "1" if vehicle_type == "tram" else "2",
                    "line": line,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            for vehicle in data.get("result", []):
                try:
                    results.append({
                        "line":    str(vehicle.get("Lines", "")).strip(),
                        "brigade": str(vehicle.get("Brigade", "")).strip(),
                        "lat":     float(vehicle.get("Lat", 0)),
                        "lon":     float(vehicle.get("Lon", 0)),
                        "time":    str(vehicle.get("Time", "")),
                        "type":    vehicle_type,
                    })
                except (ValueError, TypeError):
                    continue

        except httpx.HTTPError as e:
            print(f"  ⚠️  Błąd GPS {vehicle_type} linia {line}: {e}")
            continue

    return results


def fetch_timetable_departures(busstop_id: str, busstop_nr: str, line: str) -> list[str]:
    """
    Pobiera rozkładowe godziny odjazdów dla danego przystanku i linii.
    Zwraca listę stringów w formacie "HH:MM:SS".
    """
    try:
        resp = httpx.get(
            f"{BASE_URL}/dbtimetable_get",
            params={
                "id":         RESOURCE_IDS["timetable"],
                "busstopId":  busstop_id,
                "busstopNr":  busstop_nr,
                "line":       line,
                "apikey":     API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        departures = []
        for item in data.get("result", []):
            values = {v["key"]: v["value"] for v in item.get("values", [])}
            time_str = values.get("czas", "")
            if time_str:
                departures.append(time_str)

        return sorted(departures)

    except httpx.HTTPError as e:
        print(f"  ⚠️  Błąd rozkładu {busstop_id}/{busstop_nr} linia {line}: {e}")
        return []


def calculate_delay(now_local: datetime, departures: list[str]) -> float | None:
    """
    Oblicza opóźnienie w minutach.
    Szuka najbliższego rozkładowego odjazdu (w przeszłości lub przyszłości ±30 min).
    Zwraca różnicę w minutach (+ = spóźniony, - = przed czasem).
    Zwraca None jeśli brak danych.
    """
    if not departures:
        return None

    now_minutes = now_local.hour * 60 + now_local.minute

    best_diff = None
    for dep_str in departures:
        parts = dep_str.split(":")
        if len(parts) < 2:
            continue
        try:
            # ZTM używa godzin > 24 dla kursów po północy (np. "25:30:00")
            dep_h = int(parts[0])
            dep_m = int(parts[1])
            dep_minutes = dep_h * 60 + dep_m

            diff = now_minutes - dep_minutes  # + = my jesteśmy po rozkładzie
            if abs(diff) <= 30:
                if best_diff is None or abs(diff) < abs(best_diff):
                    best_diff = diff
        except ValueError:
            continue

    return best_diff


def find_nearest_stop(lat: float, lon: float, line: str) -> dict | None:
    """Znajduje najbliższy przystanek z naszej listy dla danej linii."""
    best = None
    best_dist = float("inf")
    for stop in STOPS:
        if line not in stop["lines"]:
            continue
        dist = haversine_km(lat, lon, CENTER_LAT, CENTER_LON)
        if dist < best_dist:
            best_dist = dist
            best = stop
    return best


def ensure_csv():
    """Tworzy plik CSV z nagłówkiem jeśli nie istnieje."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
        print(f"  📄 Utworzono nowy plik: {DATA_FILE}")


def append_rows(rows: list[dict]):
    """Dopisuje wiersze do CSV."""
    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writerows(rows)

# ─── GŁÓWNA LOGIKA ────────────────────────────────────────────────────────────

def collect():
    if not API_KEY:
        print("❌ Brak ZTM_API_KEY — ustaw zmienną środowiskową")
        sys.exit(1)

    now_utc    = datetime.now(timezone.utc)
    now_local  = now_utc.astimezone(WARSAW_TZ)
    ts_utc     = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    ts_local   = now_local.strftime("%Y-%m-%d %H:%M")

    print(f"\n🚌 Kolektor ZTM — {ts_local}")

    ensure_csv()

    new_rows = []
    total_vehicles = 0

    for vehicle_type in ("tram", "bus"):
        vehicles = fetch_vehicles(vehicle_type)
        print(f"  📡 {vehicle_type.upper()}: pobrano {len(vehicles)} pojazdów")

        for v in vehicles:
            dist = haversine_km(v["lat"], v["lon"], CENTER_LAT, CENTER_LON)

            # Interesują nas tylko pojazdy w pobliżu Kameralnej
            if dist > NEARBY_RADIUS_KM:
                continue

            total_vehicles += 1
            nearest_stop = find_nearest_stop(v["lat"], v["lon"], v["line"])

            # Pobierz rozkład i oblicz opóźnienie
            delay_min = None
            stop_name = ""
            stop_id   = ""

            if nearest_stop:
                stop_name = nearest_stop["name"]
                stop_id   = nearest_stop["busstopId"]
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

    if new_rows:
        append_rows(new_rows)
        print(f"  ✅ Zapisano {len(new_rows)} rekordów "
              f"({total_vehicles} pojazdów w pobliżu Kameralnej)")
    else:
        print("  ℹ️  Brak pojazdów w pobliżu Kameralnej w tej chwili")

    print(f"  📊 Łączny rozmiar CSV: "
          f"{DATA_FILE.stat().st_size / 1024:.1f} KB" if DATA_FILE.exists() else "")
    return len(new_rows)


if __name__ == "__main__":
    collect()
