# HANDOFF – Senator Copytrader

Koordinationsdatei für die gemeinsame Arbeit von Codex (Hauptimplementierung)
und Claude (Architektur-/Sicherheits-/Datenqualitäts-Review). Bitte vor jeder
Änderung zuerst diese Datei lesen und nach Abschluss eines Abschnitts hier
aktualisieren. Nicht gleichzeitig an derselben Datei arbeiten.

## 2026-08-12 – Claude: Bestandsaufnahme + erstes Sicherheits-/Limit-Review

**Bearbeiter:** Claude (Review + Korrekturen)
**Status:** abgeschlossen für diesen Abschnitt

### Bearbeitete Dateien

- `src/senator_copytrader/config.py`
- `src/senator_copytrader/broker.py`
- `src/senator_copytrader/engine.py`
- `src/senator_copytrader/storage.py`
- `tests/test_engine.py`
- `tests/test_broker.py`
- `tests/test_config.py`
- `config.example.json`
- `config.paper-demo.json`
- `README.md`
- `HANDOFF.md` (neu)

### Bestandsaufnahme (Ausgangslage vor dieser Änderung)

- Python-Paket, Alpaca-Paper-Anbindung, Quiver-/JSON-Provider, SQLite-Storage,
  Bootstrap, Dry-Run-Default, doppelte Freigabe (`--execute-paper` +
  `PAPER_TRADING_CONFIRM=YES`) waren bereits vorhanden und funktionsfähig.
- 11 bestehende Tests, alle grün. `bootstrap`/`run` mit `config.paper-demo.json`
  funktional geprüft (siehe Testergebnisse unten).
- **Kein Git-Repository im Projektwurzelverzeichnis.** `git status` schlägt mit
  "not a git repository" fehl. Für die verlangte Arbeitsweise ("kleine,
  nachvollziehbare Änderungen", Koordination über Diffs) sollte hier `git init`
  + Erstcommit erfolgen, bevor weitere Änderungen von Codex/Claude
  aufeinandertreffen. **Das habe ich bewusst nicht selbst gemacht**, um keine
  Entscheidung über Repo-Struktur/.gitignore-Historie vorwegzunehmen.
- `backtest_report.md` ist bereits korrekt als **Vorab-Analyse der
  Kadoa-Kennzahlen** gekennzeichnet, ausdrücklich **kein** Veröffentlichungstag-
  Backtest. Das ist ehrlich und sollte so bleiben, bis ein echter Backtest (ab
  Report-Datum, Kauf am Folgehandelstag, fester Betrag je Signal, Vergleich
  gegen SPY im selben Zeitfenster) existiert. Das ist noch offen (siehe unten).

### Gefundene Schwäche (Kernproblem) und Korrektur

**Problem:** `config.py` erzwang `max_orders_per_run` zwischen 1 und 10 und
Default 3 — ein fester, unbegründeter Deckel. Das widerspricht der
Anforderung "keine feste Begrenzung auf drei Trades oder 100 USD ... alle
gültigen Signale sollen verarbeitet werden, solange konfigurierbare Geld-,
Positions- und Portfoliolimits eingehalten werden". Es gab außerdem **keine**
Positions-, Portfolio- oder Tageslimit-Prüfung und **keine** Prüfung, ob genug
Paper-Cash vorhanden ist — bei vielen gleichzeitigen Signalen hätte der Bot
beliebig viele Käufe an Alpaca gesendet, im schlimmsten Fall über
`buying_power` (die bei einem margin-fähigen Paperkonto auch geliehenes
Kapital umfasst) hinaus.

**Korrektur:**

1. `max_orders_per_run` ist jetzt nur noch ein technisches Sicherheitsnetz
   (Default 50, Bereich 1–1000) gegen fehlerhafte Datenquellen, keine
   beabsichtigte Handelsgrenze mehr.
2. Neue Strategie-Felder: `max_position_usd`, `max_portfolio_usd`,
   `max_daily_notional_usd` (alle konfigurierbar, mit Konsistenzprüfung:
   `buy_notional_usd ≤ max_position_usd ≤ max_portfolio_usd`).
3. `buy_notional_usd`-Default von 25 auf **1.000 USD** angehoben
   (`config.example.json`), wie in der Aufgabenstellung verlangt. Die lokale
   Demo-Config (`config.paper-demo.json`) bleibt bei 25 USD mit
   proportional kleinen Limits, damit der kostenlose Funktionstest weiter
   ungefährlich bleibt.
4. `broker.py`: neue Methode `get_account_snapshot()` liefert `cash`,
   `portfolio_value`, `is_margin_account` und Positionswerte je Ticker. Für
   die Kaufgrenze wird **bewusst `cash` statt `buying_power`** verwendet —
   damit kann der Bot strukturell nie auf Margin kaufen, unabhängig davon,
   wie das Alpaca-Paperkonto konfiguriert ist.
5. `engine.py`: `execute()` prüft vor jedem Kauf in dieser Reihenfolge
   Cash-Deckung → Positionslimit → Portfoliolimit → Tageslimit und
   überspringt nur den einzelnen Trade (Status `skipped`, mit Begründung in
   der SQLite-Historie), statt den ganzen Lauf abzubrechen. Laufende Zähler
   werden innerhalb eines Laufs korrekt fortgeschrieben, damit mehrere Käufe
   im selben Lauf sich gegenseitig limitieren.
6. `storage.py`: `events`-Tabelle bekommt eine `notional_usd`-Spalte
   (Migration per `ALTER TABLE`, abwärtskompatibel zu bestehenden
   SQLite-Dateien) plus `daily_buy_notional(day)` für die Tageslimit-Prüfung.

### Testergebnisse

```
python -m unittest discover -s tests -v
...
Ran 21 tests in 0.068s
OK
```

11 bestehende Tests weiterhin grün, 10 neue Tests ergänzt:
- `test_no_fixed_cap_all_valid_signals_execute_within_money_limits` (beweist:
  mehr als drei gültige Tagessignale werden verarbeitet, solange Geldlimits
  reichen)
- `test_position_limit_skips_further_buys_of_same_ticker`
- `test_portfolio_limit_skips_buys_once_reached`
- `test_daily_limit_persists_across_runs_on_same_day`
- `test_never_buys_beyond_available_paper_cash_no_margin`
- `test_account_snapshot_uses_cash_not_buying_power`
- 4 neue Config-Validierungstests (u. a. `test_no_fixed_three_order_cap_higher_values_are_accepted`)

Zusätzlich manuell geprüft: `senator-copytrader --config config.paper-demo.json
bootstrap` und `run` liefern weiterhin das erwartete Ergebnis (1 Baseline-Event,
leerer Dry-Run-Plan, da das einzige passende Signal beim Bootstrap markiert
wurde).

**Nicht geprüft:** ein echter Lauf gegen die Alpaca-Paper-API (benötigt
`ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, die aus Sicherheitsgründen nicht in
dieser Session gesetzt wurden). Vor dem ersten echten `--execute-paper`-Lauf
bitte `check` mit echten Paper-Keys ausführen und `account.cash` sowie
`account.multiplier` im Alpaca-Dashboard stichprobenartig gegen
`get_account_snapshot()` prüfen.

### Offene Punkte für die nächste Aufgabe

1. **Kein Git-Repository.** Vor der nächsten gemeinsamen Änderung `git init`
   im Projektwurzelverzeichnis, `.gitignore` ist bereits vorhanden und deckt
   `.env`, `.venv/`, `__pycache__/`, `var/` ab. Danach Erstcommit mit dem
   aktuellen Stand (inklusive dieser Änderungen), damit künftige Diffs
   nachvollziehbar sind.
2. **Echter Veröffentlichungstag-Backtest fehlt noch.** `backtest_report.md`
   ist absichtlich nur eine ehrliche Vorab-Analyse. Für den "fertigen"
   Backtest (Signal am Report-Datum, Kauf am Folgehandelstag, fester Betrag
   je Signal, 0,20 % Kosten/Slippage, Verkauf/Haltefrist, Vergleich gegen SPY
   im selben Fenster) fehlen historische Tageskurse. Im Ordner
   `work/senate-stock-watcher-data` liegt bereits ein geklonter offener
   Datensatz — noch nicht in dieser Session ausgewertet, das ist der
   naheliegende nächste Schritt für Codex.
3. **Scheduler/Rate-Limits:** README empfiehlt einen 15-Minuten-Scheduler für
   Dauerbetrieb; weder Quiver- noch Alpaca-Rate-Limits werden aktuell
   behandelt (kein Backoff/Retry). Für Dauerbetrieb noch zu ergänzen.
4. **Kein CI-Workflow gefunden** (kein `.github/workflows`). Falls gewünscht,
   wäre ein einfacher Workflow sinnvoll, der bei jedem Push
   `python -m unittest discover -s tests` ausführt.
5. Die Alpaca-Account-Prüfung in `validate()` prüft aktuell nur
   `trading_blocked`, nicht explizit den Kontotyp. Das ist bewusst so belassen,
   weil die Cash-Ceiling-Logik in `engine.execute()` Margin bereits strukturell
   ausschließt — trotzdem könnte ein expliziter Hinweis/Log ("Margin-Konto
   erkannt, wird ignoriert") in `check` die Transparenz erhöhen.

### Nächste Aufgabe (Vorschlag)

Codex: `git init` + Erstcommit, danach Beginn des echten
Veröffentlichungstag-Backtests auf Basis von
`work/senate-stock-watcher-data`. Bitte in einem neuen Abschnitt hier
eintragen, welche Dateien dafür angefasst werden, bevor mit der Arbeit
begonnen wird.

## 2026-08-12 – Codex: Sicherheitsreview von Claudes Abschnitt

**Bearbeiter:** Codex
**Status:** Implementierung abgeschlossen; wartet auf Claude-Code-Review. Claude Code ist nicht aktiv (`claude auth status` meldet weiterhin nicht angemeldet)

### Verifizierter Ausgangsstand

- Claudes 21 Tests bestehen unverändert.
- Bytecode-Prüfung besteht mit einem temporären, erlaubten Cache-Pfad.
- Lokaler JSON-Dry-Run bleibt leer und sendet keine Order; SQLite zeigt eine Baseline-Meldung.

### Abgegrenzter Codex-Abschnitt

Codex bearbeitet ausschließlich:

- `src/senator_copytrader/config.py`
- `src/senator_copytrader/models.py`
- `src/senator_copytrader/engine.py`
- `src/senator_copytrader/broker.py`
- zugehörige Tests und Beispielkonfigurationen/Dokumentation

Ziele dieses Abschnitts:

1. den weiterhin festen `max_orders_per_run`-Signaldeckel vollständig entfernen;
2. Personen-, Ticker- und Assettyp-Normalisierung sicher machen, insbesondere fehlende/unbekannte Assettypen niemals implizit als Aktie zulassen;
3. vor jeder Paper-Order ausdrücklich ein aktives Alpaca-Asset der Klasse `us_equity` verlangen.

SQLite-Entscheidungsaudit und Backtest bleiben getrennte Folgeabschnitte.

### Umgesetzte Korrekturen

- `max_orders_per_run` vollständig aus Laufzeitmodell, Planung und Beispielkonfigurationen entfernt. Auch 75 passende Signale werden nicht abgeschnitten; ausschließlich Geld-, Positions-, Portfolio- und Cash-Limits begrenzen Käufe.
- Personenvergleich normalisiert Groß-/Kleinschreibung, Akzente und Satzzeichen; Ticker normalisieren unter anderem Dollar-Präfixe und die verbreitete Klassen-Notation `BRK/B` zu `BRK.B`.
- Assettypen werden konservativ auf `stock`, `etf` oder `unsupported` normalisiert. Fehlende oder unbekannte Typen werden nie mehr implizit als Aktie behandelt; unzulässige Konfigurationswerte werden abgewiesen.
- Kauf und Verkauf prüfen vor jedem Alpaca-Orderpfad `class=us_equity`, `status=active` und `tradable=true`; Käufe verlangen zusätzlich Teilorderfähigkeit.
- README und Beispielkonfigurationen an den tatsächlichen Stand angeglichen.

### Testergebnisse

- `PYTHONPATH=src python3 -m unittest discover -s tests -v`: 27/27 bestanden.
- Bytecode-Prüfung mit temporärem Cache: bestanden.
- Lokaler JSON-Dry-Run: keine geplante Aktion, keine Order; SQLite weiterhin eine Baseline-Meldung.
- Statische Endpunkt-/Schlüsselprüfung: einziger Alpaca-Broker-Endpunkt bleibt `https://paper-api.alpaca.markets`; Schlüssel werden nur aus Umgebungsvariablen gelesen.

### Übergabe an Claude Code

Claude Code soll diesen abgegrenzten Abschnitt prüfen und ausschließlich `HANDOFF.md` ergänzen. Fokus: konservative Normalisierung, Alpaca-Assetfelder, vollständige Entfernung des Signaldeckels und neue Tests. Danach Rückgabe an Codex für das SQLite-Entscheidungsaudit. Vorher muss die lokale Claude-Anmeldung vollständig abgeschlossen werden.
