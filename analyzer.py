"""
analyzer.py
===========
Czyta ostatnie 24h z data/delays.csv, wysyła do Claude API
i zapisuje raport do reports/YYYY-MM-DD.md

Uruchamiany raz dziennie o 6:00 UTC (8:00 PL) przez GitHub Actions.

Wymagane zmienne środowiskowe:
  ANTHROPIC_API_KEY  — klucz z console.anthropic.com
"""

import os
import csv
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict
import httpx

# ─── KONFIGURACJA ─────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DATA_FILE         = Path(__file__).parent / "data" / "delays.csv"
REPORTS_DIR       = Path(__file__).parent / "reports"
WARSAW_TZ         = timezone(timedelta(hours=2))

# ─── CZYTANIE DANYCH ──────────────────────────────────────────────────────────

def load_last_24h() -> list[dict]:
    """Wczytuje rekordy z ostatnich 24 godzin."""
    if not DATA_FILE.exists():
        print("❌ Brak pliku data/delays.csv")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = []

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    rows.append(row)
            except (ValueError, KeyError):
                continue

    return rows


def summarize(rows: list[dict]) -> str:
    """
    Buduje zwięzłe podsumowanie danych do wysłania do Claude.
    Zamiast wysyłać tysiące surowych wierszy — agregujemy statystyki.
    Oszczędza tokeny i daje Claude lepsze dane do analizy.
    """
    if not rows:
        return "Brak danych z ostatnich 24 godzin."

    # Opóźnienia per linia per godzina
    by_line_hour: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    by_line: dict[str, list[float]] = defaultdict(list)
    total_with_delay = 0
    total = len(rows)

    for row in rows:
        line = row.get("line", "?")
        delay_str = row.get("delay_min", "")
        ts_local = row.get("timestamp_local", "")

        if delay_str and delay_str != "":
            try:
                delay = float(delay_str)
                by_line[line].append(delay)
                total_with_delay += 1

                # Wyciągnij godzinę z timestamp_local "YYYY-MM-DD HH:MM"
                hour = int(ts_local.split(" ")[1].split(":")[0]) if " " in ts_local else -1
                if hour >= 0:
                    by_line_hour[line][hour].append(delay)
            except ValueError:
                pass

    lines_summary = []
    for line, delays in sorted(by_line.items()):
        if not delays:
            continue
        avg = sum(delays) / len(delays)
        max_d = max(delays)
        late_count = sum(1 for d in delays if d > 2)
        late_pct = round(100 * late_count / len(delays))

        # Znajdź najgorsze godziny
        worst_hours = []
        if line in by_line_hour:
            hour_avgs = {
                h: sum(ds) / len(ds)
                for h, ds in by_line_hour[line].items()
                if len(ds) >= 2
            }
            worst = sorted(hour_avgs.items(), key=lambda x: x[1], reverse=True)[:3]
            worst_hours = [f"{h}:00 (śr. +{round(a, 1)} min)" for h, a in worst]

        lines_summary.append(
            f"Linia {line}: {len(delays)} obs., "
            f"śr. opóźnienie {round(avg, 1)} min, "
            f"maks. {round(max_d, 1)} min, "
            f"spóźnionych > 2 min: {late_pct}%"
            + (f", najgorsze godziny: {', '.join(worst_hours)}" if worst_hours else "")
        )

    # Ogólne statystyki godzinowe (wszystkie linie)
    hour_counts: dict[int, int] = defaultdict(int)
    for row in rows:
        ts_local = row.get("timestamp_local", "")
        if " " in ts_local:
            try:
                hour = int(ts_local.split(" ")[1].split(":")[0])
                hour_counts[hour] += 1
            except (ValueError, IndexError):
                pass

    busiest = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    busiest_str = ", ".join(f"{h}:00 ({c} obs.)" for h, c in sorted(busiest))

    summary = f"""DANE ZTM — OKOLICE KAMERALNEJ 3, WARSZAWA
Okres: ostatnie 24 godziny
Łącznie rekordów: {total}
Rekordów z danymi opóźnień: {total_with_delay}

STATYSTYKI PER LINIA:
{chr(10).join(lines_summary) if lines_summary else "Brak danych o opóźnieniach."}

AKTYWNOŚĆ PO GODZINACH (top 5):
{busiest_str if busiest_str else "Brak danych."}
"""
    return summary


# ─── WYWOŁANIE CLAUDE API ─────────────────────────────────────────────────────

def generate_report(summary: str, report_date: str) -> str:
    """Wysyła podsumowanie do Claude i zwraca raport w Markdown."""

    prompt = f"""Jesteś analitykiem komunikacji miejskiej. Poniżej masz dane zebrane przez 24 godziny
o opóźnieniach autobusów i tramwajów ZTM Warszawa w okolicach ul. Kameralnej 3 (Praga Północ).

{summary}

Napisz PRAKTYCZNY raport w Markdown dla mieszkańca tej ulicy. Raport ma zawierać:

1. **Podsumowanie dnia** — ogólna ocena punktualności komunikacji (2-3 zdania)
2. **Które linie działały najlepiej / najgorzej** — konkretne wnioski z danych
3. **Godziny szczytu problemów** — kiedy opóźnienia były największe
4. **Praktyczne wskazówki** — np. "Jeśli wyjeżdżasz o 8:00, weź pod uwagę X minut zapasu na linii Y"
5. **Trend** — czy dziś było lepiej/gorzej niż typowo (jeśli masz dane porównawcze)

Pisz po polsku, zwięźle, praktycznie. Nie przepisuj surowych danych — interpretuj je."""

    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "messages":   [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
        return f"# Raport ZTM — Kameralna 3 — {report_date}\n\n{content}"

    except httpx.HTTPError as e:
        print(f"  ⚠️  Błąd Claude API: {e}")
        # Fallback — raport bez AI, tylko surowe statystyki
        return f"# Raport ZTM — Kameralna 3 — {report_date}\n\n```\n{summary}\n```\n"


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def analyze():
    if not ANTHROPIC_API_KEY:
        print("❌ Brak ANTHROPIC_API_KEY")
        sys.exit(1)

    now_local   = datetime.now(WARSAW_TZ)
    report_date = now_local.strftime("%Y-%m-%d")

    print(f"\n📊 Analizator ZTM — {report_date}")

    rows = load_last_24h()
    print(f"  📂 Załadowano {len(rows)} rekordów z ostatnich 24h")

    if not rows:
        print("  ℹ️  Brak danych — pomijam analizę")
        return

    summary = summarize(rows)
    print(f"  🤖 Wysyłam podsumowanie do Claude ({len(summary)} znaków)...")

    report = generate_report(summary, report_date)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{report_date}.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"  ✅ Raport zapisany: {report_path}")
    print(f"\n--- PODGLĄD ---\n{report[:500]}...")


if __name__ == "__main__":
    analyze()
