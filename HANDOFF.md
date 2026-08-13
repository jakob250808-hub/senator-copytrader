# HANDOFF – Senator Copytrader

Koordinationsdatei für die gemeinsame Arbeit von Codex (Hauptimplementierung)
und Claude (Architektur-/Sicherheits-/Datenqualitäts-Review). Bitte vor jeder
Änderung zuerst diese Datei lesen und nach Abschluss eines Abschnitts hier
aktualisieren. Nicht gleichzeitig an derselben Datei arbeiten.

## Status (maschinenlesbar für die Automatisierung)

**Nächster Bearbeiter:** Claude

Regeln für beide Loops (lokaler Codex-Loop und Claudes geplante
Cloud-Aufgabe):

1. `git pull` (bzw. frisch klonen).
2. Diese Zeile lesen. Steht dort nicht der eigene Name, nichts tun und
   beenden (der andere ist dran oder es ist pausiert).
3. Steht `PAUSE` dort, nichts tun und beenden — der Mensch hat die
   Automatisierung angehalten.
4. Sonst: die unter "Nächste Aufgabe" im letzten Abschnitt beschriebene
   Arbeit erledigen, Tests laufen lassen, Ergebnis in einem neuen
   `## <Datum> – <Bearbeiter>`-Abschnitt dokumentieren (Format wie unten),
   diese Zeile auf den jeweils anderen Namen setzen, committen und pushen.

Zum Anhalten der Automatisierung diese Zeile manuell auf `PAUSE` setzen und
committen.

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

Update: Git-Repo wurde inzwischen von Claude lokal initialisiert (3 Commits,
siehe `git log`). Der GitHub-Remote wird vom Menschen eingerichtet.

Codex: Sobald der Remote steht, `git pull`, dann Beginn des echten
Veröffentlichungstag-Backtests auf Basis von
`work/senate-stock-watcher-data`. Bitte in einem neuen Abschnitt hier
eintragen, welche Dateien dafür angefasst werden, bevor mit der Arbeit
begonnen wird. Am Ende des Abschnitts **"Nächster Bearbeiter:" auf `Claude`
setzen**, damit die automatisierte Review-Runde greift.

## 2026-08-13 – Codex: Veröffentlichungstag-Backtest

**Bearbeiter:** Codex (Implementierung)
**Status:** abgeschlossen für diesen Abschnitt

### Bearbeitete Dateien

- `src/senator_copytrader/backtest.py` (reproduzierbare Backtest-Logik)
- `scripts/run_backtest.py` (lokaler, dokumentierter Aufruf)
- `tests/test_backtest.py` (Look-ahead-, Handelskalender- und Renditetests)
- `backtest_results.csv` (neu berechnete Einzelergebnisse)
- `backtest_report.md` (Methodik, Abdeckung, Ergebnisse und Grenzen)
- `README.md` (Backtest ausführen und Ergebnis einordnen)
- `HANDOFF.md` (Arbeitsprotokoll und Übergabe)
- `src/senator_copytrader/storage.py` (bei Gesamttest entdeckte Datumskorrektur)
- `src/senator_copytrader/engine.py` (Ausführungsdatum an Storage übergeben)

### Ziel dieses Abschnitts

Die tagesweisen Meldedateien liefern das tatsächliche Eingangsdatum. Signale
werden erst ab diesem Datum verwendet, am nächsten vorhandenen Handelstag mit
festem Dollarbetrag eröffnet, nach 90 Kalendertagen geschlossen und nach
0,20 % Kosten/Slippage mit einem zeitgleichen SPY-Investment verglichen.
Nicht-Aktien, nicht eindeutige Ticker und Signale ohne ausreichende Kursdaten
werden mit nachvollziehbarem Ausschlussgrund gezählt statt stillschweigend
verworfen.

### Umsetzung

- Die tagesweisen Archivdateien werden direkt gelesen; `date_recieved` ist der
  Signalzeitpunkt. Identische, mehrfach vorhandene PTR-Zeilen werden
  deterministisch dedupliziert.
- Einstieg: adjustierter Eröffnungskurs des nächsten SPY-Handelstags. Ausstieg:
  adjustierter Schlusskurs des ersten SPY-Handelstags mindestens 90
  Kalendertage später. Es werden 0,10 % Kosten je Seite berechnet.
- Der Kursabruf verwendet die Yahoo-Finance-Chart-API mit Retry/Backoff,
  parallelem Abruf und lokalem, datumsbereichsgebundenem Cache unter `work/`.
- Der Kursanbieter muss `EQUITY` oder `ETF` melden. Fehlende Ticker, Nicht-Aktien,
  Investmentfonds und unvollständige Kursfenster stehen mit Ausschlussgrund in
  `backtest_results.csv`.
- Der verwendete Rohdatenstand ist festgehalten:
  `384e08e84d809477cdfba7d52479147fbe5e6bd7`.
- Beim Gesamttest fiel ein bestehender Datumsfehler im Tagesbudget auf:
  `processed_at` verwendete immer das echte UTC-Datum statt des expliziten
  Ausführungsdatums. `engine.py` und `storage.py` speichern nun konsistent das
  übergebene Datum; der zuvor am Folgetag fehlschlagende Bestandstest ist wieder
  stabil.

### Ergebnisse

- 1.161 Käufe der Zielgruppe im Archiv, davon 780 grundsätzlich geeignete
  Aktienkäufe und 686 vollständig bewertbar (87,9 % der geeigneten Signale).
- Mittlere 90-Tage-Rendite: Strategie +5,506 %, zeitgleiches SPY +5,355 %;
  Differenz nur +0,151 Prozentpunkte.
- Median der Differenz −0,056 Prozentpunkte; exakt 343 von 686 Signalen (50,0 %)
  schlagen SPY. Fazit deshalb weiterhin: keine robuste Copytrading-Alpha.
- 74 geeignete Signale sind beim heutigen Kursanbieter per HTTP 400/404 nicht
  mehr auflösbar. Das betrifft häufig delistete/übernommene/umbenannte Titel und
  erzeugt mögliches Survivorship Bias; der Bericht kennzeichnet dies klar.
- Das Archiv endet 2021. Tuberville, Mullin und McCormick fehlen; Boozman hat 43
  Meldungen, aber keine maschinenlesbaren Transaktionen; Scotts Käufe sind keine
  Aktien. Nur fünf Personen liefern bewertete Signale.
- Die aus später bekannter Aktivität abgeleitete Zehnergruppe selbst hat
  Look-ahead-Bias. Der Bericht behauptet deshalb ausdrücklich keinen
  publikationsreifen Out-of-sample-Test.

### Tests und Prüfungen

```text
PYTHONPATH=src python3 -m unittest discover -s tests -v
Ran 31 tests in 0.030s – OK

PYTHONPYCACHEPREFIX=/tmp/senator_copytrader_pycache \
  PYTHONPATH=src python3 -m compileall -q src scripts tests
OK

git diff --check
OK
```

Zusätzlich geprüft: Die Ergebnisdatei enthält genau 1.161 Datenzeilen (686
`scored`, 475 `excluded`) und jede Zeile entspricht dem dokumentierten Schema.

### Offene Punkte / nächste Aufgabe

Claude: Bitte Architektur-, Datenqualitäts- und Methodik-Review dieses Backtests,
insbesondere Tickerextraktion/Deduplizierung, adjustierter Einstiegskurs,
SPY-Handelskalender, Kostenrechnung, HTTP-Ausschlüsse und die Aussagen im
Bericht. Fehler bitte klein korrigieren; ansonsten den nächsten sinnvollen
Implementierungsschritt an Codex übergeben. Inhaltlich wäre danach entweder eine
Point-in-time-Kursquelle inklusive delisteter Titel oder – falls keine verfügbar
ist – der noch offene Retry/Backoff-/Rate-Limit-Schutz für den laufenden
Paper-Bot sinnvoller als weitere Strategieoptimierung auf diesem verzerrten
Sample.
