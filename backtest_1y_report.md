# Einjahres-Backtest der 30er-Watchlist

Stand: 14. August 2026

Vollständiges Daten- und Marktfenster: 13. August 2025 bis 13. August 2026

## Kurzurteil

Die limitgetreue Simulation aus 100.000 USD endet bei **98.045,15 USD**, also
**−1,95 %**. Bei einer hypothetischen sofortigen Liquidation aller offenen
Positionen nach weiteren 0,10 % Kosten blieben **98.025,52 USD (−1,97 %)**.

Damit liegt der Lauf 6,32 Prozentpunkte hinter dem gleich stark
risikogedeckelten Vergleich aus 80.000 USD Cash und 20.000 USD SPY
(**104.366,58 USD; +4,37 %**). Gegen vollständig in SPY investierte 100.000 USD
(**121.832,92 USD; +21,83 %**) ist der Abstand noch größer. Durchschnittlich
waren nur 15.142 USD investiert.

Das Ergebnis ist **keine belastbare Alpha-Bestätigung**. Die Watchlist
wurde anhand genau dieses zurückliegenden Jahres ausgewählt und dann auf
demselben Jahr getestet (In-sample-/Universums-Look-ahead). Zudem entscheidet
bei Signalausbrüchen die nicht vertraglich festgelegte Feed-Reihenfolge, welche
Käufe innerhalb der Limits überhaupt ausgeführt werden.

## Kontosimulation

| Kennzahl | Ergebnis |
|---|---:|
| Startwert | 100.000,00 USD |
| Endwert, offene Positionen zum Schlusskurs bewertet | 98.045,15 USD |
| Hypothetischer Liquidationswert | 98.025,52 USD |
| Rendite | −1,95 % |
| Maximaler Drawdown | −4,67 % |
| Durchschnittlich investiert | 15.141,91 USD |
| Höchster Positionswert | 20.067,83 USD |
| Käufe | 42.000,00 USD |
| Verkaufserlöse | 20.423,70 USD |
| Umsatz im Jahr (Käufe + Verkäufe) | 62.423,70 USD |
| Ausgeführte Käufe / Verkäufe | 14 / 7 |
| Offene Ticker am Ende | 7 |

Der Positionswert durfte zeitweise über 20.000 USD steigen: Das Programm
blockiert neue Käufe oberhalb des Limits, verkauft aber bestehende Gewinne
nicht automatisch zurück auf 20.000 USD.

Die 14 ausgeführten Käufe stammen von sieben Namen:

| Senator | ausgeführte Käufe |
|---|---:|
| John Boozman | 6 |
| John W. Hickenlooper | 2 |
| Tommy Tuberville | 2 |
| Angus S. King Jr. | 1 |
| David McCormick | 1 |
| Jerry Moran | 1 |
| John Fetterman | 1 |

Die sieben offenen Positionen kosteten zusammen 21.000 USD und sind zum Ende
nur noch rund 19.621 USD wert. Allein INTU steht bei rund 1.618 USD auf 3.000
USD Einsatz. Geschlossene Positionen kosteten ebenfalls 21.000 USD und brachten
nur rund 20.424 USD ein. Größere Einzeltickets verstärken damit die Auswahl der
wenigen zuerst eintreffenden Signale, ohne mehr Kapital dauerhaft einzusetzen.

## Signalfluss und Grenzen

Die Quelle enthält 913 eindeutige Zeilen der 30er-Watchlist mit einem
Filing-Datum im Jahresfenster. Nur 21 führen zu einer Order:

| Ergebnis / Grund | Zeilen |
|---|---:|
| ausgeführt | 21 |
| herausgefiltert | 366 |
| übersprungen | 526 |
| davon Nicht-Aktien | 305 |
| davon ungültiger/fehlender Ticker | 53 |
| davon vom Kursanbieter als Fonds klassifiziert | 6 |
| davon Verkauf ohne vorhandene Position | 338 |
| davon Portfoliolimit | 135 |
| davon Tageslimit | 53 |
| davon Positionslimit | 0 |

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
Angus King gleichzeitig vor. Das Tageslimit von 5.000 USD erlaubt bei 3.000 USD
je Signal nur einen Kauf. Der deterministische Hauptlauf sortiert gleiche
Ausführungstage nach Filing- und Handelstag, Senator, Ticker und Event-ID; eine
andere API-Reihenfolge wählt andere Titel.

Zur Einordnung wurden dieselben Signale 200-mal mit zufälliger Reihenfolge
innerhalb der Ausführungstage simuliert:

| Kennzahl | Rendite |
|---|---:|
| Minimum | −3,07 % |
| 5. Perzentil | −1,13 % |
| Median | +3,48 % |
| Mittelwert | +3,87 % |
| 95. Perzentil | +9,79 % |
| Maximum | +15,57 % |
| Anteil positiver Läufe | 83,5 % |
| Anteil über risikogleichem SPY (+4,37 %) | 42 % |

Der Hauptwert von −1,95 % liegt innerhalb dieser extrem breiten Verteilung.
Die Kombination aus großem Einzelticket und unverändertem Tageslimit macht die
Rendite stärker von der Reihenfolge als von einer stabilen Signalauswahl abhängig.

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
5. Startkapital und Grenzen entsprechen der Config: 100.000 USD Cash, 3.000 USD
   je Kauf, 7.000 USD je Ticker, 20.000 USD Gesamtpositionen und 5.000 USD Käufe
   je Tag. Damit passt höchstens ein Kauf pro Tag durch. Ein Limit-Skip wird
   nicht später nachgeholt.
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

Der isolierte Sprung auf 3.000 USD je Signal und 7.000 USD je Ticker macht den
Bot mit den unveränderten 20.000-/5.000-USD-Grenzen nicht besser: Der Hauptlauf
ist negativ, durchschnittlich sinkt die Kapitalnutzung und die
Reihenfolgenabhängigkeit steigt. Für eine Investitionsentscheidung reicht der
In-sample-Test ohnehin nicht.

Ein passendes Tages-/Portfoliolimit muss separat freigegeben werden. Im
Zusatzvergleich erreicht dieselbe 3.000-/7.000-USD-Kombination bei 40.000 USD
Portfolio und 10.000 USD Tageslimit +14,35 %, bleibt aber ebenfalls stark
reihenfolgeabhängig. Technisch sollten gleichzeitige Signale deterministisch
priorisiert und Cross-Senator-Verkäufe getrennt behandelt werden.
