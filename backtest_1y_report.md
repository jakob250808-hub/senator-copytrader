# Einjahres-Backtest der 30er-Watchlist

Stand: 14. August 2026

Vollständiges Daten- und Marktfenster: 13. August 2025 bis 13. August 2026

## Kurzurteil

Die limitgetreue Simulation aus 100.000 USD endet bei **105.920,35 USD**, also
**+5,92 %**. Bei einer hypothetischen sofortigen Liquidation aller offenen
Positionen nach weiteren 0,10 % Kosten blieben **105.900,27 USD (+5,90 %)**.

Damit schlägt der Lauf den faireren, gleich stark risikogedeckelten Vergleich
aus 80.000 USD Cash und 20.000 USD SPY (**104.366,58 USD; +4,37 %**) um 1,55
Prozentpunkte. Gegen vollständig in SPY investierte 100.000 USD
(**121.832,92 USD; +21,83 %**) liegt er deutlich zurück. Das ist erwartbar,
weil im Copytrader durchschnittlich nur 17.512 USD investiert waren.

Das positive Ergebnis ist **keine belastbare Alpha-Bestätigung**. Die Watchlist
wurde anhand genau dieses zurückliegenden Jahres ausgewählt und dann auf
demselben Jahr getestet (In-sample-/Universums-Look-ahead). Zudem entscheidet
bei Signalausbrüchen die nicht vertraglich festgelegte Feed-Reihenfolge, welche
Käufe innerhalb der Limits überhaupt ausgeführt werden.

## Kontosimulation

| Kennzahl | Ergebnis |
|---|---:|
| Startwert | 100.000,00 USD |
| Endwert, offene Positionen zum Schlusskurs bewertet | 105.920,35 USD |
| Hypothetischer Liquidationswert | 105.900,27 USD |
| Rendite | +5,92 % |
| Maximaler Drawdown | −1,56 % |
| Durchschnittlich investiert | 17.512,15 USD |
| Höchster Positionswert | 23.637,16 USD |
| Käufe | 33.000,00 USD |
| Verkaufserlöse | 18.843,46 USD |
| Umsatz im Jahr (Käufe + Verkäufe) | 51.843,46 USD |
| Ausgeführte Käufe / Verkäufe | 33 / 16 |
| Offene Ticker am Ende | 14 |

Der Positionswert durfte zeitweise über 20.000 USD steigen: Das Programm
blockiert neue Käufe oberhalb des Limits, verkauft aber bestehende Gewinne
nicht automatisch zurück auf 20.000 USD.

Die 33 ausgeführten Käufe stammen nur von sechs Namen:

| Senator | ausgeführte Käufe |
|---|---:|
| John Boozman | 19 |
| Angus S. King Jr. | 5 |
| John Fetterman | 3 |
| John W. Hickenlooper | 3 |
| Jerry Moran | 2 |
| Mitch McConnell | 1 |

Die Schlussrendite wird stark von wenigen offenen Gewinnern getragen. Besonders
AMD steht bei rund 2.788 USD auf 1.000 USD Einsatz, NTAP bei rund 2.083 USD und
PANW bei rund 1.855 USD. INTU liegt dagegen nur noch bei rund 539 USD. Offene
Positionen enthalten zusammen etwa +5.077 USD unrealisierte Wertänderung;
geschlossene Positionen und Kauf-/Verkaufskosten erklären den übrigen Saldo.

## Signalfluss und Grenzen

Die Quelle enthält 913 eindeutige Zeilen der 30er-Watchlist mit einem
Filing-Datum im Jahresfenster. Nur 49 führen zu einer Order:

| Ergebnis / Grund | Zeilen |
|---|---:|
| ausgeführt | 49 |
| herausgefiltert | 366 |
| übersprungen | 498 |
| davon Nicht-Aktien | 305 |
| davon ungültiger/fehlender Ticker | 53 |
| davon vom Kursanbieter als Fonds klassifiziert | 6 |
| davon Verkauf ohne vorhandene Position | 329 |
| davon Portfoliolimit | 134 |
| davon Tageslimit | 31 |
| davon Positionslimit | 4 |

Das bestätigt den Rauschverdacht aus der Watchlist-Auswahl: McCormicks viele
Zeilen sind überwiegend Municipal Securities/strukturierte Bestände; Curtis,
Scott und Fetterman melden viele Anleihen. Sie werden vom Aktienbot korrekt
nicht gekauft.

Die aktuelle Verkaufslogik wirkt **tickerweit, nicht senatorbezogen**: Ein
Verkaufssignal irgendeines beobachteten Senators schließt die gesamte vorhandene
Position dieses Tickers. Im Lauf schließt beispielsweise Tina Smith eine zuvor
auf Jerry Morans Signal gekaufte BRK.B-Position; Tuberville schließt eine auf
Fettermans Signal eröffnete MSFT-Position. Das entspricht dem aktuellen Bot,
kann aber Signale verschiedener Personen unbeabsichtigt vermischen.

## Reihenfolgen-Sensitivität

Am 19. August 2025 liegen beispielsweise 21 grundsätzlich handelbare Käufe von
Angus King gleichzeitig vor, das Tageslimit erlaubt aber nur fünf. Der
deterministische Hauptlauf sortiert gleiche Ausführungstage nach Filing- und
Handelstag, Senator, Ticker und Event-ID. Dadurch werden unter anderem AMD und
ANET gekauft; eine andere API-Reihenfolge wählt andere Titel.

Zur Einordnung wurden dieselben Signale 200-mal mit zufälliger Reihenfolge
innerhalb der Ausführungstage simuliert:

| Kennzahl | Rendite |
|---|---:|
| Minimum | +0,85 % |
| 5. Perzentil | +2,76 % |
| Median | +5,09 % |
| Mittelwert | +5,22 % |
| 95. Perzentil | +8,17 % |
| Maximum | +11,68 % |
| Anteil positiver Läufe | 100 % |
| Anteil über risikogleichem SPY (+4,37 %) | 62 % |

Der Hauptwert von +5,92 % liegt innerhalb dieser breiten Verteilung. Die
Streuung ist zu groß, um die Differenz von +1,55 Punkten zum risikogleichen SPY
als robusten Strategievorteil zu behandeln.

## Methodik

1. Zeitraum ist das letzte in Quelle und Kursdaten vollständig abgeschlossene
   Jahr: 13.08.2025 bis 13.08.2026.
2. Es werden nur die 30 Namen aus `config.example.json` verwendet. Das
   Universum ist damit **nicht out-of-sample**.
3. Signalzeitpunkt ist ausschließlich `filing_date`. Der frühere
   Transaktionstag wird nie als Einstieg benutzt.
4. Kauf oder vollständiges Schließen erfolgt am adjustierten Eröffnungskurs des
   nächsten SPY-Handelstags. Meldungen ohne Uhrzeit werden so nicht rückwirkend
   am gleichen Tag gehandelt.
5. Startkapital und Grenzen entsprechen unverändert der Config: 100.000 USD
   Cash, 1.000 USD je Kauf, 3.000 USD je Ticker, 20.000 USD Gesamtpositionen und
   5.000 USD Käufe je Tag. Ein Limit-Skip wird nicht später nachgeholt.
6. Je ausgeführter Kauf-/Verkaufsseite werden 0,10 % Kosten/Slippage berechnet.
   Cash wird nicht verzinst; Bruchstücke von Aktien werden zugelassen.
7. Eindeutige Aktien und ETFs werden akzeptiert. Anleihen, strukturierte
   Produkte, Optionen, unklare Ticker und vom Kursanbieter erkannte Fonds werden
   verworfen.
8. Offene Positionen werden am letzten verfügbaren adjustierten Schlusskurs
   markiert. Steuern, Bid-Ask-Spreads über die pauschalen Kosten hinaus,
   Liquiditätsimpact und Verzinsung des Cashbestands fehlen.

## Datenqualität und Reproduzierbarkeit

Rohmeldungen stammen aus dem offenen Repository
`kadoa-org/congress-trading-monitor`, Commit
`e51eacba83bb0188aa687fa4e5576dcafd90907f` (Daily refresh 13.08.2026). Das
Projekt normalisiert öffentliche Senate-eFD-, House-Clerk- und OGE-Meldungen.
Die Simulation verwendet ausschließlich die filerbezogenen statischen Dateien;
die auf 5.000 Einträge gekürzte Dashboard-Datei wird nicht benutzt.

Kadoa ist nicht die Live-Quiver-API. Unterschiede bei Parsing, Assettyp,
Veröffentlichungszeitpunkt und Reihenfolge können das reale Paper-Ergebnis
verändern. Auffällig verspätete Meldungen werden trotzdem korrekt erst an ihrem
Filing-Tag berücksichtigt. Die Senate-eFD-Seite selbst stellt Meldungen ab 2012
bereit und weist auf die gesetzlichen Nutzungsbeschränkungen hin.

Einzelergebnisse stehen in `backtest_1y_results.csv`, die exakte Zusammenfassung
in `backtest_1y_summary.json`. Der Kurscache verbleibt unversioniert unter
`work/backtest_1y_prices.json`.

```bash
git clone --depth 1 https://github.com/kadoa-org/congress-trading-monitor.git \
  work/congress-trading-monitor
git -C work/congress-trading-monitor checkout \
  e51eacba83bb0188aa687fa4e5576dcafd90907f
PYTHONPATH=src python3 scripts/run_backtest_1y.py
```

## Fazit

Für den Paper-Test ist das Ergebnis ermutigend: positiver Jahresertrag, kleiner
Drawdown und im Hauptlauf ein Vorsprung gegenüber einem gleich riskierten
SPY-Mix. Für eine Investitionsentscheidung reicht es nicht. Der Test ist
in-sample, die Rendite hängt an wenigen Titeln und die Orderauswahl hängt stark
von Feed-Reihenfolge und Limits ab.

Der sinnvollste nächste Forschungslauf wäre eine **vorab eingefrorene**
Watchlist für die kommenden zwölf Monate. Technisch sollten außerdem
gleichzeitige Signale deterministisch priorisiert und Cross-Senator-Verkäufe
getrennt behandelt werden, bevor höhere Geldlimits überhaupt erwogen werden.
