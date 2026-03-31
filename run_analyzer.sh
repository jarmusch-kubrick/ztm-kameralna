#!/bin/bash
# run_analyzer.sh
# Uruchamia analyzer.py i pushuje raport do GitHub
# Ustaw jako cron: 0 6 * * * /bin/bash /Users/TWOJE_KONTO/Projects/ztm-kameralna/run_analyzer.sh

REPO_DIR="/Users/jonasz/GitHub/ztm-kameralna"
ENV_FILE="$REPO_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
else
    echo "$(date): Brak pliku .env" >> "$REPO_DIR/cron.log"
    exit 1
fi

cd "$REPO_DIR" || exit 1

python3 analyzer.py >> "$REPO_DIR/cron.log" 2>&1

git add reports/
if git diff --staged --quiet; then
    echo "$(date): Brak nowego raportu" >> "$REPO_DIR/cron.log"
else
    DATE=$(date '+%Y-%m-%d')
    git commit -m "report: daily ZTM analysis ${DATE}" >> "$REPO_DIR/cron.log" 2>&1
    git push origin main >> "$REPO_DIR/cron.log" 2>&1
    echo "$(date): Raport wysłany" >> "$REPO_DIR/cron.log"
fi
