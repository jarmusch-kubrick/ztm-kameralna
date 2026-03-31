"""
analyzer.py
===========
Czyta ostatnie 24h z data/delays.csv, wysyła do Claude API,
generuje raport i zapisuje go do Notion + lokalnie jako .md

Uruchamiany raz dziennie o 6:00 UTC (8:00 PL) przez GitHub Actions.

Wymagane zmienne środowiskowe:
  ANTHROPIC_API_KEY  — klucz z console.anthropic.com
  NOTION_TOKEN       — klucz integracji Notion
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
NOTION_TOKEN      = os.environ.get("NOTION_TOKEN", "")

# ID bazy danych w Notion (data source)
NOTION_DATABASE_ID = "74a9ee68-bf48-4b64-b6ca-311a321ad209"

DATA_FILE    = Path(__file__).parent / "data" / "delays.csv"
REPORTS_DIR  = Path(__file__).parent / "reports"
WARSAW_TZ    = timezone(timedelta(hours=2))

# ─── CZYTANIE DANYCH ──────────────────────────────────────────────────────────

def load_last_24h() -> list[dict]:
    if not DATA_FILE.exists():
        print("❌ Brak pliku data/delays.csv")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = []

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    rows.append(row)
            except (ValueError, KeyError):
                continue

    return rows


def summarize(rows: list[dict]) -> tuple[str, dict]:
    """
    Zwraca (tekst podsumowania do Claude, słownik metadanych do Notion).
    """
    if not rows:
        return "Brak danych z ostatnich 24 godzin.", {}

    by_line: dict[str, list[float]]           = defaultdict(list)
    by_line_hour: dict[str, dict[int, list]]  = defaultdict(lambda: defaultdict(list))
    hour_counts: dict[int, int]               = defaultdict(int)

    for row in rows:
        line      = row.get("line", "?")
        delay_str = row.get("delay_min", "")
        ts_local  = row.get("timestamp_local", "")

        if delay_str:
            try:
                delay = float(delay_str)
                by_line[line].append(delay)
                if " " in ts_local:
                    h = int(ts_local.split(" ")[1].split(":")[0])
                    by_line_hour[line][h].append(delay)
                    hour_counts[h] += 1
            except ValueError:
                pass

    # Statystyki per linia
    lines_summary = []
    line_avgs     = {}

    for line, delays in sorted(by_line.items()):
        if not delays:
            continue
        avg       = sum(delays) / len(delays)
        max_d     = max(delays)
        late_pct  = round(100 * sum(1 for d in delays if d > 2) / len(delays))
        line_avgs[line] = avg

        worst_hours = []
        if line in by_line_hour:
            hour_avgs = {
                h: sum(ds) / len(ds)
                for h, ds in by_line_hour[line].items()
                if len(ds) >= 2
            }
            for h, a in sorted(hour_avgs.items(), key=lambda x: x[1], reverse=True)[:3]:
                worst_hours.append(f"{h}:00 (śr. +{round(a,1)} min)")

        lines_summary.append(
            f"Linia {line}: {len(delays)} obs., "
            f"śr. {round(avg,1)} min, maks. {round(max_d,1)} min, "
            f"spóźnionych >2min: {late_pct}%"
            + (f", najgorsze godz.: {', '.join(worst_hours)}" if worst_hours else "")
        )

    # Metadane do Notion
    all_delays = [d for delays in by_line.values() for d in delays]
    avg_global = round(sum(all_delays) / len(all_delays), 1) if all_delays else 0

    worst_line = max(line_avgs, key=line_avgs.get) if line_avgs else ""
    best_line  = min(line_avgs, key=line_avgs.get) if line_avgs else ""

    busiest = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    peak    = ", ".join(f"{h}:00" for h, _ in sorted(busiest))

    if avg_global <= 2:
        ocena = "🟢 Dobry"
    elif avg_global <= 4:
        ocena = "🟡 Średni"
    else:
        ocena = "🔴 Zły"

    meta = {
        "avg_delay":    avg_global,
        "worst_line":   worst_line,
        "best_line":    best_line,
        "observations": len(rows),
        "peak_hours":   peak,
        "ocena":        ocena,
    }

    busiest_str = ", ".join(f"{h}:00 ({c} obs.)" for h, c in sorted(busiest))
    summary_txt = f"""DANE ZTM — OKOLICE KAMERALNEJ 3
Okres: ostatnie 24h | Rekordów: {len(rows)}

STATYSTYKI PER LINIA:
{chr(10).join(lines_summary) if lines_summary else 'Brak danych.'}

AKTYWNOŚĆ PO GODZINACH: {busiest_str or 'Brak danych.'}
"""
    return summary_txt, meta


# ─── CLAUDE API ───────────────────────────────────────────────────────────────

def generate_report(summary: str, report_date: str) -> str:
    prompt = f"""Jesteś analitykiem komunikacji miejskiej. Poniżej dane o opóźnieniach
ZTM Warszawa w okolicach ul. Kameralnej 3 (Praga Północ) z ostatnich 24h.

{summary}

Napisz PRAKTYCZNY raport w Markdown dla mieszkańca tej ulicy:

1. **Podsumowanie dnia** — ogólna ocena punktualności (2-3 zdania)
2. **Najlepsza / najgorsza linia** — konkretne wnioski
3. **Godziny problemów** — kiedy było najgorzej
4. **Wskazówki na jutro** — np. weź X minut zapasu na linii Y o godzinie Z

Pisz po polsku, zwięźle i praktycznie."""

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
                "max_tokens": 1000,
                "messages":   [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    except httpx.HTTPError as e:
        print(f"  ⚠️  Błąd Claude API: {e}")
        return f"Błąd generowania raportu: {e}\n\n```\n{summary}\n```"


# ─── ZAPIS DO NOTION ──────────────────────────────────────────────────────────

def save_to_notion(report_date: str, meta: dict, report_text: str):
    if not NOTION_TOKEN:
        print("  ℹ️  Brak NOTION_TOKEN — pomijam zapis do Notion")
        return

    headers = {
        "Authorization":  f"Bearer {NOTION_TOKEN}",
        "Content-Type":   "application/json",
        "Notion-Version": "2022-06-28",
    }

    # Skróć raport do 2000 znaków (limit pola tekstowego Notion)
    raport_skrot = report_text[:1950] + "…" if len(report_text) > 1950 else report_text

    page = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Name": {
                "title": [{"text": {"content": f"Raport {report_date}"}}]
            },
            "Data": {
                "date": {"start": report_date}
            },
            "Ocena dnia": {
                "select": {"name": meta.get("ocena", "🟡 Średni")}
            },
            "Śr. opóźnienie (min)": {
                "number": meta.get("avg_delay", 0)
            },
            "Najgorsza linia": {
                "rich_text": [{"text": {"content": meta.get("worst_line", "")}}]
            },
            "Najlepsza linia": {
                "rich_text": [{"text": {"content": meta.get("best_line", "")}}]
            },
            "Liczba obserwacji": {
                "number": meta.get("observations", 0)
            },
            "Szczyt problemów": {
                "rich_text": [{"text": {"content": meta.get("peak_hours", "")}}]
            },
            "Raport": {
                "rich_text": [{"text": {"content": raport_skrot}}]
            },
        }
    }

    try:
        resp = httpx.post(
            "https://api.notion.com/v1/pages",
            headers=headers,
            json=page,
            timeout=15,
        )
        resp.raise_for_status()
        print(f"  ✅ Zapisano do Notion: Raport {report_date}")
    except httpx.HTTPError as e:
        print(f"  ⚠️  Błąd zapisu do Notion: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"      Szczegóły: {e.response.text[:300]}")


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

    summary_txt, meta = summarize(rows)
    print(f"  📈 Avg opóźnienie: {meta.get('avg_delay')} min | Ocena: {meta.get('ocena')}")
    print(f"  🤖 Generuję raport przez Claude...")

    report_text = generate_report(summary_txt, report_date)

    # Zapis lokalny (.md w repo)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{report_date}.md"
    full_report = f"# Raport ZTM — Kameralna 3 — {report_date}\n\n{report_text}"
    report_path.write_text(full_report, encoding="utf-8")
    print(f"  💾 Zapisano lokalnie: {report_path}")

    # Zapis do Notion
    save_to_notion(report_date, meta, report_text)


if __name__ == "__main__":
    analyze()
