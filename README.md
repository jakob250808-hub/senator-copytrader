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
Groß-/Kleinschreibung, Akzente und Satzpunkte in Namen werden normalisiert;
die Person selbst muss dennoch eindeutig der Quiver-Meldung entsprechen.

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

## Kostenloser lokaler Funktionstest

Vor dem Quiver-Abo kann die Verarbeitung mit der Beispielmeldung und der
fertigen `config.paper-demo.json` getestet werden:

```bash
senator-copytrader --config config.paper-demo.json bootstrap
senator-copytrader --config config.paper-demo.json run
```

Auch dabei zuerst `bootstrap` verwenden. Für einen simulierten neuen Eingang
anschließend eine weitere Meldung mit neuem `ReportDate` und Ticker in die
Beispieldatei einfügen.

## Grenzen des Tests

Politiker melden Trades erst nachträglich und nur in Wertspannen. Die
Software kopiert deshalb nicht den ursprünglichen Einstiegskurs oder die
wirkliche Positionsgröße. Quiver-Daten sollten stichprobenartig mit Capitol
Trades und bei wichtigen Fällen mit der offiziellen Senate-eFD-Meldung
verglichen werden. Das Projekt ist ein technischer Paper-Test und keine
Anlageempfehlung.
