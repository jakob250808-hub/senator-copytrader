# Einjahres-Kontosimulation der aktuellen Paper-Config

Stand: 14.08.2026

Zeitraum: 13.08.2025 bis 13.08.2026

## Kurzurteil

Die aktuelle Cash-only-Konfiguration mit 2.000 USD je Kauf, 6.000 USD je
Ticker, 60.000 USD Portfoliolimit und 16.000 USD Tageslimit endet bei
**113.952,59 USD (+13,95 %)**. Nach einer hypothetischen Schlussliquidation mit
weiteren 0,10 % Kosten verbleiben 113.891,92 USD (+13,89 %). Der maximale
Drawdown des Hauptlaufs beträgt **−4,54 %**.

Durchschnittlich waren 51.362,03 USD investiert, maximal 67.194,71 USD. Der
frühere 3k/7k/20k/5k-Stand band im gleichen Hauptlauf durchschnittlich nur
15.141,91 USD und erzielte −1,95 %. Die Kapitalnutzung wurde damit nachweislich
erhöht, ohne Margin zu simulieren.

Ein risikogleicher Vergleich aus 40.000 USD Cash und 60.000 USD SPY erzielt
+13,10 %, voller SPY +21,83 %. Die Strategie liegt im Hauptlauf 0,85
Prozentpunkte über dem risikogleichen Mix, aber klar unter vollständig
investiertem SPY.

## Ausführung und Limits

- Startkapital: 100.000 USD Cash; kein Kredit und kein Cashzins.
- Kauf: adjustierter Eröffnungskurs des nächsten SPY-Handelstags nach dem
  Filing-Datum; 0,10 % Kosten/Slippage je Seite.
- Verkauf: nächster Tages-Open, vollständige tickerweite Position; kein Short.
- Offene Positionen: letzter verfügbarer adjustierter Schlusskurs am 13.08.2026.
- Stop-Loss, Take-Profit und maximale Haltedauer: deaktiviert.

Von 913 Watchlist-Zeilen wurden 84 ausgeführt: 57 Käufe und 27 Verkäufe. 366
Zeilen wurden fachlich gefiltert und 463 übersprungen. Die Kapitalgrenzen
verhinderten 117 Käufe am Portfoliolimit, 23 am Tageslimit und 5 am
Tickerlimit; das Cashlimit wurde nie überschritten. Weitere 318 Verkäufe hatten
keine offene Position. Der Umsatz beträgt 181.278,15 USD, davon 114.000 USD
Käufe und 67.278,15 USD Verkaufserlöse.

## Reihenfolgen-Sensitivität

Für gleichzeitige Meldungen wurden 200 deterministische Zufallsreihenfolgen
(Seeds 0–199) simuliert:

| Kennzahl | Rendite |
|---|---:|
| Minimum | +6,96 % |
| P05 | +9,53 % |
| Median | +14,82 % |
| Mittel | +15,04 % |
| P95 | +21,78 % |
| Maximum | +26,34 % |

Alle 200 Läufe waren positiv; 68 % schlugen den risikogleichen SPY-Mix. Der
Median des maximalen Drawdowns lag bei −5,70 %, der schlechteste Drawdown über
alle Reihenfolgen bei −9,92 %. Das bleibt ein erhebliches Auswahlrisiko durch
die Feed-Reihenfolge.

## Monate und 7-%-Ziel

| Monat | Rendite |
|---|---:|
| 2025-08 (Teilmonat) | +0,30 % |
| 2025-09 | +1,08 % |
| 2025-10 | +2,10 % |
| 2025-11 | −0,82 % |
| 2025-12 | −0,19 % |
| 2026-01 | +0,69 % |
| 2026-02 | −1,16 % |
| 2026-03 | −2,13 % |
| 2026-04 | +4,84 % |
| 2026-05 | +3,98 % |
| 2026-06 | +0,16 % |
| 2026-07 | +1,73 % |
| 2026-08 (Teilmonat) | +2,80 % |

Neun von 13 Monaten waren positiv. Der Median beträgt +0,69 %, der beste Monat
+4,84 % und der schlechteste −2,13 %. **Kein Monat erreichte 7 %.** Das
langfristige Wunschziel von 7 % pro Monat ist in diesen Daten nicht belegt.

## Konzentration

John Boozman erzeugte 28 der 57 ausgeführten Käufe (49,1 %), Angus King 8 und
John Fetterman 6. Der größte einzelne Ticker, MSFT, erhielt 3 Käufe (5,3 %);
mehrere weitere Ticker erhielten je 2. Die Senatorenkonzentration bleibt damit
hoch, obwohl die Tickerverteilung breiter ist.

## Daten und Grenzen

Die Rohmeldungen stammen aus dem statischen Kadoa-Commit
`e51eacba83bb0188aa687fa4e5576dcafd90907f`; die Kursdaten kommen aus dem
lokalen, datumsgebundenen Yahoo-Chart-Cache. Die Watchlist wurde anhand
desselben zurückliegenden Jahres ausgewählt. Der Test ist deshalb **in-sample**
und enthält Universums-Look-ahead. Kadoa ist außerdem nicht der Live-Quiver-
Feed, und tickerweite Verkäufe können eine Position schließen, die ein anderer
Senator eröffnet hat.

Die robustere Limitkombination wurde ebenfalls auf diesem Jahr gewählt. Sie ist
eine begründete Paper-Konfiguration, kein Out-of-sample-Nachweis und keine
Renditezusage. Für einen belastbaren Strategienachweis muss die Watchlist jetzt
eingefroren und ein zukünftiges Fenster ausgewertet werden.

Die vollständige Kapitalmatrix, konservativere Kostenannahmen und die
Auswahlbegründung stehen in `backtest_1y_capital_report.md`. Alle 913
Einzelentscheidungen stehen in `backtest_1y_results.csv`, die maschinenlesbaren
Kennzahlen in `backtest_1y_summary.json`.
