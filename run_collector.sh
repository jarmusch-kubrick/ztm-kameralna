#!/bin/bash
# run_collector.sh
# Uruchamia collector.py i pushuje wyniki do GitHub
# Ustaw jako cron: */5 * * * * /bin/bash /Users/TWOJE_KONTO/Projects/ztm-kameralna/run_collector.sh

# ── KONFIGURACJA ──────────────────────────────────────────────────────────────
# Ścieżka do folderu repo (dostosuj do swojej lokalizacji)
REPO_DIR="/Users/jonasz/GitHub/ztm-kameralna"

# Plik z kluczami (nie wpisuj kluczy bezpośrednio tutaj)
ENV_FILE="$REPO_DIR/.env"

# ── ŁADOWANIE KLUCZY ──────────────────────────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
else
    echo "$(date): Brak pliku .env w $REPO_DIR" >> "$REPO_DIR/cron.log"
    exit 1
fi

# ── URUCHOMIENIE COLLECTORA ───────────────────────────────────────────────────
cd "$REPO_DIR" || exit 1

python3 collector.py >> "$REPO_DIR/cron.log" 2>&1
EXIT_CODE=$?

# ── PUSH DO GITHUB (tylko jeśli są nowe dane) ─────────────────────────────────
git add data/delays.csv

if git diff --staged --quiet; then
    echo "$(date): Brak nowych danych" >> "$REPO_DIR/cron.log"
else
    TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M UTC')
    git commit -m "data: collect ZTM delays ${TIMESTAMP}" >> "$REPO_DIR/cron.log" 2>&1
    git push origin main >> "$REPO_DIR/cron.log" 2>&1
    echo "$(date): Push zakończony" >> "$REPO_DIR/cron.log"
fi

exit $EXIT_CODE
