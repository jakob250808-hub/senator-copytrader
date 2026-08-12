#!/usr/bin/env bash
# Lokaler Automatisierungs-Loop fuer Codex.
#
# Voraussetzungen:
#   1. Codex CLI installiert und eingeloggt: `codex login`
#      (siehe README.md / HANDOFF.md fuer Details)
#   2. Dieses Repo hat einen Remote "origin", der auf das private
#      GitHub-Repo zeigt, und du bist dort per SSH oder gh-Login
#      angemeldet (git push muss ohne Passwortabfrage funktionieren).
#
# Start (im Terminal, im Projektordner):
#   bash scripts/codex_loop.sh
#
# Laeuft dauerhaft im Vordergrund. Zum Stoppen: Strg+C.
# Alternativ als Hintergrunddienst z. B. per `launchd` einrichten.
#
# Pausieren ohne den Loop zu beenden: in HANDOFF.md die Zeile
# "**Naechster Bearbeiter:**" auf "PAUSE" setzen und committen/pushen.

set -uo pipefail
cd "$(dirname "$0")/.."

INTERVAL_SECONDS="${CODEX_LOOP_INTERVAL:-300}"  # alle 5 Minuten pruefen

echo "Codex-Loop gestartet. Pruefe alle ${INTERVAL_SECONDS}s auf HANDOFF.md-Status."

while true; do
  if ! git pull --quiet origin main; then
    echo "$(date): git pull fehlgeschlagen, versuche es beim naechsten Mal erneut."
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  NEXT=$(grep -m1 '^\*\*Nächster Bearbeiter:\*\*' HANDOFF.md | sed 's/.*: *//' | tr -d '\r')

  if [ "$NEXT" = "Codex" ]; then
    echo "$(date): Codex ist dran, starte codex exec ..."
    codex exec --sandbox workspace-write "$(cat <<'PROMPT'
Lies HANDOFF.md komplett (im aktuellen Verzeichnis). Erledige die dort fuer
dich (Codex) vorgesehene naechste Aufgabe im Projekt 'senator_copytrader'.

Regeln, an die du dich halten musst:
- Dry-Run bleibt Standard; Live-Trading bleibt technisch ausgeschlossen
  (nur https://paper-api.alpaca.markets).
- Keine Geheimnisse (API-Keys) in Dateien, Logs, der SQLite-Datenbank oder
  Git speichern; nur ueber Umgebungsvariablen lesen.
- Kleine, nachvollziehbare Aenderungen. Nicht gleichzeitig an Dateien
  arbeiten, an denen laut HANDOFF.md gerade Claude arbeitet.
- Nach der Aenderung: `python -m unittest discover -s tests` ausfuehren
  und das Ergebnis dokumentieren.
- Dokumentiere dein Ergebnis in einem NEUEN Abschnitt am Ende von
  HANDOFF.md nach dem bestehenden Format (Datum, Bearbeiter, bearbeitete
  Dateien, erledigte Arbeit, Testergebnisse, offene Punkte, naechste
  Aufgabe fuer Claude).
- Setze am Ende die Zeile "**Naechster Bearbeiter:**" ganz oben in
  HANDOFF.md auf "Claude".
- Committe alle Aenderungen NICHT selbst (das macht dieses Skript danach).
PROMPT
)"

    git add -A
    if ! git diff --cached --quiet; then
      git commit -m "Codex-Automatisierungslauf: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
      git push origin main
      echo "$(date): Aenderungen committet und gepusht."
    else
      echo "$(date): Codex hat nichts geaendert."
    fi
  elif [ "$NEXT" = "PAUSE" ]; then
    echo "$(date): Automatisierung pausiert (HANDOFF.md sagt PAUSE)."
  else
    echo "$(date): nicht Codex' Zug (Status: '${NEXT:-unbekannt}'), warte."
  fi

  sleep "$INTERVAL_SECONDS"
done
