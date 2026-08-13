# HANDOFF – Senator Copytrader

Koordinationsdatei für die gemeinsame Arbeit von Codex (Hauptimplementierung)
und Claude (Architektur-/Sicherheits-/Datenqualitäts-Review). Bitte vor jeder
Änderung zuerst diese Datei lesen und nach Abschluss eines Abschnitts hier
aktualisieren. Nicht gleichzeitig an derselben Datei arbeiten.

## Status (maschinenlesbar für die Automatisierung)

**Nächster Bearbeiter:** Codex

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

## 2026-08-14 – Codex: Einjahres-Backtest der 30er-Watchlist

**Bearbeiter:** Codex (direkter Nutzerauftrag)
**Status:** abgeschlossen für diesen Abschnitt

### Bearbeitete Dateien

- `src/senator_copytrader/portfolio_backtest.py` (limitgetreue Kontosimulation)
- `scripts/run_backtest_1y.py` (reproduzierbarer Einjahreslauf)
- `tests/test_portfolio_backtest.py` (Daten-/Limit-/Ausführungstests)
- `backtest_1y_results.csv` (Entscheidung je veröffentlichtem Signal)
- `backtest_1y_report.md` (Ergebnis, Benchmark und Grenzen)
- `README.md` (Aufruf und Einordnung)
- `HANDOFF.md` (Arbeitsprotokoll und Übergabe)

### Festgelegte Methodik vor Berechnung

- Zeitraum: 13.08.2025 bis 13.08.2026, ausschließlich anhand des
  Veröffentlichungs-/Filing-Datums; kein Einstieg am rückwirkenden Handelstag.
- Ausgangskapital 100.000 USD. Die vier Geldlimits aus `config.example.json`
  werden unverändert simuliert: 1.000 USD je Kauf, 3.000 USD je Position,
  20.000 USD Gesamtpositionen und 5.000 USD Käufe je Ausführungstag.
- Kauf/Verkauf am adjustierten Eröffnungskurs des nächsten SPY-Handelstags;
  0,10 % Kosten/Slippage je ausgeführter Seite. Verkäufe schließen wie der Bot
  die vollständige vorhandene Tickerposition; ohne Position kein Short.
- Offene Positionen werden am letzten verfügbaren Schlusskurs bewertet. Neben
  dem laufenden Kontowert wird ein hypothetischer Liquidationswert nach weiteren
  0,10 % ausgewiesen.
- Benchmark sowohl 100.000 USD SPY als auch fairer risikogedeckelter Vergleich
  80.000 USD Cash + 20.000 USD SPY. Cash wird ohne Zins gerechnet.
- Rohmeldungen: statische, offene Kadoa-Dateien aus dem Commit
  `e51eacba83bb0188aa687fa4e5576dcafd90907f` (Daily refresh 13.08.2026), die
  laut Projekt aus Senate eFD/House Clerk/OGE normalisiert werden. Kursquelle:
  Yahoo-Finance-Chart-API wie im bestehenden Backtest.

Der alte lokale Senate-Stock-Watcher-Datensatz endet 2021 und ist für diese
Aufgabe ungeeignet. Die neue Quelle wird nur im ignorierten `work/`-Ordner
gehalten; Commit, Fenster und jede verwendete Meldung werden im Bericht/CSV
festgehalten.

### Ergebnis

- Der deterministische Hauptlauf startet mit 100.000 USD und endet bei
  **105.920,35 USD (+5,92 %)**; nach hypothetischer Schlussliquidation bleiben
  105.900,27 USD (+5,90 %).
- 100.000 USD SPY steigen im selben Fenster nach dem identischen Einstiegskosten-
  Ansatz auf 121.832,92 USD (+21,83 %). Der risikogleichere Vergleich aus
  80.000 USD Cash + 20.000 USD SPY endet bei 104.366,58 USD (+4,37 %). Der
  Hauptlauf liegt damit +1,55 Prozentpunkte vor der risikogleichen Benchmark.
- Durchschnittlich waren 17.512,15 USD investiert. Maximaler Drawdown: −1,56 %.
  Umsatz: 51.843,46 USD aus 33.000 USD Käufen und 18.843,46 USD Verkäufen.
- Von 913 Watchlist-Zeilen wurden nur 49 ausgeführt (33 Käufe, 16 Verkäufe), 366
  fachlich gefiltert und 498 wegen Limits oder fehlender Position übersprungen.
  Die größten Bremsen waren 305 Nicht-Aktien, 329 Verkäufe ohne Position, 134
  Portfoliolimit- und 31 Tageslimit-Skips.
- Nur sechs Namen erzeugten ausgeführte Käufe: Boozman 19, King 5, Fetterman 3,
  Hickenlooper 3, Moran 2 und McConnell 1. McCormicks, Curtis', Scotts und viele
  von Fettermans Zeilen bestätigen als Anleihen/strukturierte Bestände den
  zuvor markierten Rauschverdacht.
- Die tickerweite Verkaufslogik vermischt Senatorensignale: Im Lauf schließt
  beispielsweise Tina Smith eine aus Morans Signal stammende BRK.B-Position und
  Tuberville eine aus Fettermans Signal stammende MSFT-Position.

### Robustheitsprüfung

Weil das Tageslimit bei Meldungsclustern die ersten fünf Käufe bevorzugt, wurden
200 deterministische Zufallsreihenfolgen (Seeds 0–199) gerechnet. Die Rendite
reicht von +0,85 % bis +11,68 %, Median +5,09 %, 5.–95. Perzentil
+2,76 % bis +8,17 %. Alle Läufe sind positiv, aber nur 62 % schlagen den
risikogleichen SPY-Mix. Der Hauptwert ist daher reihenfolgeabhängig.

Noch wichtiger: Die Watchlist wurde am Ende des Testfensters gerade anhand der
Aktivität desselben Jahres ausgewählt. Der Test ist deshalb in-sample und hat
Universums-Look-ahead. Das positive Ergebnis ist nützlich für die technische
Paper-Simulation, aber kein Beweis einer künftig kopierbaren Alpha.

### Tests und Prüfungen

```text
PYTHONPATH=src python3 -m unittest discover -s tests -v
Ran 41 tests in 0.029s – OK

PYTHONPYCACHEPREFIX=/tmp/senator_copytrader_pycache \
  PYTHONPATH=src python3 -m compileall -q src scripts tests
OK

python3 -m json.tool backtest_1y_summary.json
OK

Artefaktprüfung: 913 CSV-Zeilen, Status-/Grundsummen, Referenz-Endwert und
200 Sensitivitätsläufe konsistent

git diff --check
OK
```

Neu abgesichert sind: Filing- statt Transaktionsdatum, Tuberville-/McConnell-
Alias, fünf-von-sechs-Tageslimit, Positionslimit, vollständiges Schließen ohne
Short und Reihenfolgen-Sensitivität. Alle 35 zuvor vorhandenen Tests bleiben
grün.

### Nächste Aufgabe

Claude: Bitte Daten-/Methodikreview des Einjahreslaufs, besonders
Kadoa-Assetklassifikation, Ausführung zum nächsten Open, SPY-Benchmark,
Reihenfolgen-Sensitivität und Cross-Senator-Verkäufe. Vor höheren Geldlimits
sollten eine deterministische Signalpriorität und senatorbezogene Lots geklärt
werden. Für Strategienachweis die heutige Watchlist einfrieren und ausschließlich
ein künftiges Out-of-sample-Fenster bewerten.

## 2026-08-14 – Codex: Deterministische Exits + aggressiver C-Backtest

**Bearbeiter:** Codex (direkter Nutzerauftrag; deshalb trotz des auf Claude
stehenden Automatisierungsmarkers ausgeführt)
**Status:** abgeschlossen für diesen Abschnitt

### Bearbeitete Dateien

- `src/senator_copytrader/config.py` (optionale Exit-Felder und Validierung)
- `src/senator_copytrader/broker.py` (Alpaca-Positionswerte/offene Verkäufe)
- `src/senator_copytrader/engine.py` (unabhängige Exit-Prüfung und Vorschau)
- `src/senator_copytrader/storage.py` (Exit-Grund und lokale Haltedauer)
- `src/senator_copytrader/cli.py` (`planned_strategy_exits` im Dry-Run)
- `src/senator_copytrader/portfolio_backtest.py` (dieselben Regeln am Tages-Open)
- `scripts/run_backtest_1y.py` (Config-Exitfelder an Simulation weiterreichen)
- `scripts/run_backtest_1y_scenarios.py` (C-/Exit-Szenarienvergleich)
- `tests/test_config.py`, `tests/test_broker.py`, `tests/test_engine.py`,
  `tests/test_portfolio_backtest.py`
- `config.example.json`, `README.md`, `HANDOFF.md`
- `backtest_1y_aggressive_report.md`,
  `backtest_1y_aggressive_results.csv`,
  `backtest_1y_aggressive_summary.json`

### Exit-Regeln

Neue optionale Strategy-Felder:

- `stop_loss_pct`: Standard `None`/JSON `null`; gültig `0 < x <= 100`
- `take_profit_pct`: Standard `None`/JSON `null`; gültig `0 < x <= 1000`
- `max_holding_days`: Standard `None`/JSON `null`; gültig `1..3650`

Sind alle drei deaktiviert, wird nicht einmal die zusätzliche
Broker-Positionsabfrage ausgeführt; das bisherige Verhalten bleibt unverändert.
Bei Aktivierung läuft die Prüfung vor neuen Senatorensignalen und auch ohne neue
Meldung. Priorität bei gleichzeitig erfüllten Regeln: Stop-Loss, Take-Profit,
maximale Haltedauer. Alpaca liefert `avg_entry_price`, `current_price`,
`unrealized_plpc` und `market_value`; pro Ticker wird höchstens eine Regel
ausgeführt.

Die Haltedauer kommt aus SQLite: erster lokal als `submitted` gespeicherter Kauf
seit der letzten übermittelten vollständigen Schließung. Nur Ticker mit solchem
Bot-Kauf werden erfasst. Eine offene Verkaufsorder verhindert eine Doppelorder;
ein mechanisch geschlossener Ticker wird im selben Lauf weder durch Kauf- noch
Verkaufssignal doppelt verarbeitet. `events.action='risk_exit'` speichert
`exit_reason`, Einstiegstag, Kalendertage, Einstiegspreis, beobachteten Kurs,
Rendite, Brokerstatus und Order-ID. Wiederholungen desselben Tages aktualisieren
den deterministischen Exit-Datensatz statt ihn zu duplizieren.

Der normale Dry-Run zeigt diese Kandidaten als `planned_strategy_exits`, ohne
eine Order zu senden. Es sind Polling-Regeln, keine dauerhaft beim Broker
liegenden Stop-Orders: Zwischen zwei Läufen und bei Kurslücken ist die Schwelle
nicht als Ausführungspreis garantiert. Alpaca aggregiert außerdem manuelle und
Bot-Stücke desselben Tickers; deshalb bleibt ein separates Paperkonto nötig.
Order-Fills werden weiterhin nicht nachträglich reconciled; wie bei den
bisherigen Käufen/Verkäufen basiert die lokale Historie auf `submitted`.

### Aggressiver Einjahres-Backtest

Die Geldlimits in `config.example.json` wurden **nicht verändert**. Variante C
wird ausschließlich historisch gerechnet: 40.000 USD Portfoliolimit, 10.000 USD
Tageslimit, weiterhin 1.000 USD je Kauf und 3.000 USD je Ticker.

| Szenario | Rendite | Max. Drawdown | Ø investiert | Regel-Exits |
|---|---:|---:|---:|---:|
| bisher 20k/5k, Exits aus | +5,92 % | −1,56 % | 17.512 USD | 0 |
| C 40k/10k, Exits aus | **+9,93 %** | −2,57 % | 33.676 USD | 0 |
| C, Stop 12 %, 90 Tage | +3,36 % | −1,66 % | 23.530 USD | 74 |
| C, Stop 12 %, TP 25 %, 90 Tage | +1,45 % | −1,42 % | 21.877 USD | 77 |
| C, Stop 15 %, TP 30 %, 120 Tage | +2,12 % | −2,25 % | 26.268 USD | 66 |

Der primäre C-Lauf endet bei 109.925,00 USD; nach Schlussliquidation
109.884,18 USD (+9,88 %). Investitionsspitze 44.965 USD, Käufe 74.000 USD,
Umsatz 117.101,74 USD. Sein risikogleicher 40k-SPY-Mix erzielt +8,73 %, voller
SPY +21,83 %.

200 Reihenfolgen für C ohne Exits: Minimum +4,92 %, Median +9,72 %, Mittel
+9,63 %, P05–P95 +6,51 bis +12,76 %, Maximum +14,42 %; alle positiv, 69,5 %
über dem risikogleichen SPY-Mix. Höheres Kapital reduziert die Wirkung der
Burst-Skips, beseitigt sie aber nicht.

Alle drei getesteten Exit-Sets schneiden in diesem Fenster deutlich schlechter
ab. Sie recyceln Kapital und senken teilweise den Drawdown, realisieren aber die
wenigen starken Gewinner zu früh und steigern den Umsatz auf rund 278.000 bis
288.000 USD. Ergebnis: Mechanismus vorhanden, **keine Exit-Schwelle aktiviert**.
Eine nachträgliche Wahl des besten Schwellenwerts aus diesem In-sample-Jahr wäre
Overfitting.

### Tests und Prüfungen

```text
PYTHONPATH=src python3 -m unittest discover -s tests -v
Ran 55 tests in 0.046s – OK
```

Neu abgesichert: Stop-Loss, Take-Profit, maximale Haltedauer, deaktivierte
Rückwärtskompatibilität, Fremdticker-Schutz, kein sofortiger Wiedereinstieg,
orderfreie Vorschau, Alpaca-Positionsfelder, offene Verkaufsorder und
Budget-Recycling im Backtest. Der historische Rohdatencommit bleibt
`e51eacba83bb0188aa687fa4e5576dcafd90907f`.

### Nächste Aufgabe

Claude: Bitte Exit-/Storage-Review mit Fokus auf Alpaca-Orderzustände,
`submitted` versus tatsächlich gefüllt, SQLite-Migration/Upsert, aggregierte
Tickerpositionen und Polling-Gap-Risiko. Beim Backtest bitte besonders prüfen,
ob Exit-vor-Signal am adjustierten Open ohne Intraday-Hoch/Tief sauber und die
Schlussfolgerung „vorerst deaktiviert“ aus den fünf In-sample-Szenarien korrekt
begrenzt ist. Die Live-Geldlimits erst nach separater Nutzerfreigabe verändern.

## 2026-08-14 – Codex: Nutzerfreigabe für 3k-Kauf / 7k-Ticker

**Bearbeiter:** Codex (direkter Nutzerauftrag; zwei ausdrücklich genannte
Geldwerte trotz des auf Claude stehenden Automatisierungsmarkers geändert)
**Status:** abgeschlossen für diesen Abschnitt

### Geänderte Config

- `buy_notional_usd`: 1.000 → **3.000 USD**
- `max_position_usd`: 3.000 → **7.000 USD**
- `max_portfolio_usd`: unverändert **20.000 USD**
- `max_daily_notional_usd`: unverändert **5.000 USD**
- Exit-Felder: weiterhin `null`/deaktiviert
- `config.paper-demo.json`: unverändert klein

Die Schutzprüfung in `tests/test_watchlist.py` fixiert nun exakt diese vier
Werte. README und der reproduzierbare Einjahresbericht wurden angepasst. Die
alte aggressive 1k/3k-Szenarienmatrix bleibt im Skript absichtlich auf ihren
historischen Parametern eingefroren, damit ihr veröffentlichter Bericht trotz
der neuen Beispielconfig reproduzierbar bleibt.

### Kritischer Kapazitätseffekt

3.000 USD je Kauf passen nur einmal in das unveränderte Tageslimit von 5.000
USD. Zwei Käufe wären 6.000 USD und werden abgewiesen; 2.000 USD Tagesbudget
bleiben strukturell ungenutzt. Das 7.000-USD-Tickerlimit erlaubt zwei Käufe
(6.000 USD), aber keinen dritten. Das ist größer je ausgewähltem Signal, nicht
automatisch mehr Gesamtinvestition.

### Einjahres-Backtest des exakten Config-Stands

- Endwert 98.045,15 USD, Rendite **−1,95 %**; nach Liquidation −1,97 %
- Maximaler Drawdown −4,67 %
- Durchschnittlich nur 15.141,91 USD investiert, Spitze 20.067,83 USD
- 14 Käufe / 7 Verkäufe; 42.000 USD Kaufvolumen, 62.423,70 USD Umsatz
- 53 Tageslimit- und 135 Portfoliolimit-Skips
- 200 Reihenfolgen: Minimum −3,07 %, P05 −1,13 %, Median +3,48 %,
  Mittel +3,87 %, P95 +9,79 %, Maximum +15,57 %
- 83,5 % positiv, aber nur 42 % über dem risikogleichen SPY-Mix (+4,37 %)

Der deterministische Hauptlauf verschlechtert sich gegenüber dem früheren
1k/3k-Stand; die Rendite wird extrem reihenfolgeabhängig. Das Ziel von 7 % pro
Monat wird durch diese Änderung im Test nicht annähernd belegt.

### Nicht übernommene Zusatzszenarien

Zur Kapazitätseinordnung wurde dieselbe 3k/7k-Kombination read-only mit höheren
Gesamtlimits gerechnet; **keiner dieser Werte wurde in die Config übernommen**:

| Portfolio / Tag | Hauptlauf | Median aus 200 | P05–P95 | Max. Drawdown |
|---|---:|---:|---:|---:|
| 20k / 5k (Config) | −1,95 % | +3,48 % | −1,13 bis +9,79 % | −4,67 % |
| 40k / 10k | +14,35 % | +9,86 % | +4,05 bis +18,02 % | −3,32 % |
| 60k / 15k | +17,76 % | +15,27 % | +8,35 bis +24,51 % | −4,55 % |
| 80k / 20k | +16,63 % | +18,34 % | +10,75 bis +27,63 % | −7,32 % |
| 100k / 30k | +20,38 % | +26,36 % | +17,68 bis +34,80 % | −6,44 % |

Auch die aggressivste Zeile liegt im Hauptlauf weit unter den für 7 % monatlich
nötigen +125 % jährlich. Die breite Streuung zeigt zudem steigendes
Auswahl-/Konzentrationsrisiko statt einer nachgewiesenen stabilen Alpha.

### Tests

```text
PYTHONPATH=src python3 -m unittest discover -s tests -v
Ran 55 tests in 0.047s – OK

python3 scripts/run_backtest_1y.py
913 Signale; JSON/CSV konsistent
```

### Nächste Aufgabe

Claude: Bitte nur die ausdrücklich geänderten 3k-/7k-Werte und die
Backtest-Konsistenz reviewen. Portfolio-/Tageslimit nicht ohne neue
Nutzerfreigabe anheben. Besonders darauf hinweisen, dass 3k/5k nur einen Kauf
pro Tag zulässt und der Hauptlauf negativ ist.

## 2026-08-14 – Codex: Handoff für aggressivere Kapitalnutzung

**Bearbeiter:** Codex (Handoff für einen neuen Chat auf direkten
Nutzerwunsch)
**Status:** Handoff vorbereitet; Umsetzung ist die nächste Aufgabe

### Nutzerziel

Der Bot soll im Paper-Trading aggressiver handeln und deutlich mehr von den
100.000 USD Startkapital investieren. Das langfristige Wunschziel des Nutzers
sind 7 % pro Monat. Dieses Ziel ist eine Ambition, keine nachgewiesene oder zu
versprechende Rendite. Der neue Chat soll die Kapitalnutzung erhöhen und danach
ehrlich messen, welche Rendite und welches Risiko die Daten tatsächlich
zeigen.

### Verbindlicher Ausgangsstand

- 30-Senatoren-Watchlist bleibt bestehen.
- `buy_notional_usd`: **3.000 USD**
- `max_position_usd`: **7.000 USD**
- `max_portfolio_usd`: **20.000 USD**
- `max_daily_notional_usd`: **5.000 USD**
- Stop-Loss, Take-Profit und maximale Haltedauer sind implementiert, aber in
  `config.example.json` weiterhin deaktiviert (`null`).
- `config.paper-demo.json` bleibt klein und darf nicht aggressiv gemacht
  werden.
- Es wird ausschließlich mit vorhandenem Cash gearbeitet; keine Margin und
  keine Live-Trading-Freigabe.
- Aktueller Commit bei Erstellung dieses Handoffs: `e0db3b9`.

### Warum der aktuelle Stand nicht genügt

Mit 3.000 USD je Kauf und nur 5.000 USD Tageslimit passt lediglich ein Kauf in
einen Tag. Dadurch bleiben jeweils 2.000 USD Tagesbudget ungenutzt. Im exakten
Einjahres-Backtest wurden durchschnittlich nur 15.141,91 USD investiert; der
Hauptlauf lag bei **−1,95 %** und war stark von der Reihenfolge gleichzeitiger
Signale abhängig.

Read-only bereits getestete Orientierung mit unverändert 3.000 USD je Kauf und
7.000 USD je Ticker:

| Portfolio / Tag | Hauptlauf | Median aus 200 | P05–P95 | Max. Drawdown |
|---|---:|---:|---:|---:|
| 20k / 5k | −1,95 % | +3,48 % | −1,13 bis +9,79 % | −4,67 % |
| 40k / 10k | +14,35 % | +9,86 % | +4,05 bis +18,02 % | −3,32 % |
| 60k / 15k | +17,76 % | +15,27 % | +8,35 bis +24,51 % | −4,55 % |
| 80k / 20k | +16,63 % | +18,34 % | +10,75 bis +27,63 % | −7,32 % |
| 100k / 30k | +20,38 % | +26,36 % | +17,68 bis +34,80 % | −6,44 % |

Diese Tabelle ist keine Freigabe, einfach die renditestärkste Zeile zu
übernehmen. Sie zeigt vor allem, dass Portfolio- und Tageslimit die
Kapitalnutzung bremsen und dass die Ergebnisstreuung mit der Aggressivität
steigt.

### Nächste Aufgabe für Codex im neuen Chat

1. Zuerst `git pull`, diese Datei und den aktuellen Backtest-Code lesen. Den
   vorhandenen Stand nicht aus alten Chat-Zusammenfassungen rekonstruieren.
2. Die Investitionsbremsen quantitativ untersuchen: Tageslimit-,
   Portfoliolimit-, Tickerlimit- und Reihenfolge-Skips sowie durchschnittliche
   und maximale Kapitalbindung ausweisen.
3. Eine reproduzierbare Szenarienmatrix für eine **cash-only
   Paper-Konfiguration** rechnen. Mindestens die bereits getesteten
   40k/10k-, 60k/15k-, 80k/20k- und 100k/30k-Grenzen einbeziehen. Zusätzlich
   prüfen, ob 3k Kaufbetrag / 7k Tickerlimit sinnvoll ist oder ob eine andere
   Kombination das Tagesbudget sauberer ausnutzt. Keine Kombination darf mehr
   als 100.000 USD Startkapital als planmäßiges Portfolio-Limit verwenden.
4. Nicht nur die Jahresrendite optimieren. Je Szenario mindestens berichten:
   Hauptlauf, 200 Reihenfolgen (Minimum, P05, Median, P95, Maximum), maximaler
   Drawdown, durchschnittlich und maximal investiertes Kapital, Umsatz,
   Signal-Skips, Konzentration pro Senator/Ticker und Vergleich mit dem
   risikogleichen SPY-Mix.
5. Für das 7-%-Monatsziel die Renditen jedes einzelnen Kalendermonats zeigen:
   bester/schlechtester Monat, Median, Anzahl positiver Monate und Anzahl der
   Monate ≥ 7 %. Nicht aus einer Jahresrendite auf stabile Monatsrenditen
   schließen.
6. Slippage/Gebühren konservativ einrechnen oder mindestens als
   Sensitivität ausweisen. Wenn die vorhandenen Daten keinen echten
   Out-of-sample-Test erlauben, das klar als Grenze dokumentieren und keine
   Schwellen nachträglich auf dieses eine Jahr überoptimieren.
7. Danach die robusteste aggressivere Variante für **Paper-Trading** auswählen
   und in `config.example.json` umsetzen. Auswahlkriterium ist höhere,
   nachvollziehbare Kapitalnutzung bei vertretbarer Streuung und Drawdown –
   nicht bloß der höchste einzelne Backtestwert. Geldbeträge müssen logisch
   teilbar sein, damit nicht erneut strukturell Tagesbudget liegen bleibt.
8. Exit-Felder nicht gleichzeitig anhand desselben Jahres optimieren. Sie
   bleiben deaktiviert, sofern ein unabhängiger Test keinen belastbaren Vorteil
   zeigt. `config.paper-demo.json`, No-Margin-Schutz und doppelte
   Ausführungsfreigabe unverändert lassen.
9. Backtest-Artefakte, README und einen neuen Abschnitt in dieser Datei
   aktualisieren. Alle Tests ausführen, Ergebnisse samt Grenzen ehrlich
   dokumentieren, committen und auf `main` pushen.

### Abnahmekriterien

- Mehr Kapital wird nachweislich eingesetzt als die bisherigen durchschnittlich
  rund 15.000 USD; bloß höhere Einzelorders ohne höhere Gesamtauslastung gelten
  nicht als Erfolg.
- Kein Margin-Einsatz, kein Live-Trade und keine Änderung der kleinen
  Demo-Config.
- Das Ergebnis nennt sowohl Renditechance als auch Verlust-/Konzentrationsrisiko.
- 7 % pro Monat werden nur dann als erreicht bezeichnet, wenn die monatliche
  Auswertung das tatsächlich zeigt; ansonsten klar als nicht belegt markieren.
- Tests, Backtest und Dokumentation sind reproduzierbar und gemeinsam
  committed/gepusht.
