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

## 2026-08-13 – Codex: 30er-Live-Watchlist nach Signalqualität

**Bearbeiter:** Codex (direkter Nutzerauftrag; deshalb trotz des noch auf Claude
stehenden Automatisierungsmarkers ausgeführt)
**Status:** abgeschlossen für diesen Abschnitt

### Bearbeitete Dateien

- `config.example.json` (30er-Live-Watchlist)
- `src/senator_copytrader/models.py` (robuster Namensabgleich)
- `tests/test_models.py` (Namensvarianten)
- `tests/test_watchlist.py` (30 Namen, Engine-Filter und unveränderte Limits)
- `README.md` (Watchlist-, Demo- und Kapazitätshinweise)
- `HANDOFF.md` (Auswahlbelege, Rauschverdacht und Übergabe)

`config.paper-demo.json` bleibt unverändert bei Gary Peters. Die kleine Config
ist ein kostenloser, deterministischer Funktionstest für
`examples/trades.sample.json`, keine simulierte Live-Watchlist.

### Quellen und Methodik (Stichtag 13.08.2026)

- Amtierender Status: offizielles
  [U.S.-Senatsregister](https://www.senate.gov/senators/index.htm?source=email).
  Jeder aufgenommene Name wurde dort einzeln gefunden. Dieses Register hat bei
  Konflikten Vorrang vor den teils verzögerten Drittanbieterprofilen.
- Zwölfmonatsaktivität und Tiebreak-Performance: öffentliche
  [Capitol-Markets-Senatsrangliste, 1Y](https://www.capitolmarkets.org/leaderboard?chamber=senate&sort=trades&tf=1Y),
  deren Forschungsseite die tägliche Aktualisierung aus öffentlichen Meldungen
  beschreibt. Gezählt wurden Käufe und Verkäufe, nicht Schlagzeilen.
- Eigentümer-/Asset-Plausibilisierung und historische Aktivität:
  [GovTrades Senate Stock Tracker](https://www.govtrades.com/senate-stock-tracker)
  sowie einzelne Quiver-Profile. Abweichende Zählweisen zwischen Aggregatoren
  sind der Grund, weshalb die Schwelle mit `~10` und nicht als vermeintlich
  exakte Wahrheit behandelt wird.
- Feedformat: Die
  [Quiver-API-Dokumentation](https://api.quiverquant.com/datasets/congress-trades)
  zeigt `Representative: "John Boozman"`; die lokale Fixture verwendet
  `Gary Peters`. Quiver-Profile zeigen daneben Mittelinitialen und Suffixe.

Wichtiger Befund: Die verlangte Schnittmenge aus „aktuell amtierend“ und
„mindestens ungefähr zehn Transaktionen im letzten Jahr“ enthält im
Capitol-Markets-Snapshot nur 13 Namen. Nach dem Ausschluss von Alan Armstrongs
extremem, nicht als wiederkehrendes Live-Muster belastbarem Einstandsblock
bleiben **zwölf Kernnamen**. Eine angeblich vollständig schwellenkonforme
30er-Liste wäre daher erfunden. Die Config enthält zwölf Kernnamen und 18 klar
gekennzeichnete Beobachtungsnamen. Die Reihenfolge folgt erst Aktivität, dann
Verwertbarkeit/Rauschprüfung und erst zuletzt der geschätzten Performance.
Bei den beiden gleich aktiven Kernnamen mit je zehn Meldungen lag Hickenloopers
1Y-Schätzung (13,6 %) vor Morans (4,2 %), daher steht Hickenlooper zuerst. Wo
bei gleicher Aktivität keine hinreichend bewerteten Börsenticker vorlagen, wurde
keine Scheingenauigkeit aus einer Einzelrendite erzeugt; dort entschieden
jüngere beziehungsweise umfangreichere historische Aktivität.

### Aufgenommene 30 Namen

| Rang | Quiver-kompatibler Config-Name | 1Y-Meldungen | Stufe / Datenqualität |
|---:|---|---:|---|
| 1 | John Boozman | 212 | Kern; sehr aktiv, überwiegend Gemeinschaftsdepot |
| 2 | David McCormick | 195 | Kern; **Rauschverdacht**, siehe unten |
| 3 | Shelley Moore Capito | 41 | Kern; **Rauschverdacht**, Ehepartnerdepot |
| 4 | Sheldon Whitehouse | 40 | Kern; jüngste Stichprobe mehrheitlich `Self` |
| 5 | Tommy Tuberville | 35 | Kern; **Rauschverdacht**, Gemeinschafts-/Beraterdepot |
| 6 | John Fetterman | 30 | Kern; **Rauschverdacht**, Kinder-/Familiendepot |
| 7 | John R. Curtis | 25 | Kern; noch kurze Historie, keine Rendite belastbar |
| 8 | Rick Scott | 16 | Kern; Self/Spouse gemischt, viele nicht direkt handelbare Assets |
| 9 | Angus S. King Jr. | 12 | Kern |
| 10 | Gary C. Peters | 11 | Kern; Feed-/Fixture-Namensfall explizit getestet |
| 11 | John W. Hickenlooper | 10 | Kern; jüngste Eigentümerstichprobe `Self`; bessere Performance-Tiebreak-Schätzung |
| 12 | Jerry Moran | 10 | Kern; Self/Spouse gemischt |
| 13 | Tina Smith | 9 | Beobachtung; knapp unter Schwelle, Ehepartnerhinweis |
| 14 | Bernie Moreno | 7 | Beobachtung; kurze Historie |
| 15 | Katie Boyd Britt | 7 | Beobachtung; kurze Historie |
| 16 | Mitch McConnell | 5 | Beobachtung; Ehepartnerdepot |
| 17 | Susan M. Collins | 4 | Beobachtung; Ehepartnerdepot, historisch häufig aktiv |
| 18 | Ron Wyden | <4 | Beobachtung; Startliste, 321 historische Meldungen |
| 19 | Ted Cruz | 1 | Beobachtung; Startliste, aktuell kein regelmäßiges Signal |
| 20 | Adam B. Schiff | 1 | Beobachtung; Ehepartner, kurze Senatshistorie |
| 21 | James Conley Justice II | 1 | Beobachtung; neue/kurze Senatshistorie |
| 22 | Bill Cassidy | 0 | Beobachtung; 208 historische Meldungen |
| 23 | Jack Reed | 0 | Beobachtung; 200+ historische Meldungen |
| 24 | Dan Sullivan | 0 | Beobachtung; 170 historische Meldungen |
| 25 | Patty Murray | 0 | Beobachtung; 161 historische Meldungen |
| 26 | John Hoeven | 0 | Beobachtung; Startliste, 149 historische Meldungen |
| 27 | Mark R. Warner | 0 | Beobachtung; 105 historische Meldungen |
| 28 | Thom Tillis | 0 | Beobachtung; 100 historische Meldungen |
| 29 | Ashley B. Moody | 0 | Beobachtung; 57 historische Meldungen, knapp außerhalb 1Y |
| 30 | Bill Hagerty | 0 | Beobachtung; 46 historische Meldungen |

`0` bedeutet hier: keine Transaktion im verwendeten gleitenden 1Y-Fenster,
nicht „noch nie gehandelt“. Diese Namen sind nur Reserve für eine erneute
Aktivitätsaufnahme. Die Beobachtungsgruppe sollte künftig regelmäßig neu
gerankt werden; sie ist keine Behauptung, dass alle 30 heute gleich starke
Signale liefern.

### Rauschverdacht und bewusste Ausschlüsse

- **David McCormick:** Quiver beschreibt zahlreiche jüngste Positionen als
  „Managed Structured Note Strategy“; im Gegencheck waren nur sehr wenige der
  vielen Meldungszeilen direkt tickerfähig. Wegen der außergewöhnlichen
  Aktivität in der Kernliste belassen, aber nicht als gleichwertiges
  selbstbestimmtes Signal interpretieren.
- **Shelley Moore Capito, Tommy Tuberville, John Fetterman, John Boozman:** Die
  jüngste Eigentümerstichprobe war überwiegend Spouse, Joint oder Child. Sie
  bleiben wegen regelmäßiger, zum Teil tickerfähiger Signale enthalten, sind
  aber gegenüber Whitehouse/Hickenlooper qualitativ abzuwerten.
- **Richard Blumenthal:** aktuell amtierend, aber ausgeschlossen. Der bekannte
  hohe 2025-Umsatz stammt weitgehend aus Ehepartner-/Trust-/Fonds- und privaten
  Gesellschaftspositionen; das ist Rebalancing-Rauschen statt sauberem
  Aktienauswahlsignal.
- **Alan Armstrong:** aktuell amtierend und im Roh-Ranking mit 703 Zeilen ganz
  oben, aber ausgeschlossen. Der Block konzentriert sich auf seinen Eintritt in
  den Senat und ist als einmalige Bestands-/Offenlegungswelle, nicht als
  wiederkehrendes Live-Handelsmuster, zu bewerten. Das ist eine aus Muster und
  Zeitpunkt abgeleitete Rauschklassifikation, keine Tatsachenbehauptung über
  seine Handelsabsicht.
- **Markwayne Mullin:** trotz teils noch als „Current“ markierter
  Drittanbieterprofile nicht aufgenommen; er fehlt im offiziellen Register am
  Stichtag. Dasselbe Amtierenden-Kriterium entfernt Kelly Loeffler, David
  Perdue, Pat Roberts, Thomas Carper und Richard Burr.
- **John Kennedy:** aktuell amtierend, aber mit nur einer Transaktion und damit
  trotz publizierter hoher Einzelrendite kein regelmäßiges Live-Signal.

### Namensformat und Tests

`normalize_person_name()` kann jetzt neben Satzpunkten/Akzenten auch
`Nachname, Vorname`, Titel, Suffixe und Mittelinitialen abgleichen. Damit werden
beispielsweise alle folgenden Paare gleich behandelt:

- `Gary Peters` (Fixture) ↔ `Gary C. Peters` (Config/Quiver-Profil)
- `Peters, Gary C.` ↔ `Gary C. Peters`
- `King, Angus S., Jr.` ↔ `Angus S. King Jr.`

`tests/test_watchlist.py` lädt die echte Beispielconfig, verlangt genau 30
verifizierte Namen, leitet für jeden eine Quiver-formatierte Meldung durch
`CopyEngine.selected_trades()` und fixiert zusätzlich alle vier Geldlimits auf
den vorgefundenen Werten. So schlägt der Test sowohl bei einem stillen
Namensfilterfehler als auch bei einer versehentlichen Limitänderung fehl.

### Kapazitätsprüfung – keine Limitänderung

- `buy_notional_usd = 1.000`, `max_position_usd = 3.000`,
  `max_portfolio_usd = 20.000` und `max_daily_notional_usd = 5.000` sind
  unverändert.
- `max_orders_per_run` existiert im aktuellen Modell nicht mehr; ein alter
  Config-Eintrag wird absichtlich ignoriert. Der vorhandene Test plant 75
  gültige Meldungen ohne technische Trunkierung. Dieser Teil passt also auch
  für 30 Senatoren.
- Das Tageslimit lässt höchstens **fünf neue Käufe pro Kalendertag** zu. Das
  Portfoliolimit reicht bei 1.000 USD je Eröffnung zunächst für höchstens 20
  gleich große Positionen, das Positionslimit für drei Käufe desselben Tickers
  (jeweils ohne zwischenzeitliche Kurswertänderungen gerechnet).
- Kritischer als die Höhe des Tageslimits: Ein wegen Tages-, Portfolio-,
  Positions- oder Cashlimit übersprungenes Signal wird als verarbeitet
  gespeichert und später **nicht erneut versucht**. Bei einem Meldungscluster
  kann die 30er-Liste daher mehr als fünf gültige Käufe liefern und der Rest
  dauerhaft entfallen.

Ergebnis: Kein technischer Orderdeckel muss geändert werden. Das Tageslimit ist
für einen konservativen Paper-Test vertretbar, aber nicht geeignet, wenn
ausnahmslos jedes Burst-Signal ausgeführt werden soll. Entsprechend
Nutzeranweisung wurden weder Limit noch Queue-Verhalten geändert. Vor einer
Erhöhung sollte entschieden werden, ob Kapazitäts-Skips zunächst mit Ablaufdatum
zurückgestellt werden sollen; das ist sicherer als blind mehr Tagesbudget
freizugeben.

### Tests und Prüfungen

```text
PYTHONPATH=src python3 -m unittest discover -s tests -v
Ran 35 tests in 0.028s – OK

PYTHONPYCACHEPREFIX=/tmp/senator_copytrader_pycache \
  PYTHONPATH=src python3 -m compileall -q src scripts tests
OK

git diff --check
OK
```

Zusätzlich per Test bestätigt: `config.example.json` enthält genau 30 Namen,
alle 30 passieren den Engine-Filter im dokumentierten Quiver-Format, die reale
Beispieldatei `Gary Peters` trifft `Gary C. Peters`, und die vier Geldlimits
haben exakt ihre vorherigen Werte. `config.paper-demo.json` ist unverändert.

### Nächste Aufgabe

Claude: Bitte die Watchlist-Auswahl und besonders die Rauschklassifikationen
gegen die aktuellen Rohmeldungen reviewen. Technisch bitte prüfen, ob
Limit-Skips wirklich endgültig verbraucht bleiben sollen oder ob eine kleine,
zeitlich begrenzte Pending-Queue der sinnvollere nächste Schritt ist. Geldlimits
nicht ohne Rücksprache ändern.
