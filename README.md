# Senator Copytrader – Alpaca Paper MVP

Dieses Programm liest neu veröffentlichte Kongress-Transaktionen aus der
dokumentierten Quiver-API und bildet ausgewählte Senatoren ausschließlich in
einem Alpaca-Paperkonto nach.

Es gibt absichtlich keinen Live-Trading-Modus.

## Sicherheitsregeln

- Die Broker-Adresse ist fest auf `https://paper-api.alpaca.markets` gesetzt.
- Es gibt weder eine Live-Adresse noch einen Schalter für Live-Trading.
- Bestehende Meldungen werden beim ersten Start nur als Ausgangsbestand gespeichert.
- Es gibt **keine feste Obergrenze** wie "höchstens drei Orders" oder "höchstens
  100 USD". Stattdessen verarbeitet der Bot alle gültigen Tagesmeldungen, solange
  die folgenden konfigurierbaren Limits eingehalten werden (`strategy` in
  `config.json`):
  - `buy_notional_usd` – Betrag je einzelnem Kaufsignal (Standard: 1.000 USD).
  - `max_position_usd` – maximal investierter Betrag je Ticker.
  - `max_portfolio_usd` – maximal investierter Gesamtbetrag über alle Positionen.
  - `max_daily_notional_usd` – maximal an einem Kalendertag ausgegebener Betrag.
- Drei optionale, feste Exit-Regeln ergänzen Senatoren-Verkäufe und sind
  standardmäßig deaktiviert (`null`):
  - `stop_loss_pct` – vollständiges Schließen ab diesem Verlust seit Einstieg.
  - `take_profit_pct` – vollständiges Schließen ab diesem Gewinn seit Einstieg.
  - `max_holding_days` – vollständiges Schließen nach dieser Zahl Kalendertage.
- Die Haltedauer beginnt beim ersten lokal als `submitted` protokollierten Kauf
  der aktuell offenen Tickerposition und wird nach einer übermittelten
  vollständigen Schließung zurückgesetzt. Die Brokerposition muss beim Prüfen
  tatsächlich offen sein.
- Mechanische Exits laufen vor neuen Signalen und nur für Ticker, deren Kauf in
  der lokalen Bot-Historie steht. Ticker ohne lokalen Bot-Kauf werden nicht
  geschlossen. Manuell zum selben Ticker hinzugekaufte Stücke kann Alpaca in
  seiner aggregierten Position jedoch nicht trennen; deshalb gehört der Bot in
  ein separates Paperkonto. Bereits offene Verkaufsorders werden nicht
  verdoppelt; ein im selben Lauf geschlossener Ticker wird nicht sofort wieder
  gekauft.
- Fehlende oder unbekannte Assettypen werden nicht als Aktie erraten. Vor jeder
  Order muss Alpaca den Ticker außerdem als aktives, handelbares US-Wertpapier
  (`us_equity`) bestätigen; Krypto, Optionen und andere Assetklassen werden abgewiesen.
- Käufe werden **niemals über das verfügbare Paper-Cash hinaus** ausgeführt.
  Dafür wird bewusst `cash` und nicht `buying_power` von Alpaca geprüft, damit
  auch bei einem margin-fähigen Paperkonto nie auf Kredit gekauft wird.
- Verkäufe schließen nur eine vorhandene Paper-Position; es wird nie leerverkauft.
- Ohne `--execute-paper` ist jeder Lauf eine reine Vorschau.
- Eine echte Paper-Order benötigt zusätzlich `PAPER_TRADING_CONFIRM=YES`.

## Voraussetzungen

- Python 3.9 oder neuer
- Alpaca-Paperkonto und dessen Paper-API-Schlüssel
- Quiver-API-Schlüssel für die Congress-Trades-API

Für Alpaca ist keine zusätzliche Python-Bibliothek nötig.

Quiver bietet die passende API derzeit ab 30 USD pro Monat an. Für lokale
Tests kann stattdessen die beiliegende JSON-Beispieldatei verwendet werden.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp config.example.json config.json
```

Die Schlüssel nur in der aktuellen Shell setzen; niemals in `config.json`
oder Git speichern:

```bash
export QUIVER_API_KEY='...'
export ALPACA_API_KEY='...paper key...'
export ALPACA_SECRET_KEY='...paper secret...'
```

In `config.json` die Namen unter `politicians` sowie die Geld-, Positions- und
Portfoliolimits an das eigene Paperkonto (hier: rund 100.000 USD) anpassen.
`config.example.json` enthält die am 13.08.2026 geprüfte 30er-Watchlist. Nur
zwölf aktuell amtierende Senatoren erreichten in der verwendeten
Zwölfmonatsauswertung mindestens zehn Meldungen; die übrigen 18 sind deshalb
transparent als Beobachtungsgruppe nach jüngster und historischer Aktivität
ergänzt. Auswahl, Ausschlüsse und Rauschverdacht stehen in `HANDOFF.md`.

Groß-/Kleinschreibung, Akzente, Satzpunkte, Mittelinitialen, Titel, Suffixe und
die Schreibweise `Nachname, Vorname` werden für den Vergleich normalisiert; die
Person selbst muss dennoch eindeutig der Quiver-Meldung entsprechen.

Die größere Watchlist ändert keine Geldgrenze: Mit 1.000 USD je Kauf und 5.000
USD Tageslimit können höchstens fünf Käufe pro Tag eingereicht werden. Einen
zusätzlichen `max_orders_per_run`-Deckel gibt es nicht. Erreicht ein Signal ein
Geldlimit, wird es als `skipped` protokolliert und nicht für einen späteren Lauf
aufgehoben. Das ist bei Signalausbrüchen bewusst konservativ, kann aber Signale
verwerfen; vor einer Änderung der Limits ist eine ausdrückliche Entscheidung
nötig.

## Empfohlener Ablauf

1. Verbindung prüfen:

   ```bash
   senator-copytrader --config config.json check
   ```

2. Alle bereits vorhandenen Meldungen als Ausgangsbestand markieren. Dadurch
   werden beim ersten Lauf keine alten Käufe ausgelöst:

   ```bash
   senator-copytrader --config config.json bootstrap
   ```

3. Neue Aktionen nur anzeigen:

   ```bash
   senator-copytrader --config config.json run
   ```

   Bei aktivierten Exit-Feldern enthält die Vorschau zusätzlich
   `planned_strategy_exits`; dafür werden die aktuellen Paperpositionen gelesen,
   aber keine Orders gesendet.

4. Erst nach manueller Kontrolle bei Capitol Trades an das Paperkonto senden:

   ```bash
   export PAPER_TRADING_CONFIRM=YES
   senator-copytrader --config config.json run --execute-paper
   ```

5. Lokalen Zustand prüfen:

   ```bash
   senator-copytrader --config config.json status
   ```

Wenn die Senatorenliste in `config.json` geändert wird, verlangt das Programm
absichtlich einen neuen `bootstrap`-Lauf.

Für einen dauerhaften Test kann Schritt 3 beziehungsweise 4 während der
US-Handelszeiten alle 15 Minuten über einen Scheduler ausgeführt werden.
Stop-Loss und Take-Profit sind in dieser Umsetzung Polling-Regeln: Sie werden
nur bei einem Programmlauf geprüft. Kurslücken und Bewegungen zwischen zwei
Läufen können deshalb zu einem schlechteren Ausführungspreis als der
konfigurierten Schwelle führen.

## Kostenloser lokaler Funktionstest

Vor dem Quiver-Abo kann die Verarbeitung mit der Beispielmeldung und der
fertigen `config.paper-demo.json` getestet werden:

```bash
senator-copytrader --config config.paper-demo.json bootstrap
senator-copytrader --config config.paper-demo.json run
```

Auch dabei zuerst `bootstrap` verwenden. Für einen simulierten neuen Eingang
anschließend eine weitere Meldung mit neuem `ReportDate` und Ticker in die
Beispieldatei einfügen. Die Demo bleibt absichtlich bei Gary Peters: Sie prüft
kostenlos und deterministisch genau die mitgelieferte Beispielmeldung und soll
keine Live-Abdeckung vortäuschen.

## Historischer Veröffentlichungstag-Backtest

Der reproduzierbare Forschungs-Backtest verwendet den tatsächlichen Eingangstag
einer Senatsmeldung, kauft am nächsten SPY-Handelstag und verkauft nach 90
Kalendertagen. Pro Signal und für den zeitgleichen SPY-Vergleich gelten derselbe
Betrag von 1.000 USD sowie rund 0,20 % Kosten/Slippage. Er sendet keine Orders.

Das benötigte Offenlegungsarchiv wird unter
`work/senate-stock-watcher-data/data` erwartet. Der veröffentlichte Bericht
verwendet den Archivstand `384e08e84d809477cdfba7d52479147fbe5e6bd7`:

```bash
git clone https://github.com/timothycarambat/senate-stock-watcher-data.git \
  work/senate-stock-watcher-data
git -C work/senate-stock-watcher-data checkout \
  384e08e84d809477cdfba7d52479147fbe5e6bd7
```

Danach:

```bash
PYTHONPATH=src python3 scripts/run_backtest.py
```

Historische Kurse werden von Yahoo Finance geladen und nur im ignorierten
`work/`-Ordner zwischengespeichert. Die versionierte `backtest_results.csv`
enthält pro Kauf den Status, einen eventuellen Ausschlussgrund und bei bewerteten
Signalen die tatsächlich verwendeten Titel- und SPY-Preise. Methodik, Abdeckung,
Verzerrungen und Fazit stehen in `backtest_report.md`.

Der aktuelle Befund ist **keine Handelsempfehlung**: Der mittlere Vorsprung
gegen SPY ist sehr klein, der Median negativ, und fehlende historische Kurse
delisteter Titel können das Ergebnis verzerren.

## Einjahres-Kontosimulation der aktuellen Watchlist

Die aktuelle 30er-Watchlist kann zusätzlich als echtes, begrenztes
100.000-USD-Paperkonto über das letzte vollständige Datenjahr simuliert werden.
Anders als der unabhängige 90-Tage-Signaltest berücksichtigt dieser Lauf die
unveränderten Tages-, Positions- und Portfoliolimits sowie tickerweite
Verkaufssignale.

Benötigt wird der offene, statische Kadoa-Datensatz am dokumentierten Stand:

```bash
git clone --depth 1 https://github.com/kadoa-org/congress-trading-monitor.git \
  work/congress-trading-monitor
git -C work/congress-trading-monitor checkout \
  e51eacba83bb0188aa687fa4e5576dcafd90907f
PYTHONPATH=src python3 scripts/run_backtest_1y.py
```

Das Ergebnis steht in `backtest_1y_report.md`, die 913 Einzelentscheidungen in
`backtest_1y_results.csv` und die maschinenlesbare Zusammenfassung in
`backtest_1y_summary.json`. Der historische Kurscache bleibt unter `work/`
ignoriert.

Der Lauf ist bewusst als **in-sample** markiert: Die heutige Watchlist wurde
anhand desselben zurückliegenden Jahres ausgewählt. Außerdem kann bei mehr als
fünf gleichzeitigen Käufen die Feed-Reihenfolge die Rendite stark verändern.
Für einen belastbaren Nachweis muss die Liste jetzt eingefroren und ein neues,
zukünftiges Jahr abgewartet werden.

### Aggressiver Szenarienvergleich

Der zusätzliche Szenarienlauf vergleicht die bisherigen Grenzen mit Variante C
(40.000 USD Portfoliolimit, 10.000 USD Tageslimit) und drei festen Exit-Sets.
Die Live-Config und ihre Geldlimits werden dabei nicht verändert:

```bash
PYTHONPATH=src python3 scripts/run_backtest_1y_scenarios.py
```

Der Bericht steht in `backtest_1y_aggressive_report.md`, die vollständigen
Entscheidungen der primären C-Variante in
`backtest_1y_aggressive_results.csv` und alle Szenarien einschließlich je 200
Reihenfolgen in `backtest_1y_aggressive_summary.json`.

## Grenzen des Tests

Politiker melden Trades erst nachträglich und nur in Wertspannen. Die
Software kopiert deshalb nicht den ursprünglichen Einstiegskurs oder die
wirkliche Positionsgröße. Quiver-Daten sollten stichprobenartig mit Capitol
Trades und bei wichtigen Fällen mit der offiziellen Senate-eFD-Meldung
verglichen werden. Das Projekt ist ein technischer Paper-Test und keine
Anlageempfehlung.
