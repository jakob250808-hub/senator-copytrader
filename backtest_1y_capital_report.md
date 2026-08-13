# Cash-only-Szenarien für aggressivere Kapitalnutzung

Stand: 14.08.2026

Zeitraum: 2025-08-13 bis 2026-08-13; Startkapital: 100.000 USD; keine Margin.

## Ergebnis und Auswahl

Ausgewählt wird für das Paper-Trading **2000 USD je Kauf, 6000 USD je Ticker, 60000 USD Portfolio- und 16000 USD Tageslimit**. Alle Geldbeträge sind durch den Kaufbetrag teilbar; damit passen 8 Käufe exakt in das Tagesbudget und 3 Käufe exakt in das Tickerlimit.

Der deterministische Lauf erzielt +13.95 %, über 200 Reihenfolgen liegt der Median bei +14.82 % und P05–P95 bei +9.53 bis +21.78 %. Der schlechteste Lauf liegt bei +6.96 %, der maximale Drawdown des Hauptlaufs bei -4.54 %.

Durchschnittlich sind 51362 USD statt zuvor 15142 USD investiert; die Spitze steigt von 20068 auf 67195 USD. Damit ist die geforderte höhere Kapitalnutzung tatsächlich erreicht.

Gegenüber der ähnlich ausgelasteten 3k/6k-Variante verbessert der kleinere Kaufbetrag den schlechtesten Reihenfolgenlauf von +3.82 auf +6.96 %, P05 von +7.89 auf +9.53 % und den schlimmsten Drawdown aus 200 Läufen von -12.59 auf -9.92 %. Das ist der Grund für die Auswahl; nicht der höchste einzelne Backtestwert.

Der risikogleiche SPY-Mix erzielt +13.10 %, voller SPY +21.83 %. Die gewählte Variante liegt im Hauptlauf +0.85 Prozentpunkte über dem risikogleichen Vergleich.

## Szenarienmatrix – Rendite und Risiko

| Szenario | Hauptlauf | Min | P05 | Median | P95 | Max | Drawdown | Risiko-SPY |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Ausgangsstand 3k/7k, 20k/5k | -1.95 % | -3.07 % | -1.13 % | +3.48 % | +9.79 % | +15.57 % | -4.67 % | +4.37 % |
| 3k/7k, 40k/10k | +14.35 % | -0.66 % | +4.05 % | +9.86 % | +18.02 % | +31.55 % | -3.32 % | +8.73 % |
| 3k/7k, 60k/15k | +17.76 % | +2.55 % | +8.35 % | +15.27 % | +24.51 % | +35.04 % | -4.55 % | +13.10 % |
| 3k/7k, 80k/20k | +16.63 % | +8.20 % | +10.75 % | +18.34 % | +27.63 % | +35.74 % | -7.32 % | +17.47 % |
| 3k/7k, 100k/30k | +20.38 % | +11.77 % | +17.68 % | +26.36 % | +34.80 % | +41.21 % | -6.44 % | +21.83 % |
| 2k/6k, 60k/16k | +13.95 % | +6.96 % | +9.53 % | +14.82 % | +21.78 % | +26.34 % | -4.54 % | +13.10 % |
| 2,5k/7,5k, 60k/15k | +14.19 % | +5.50 % | +7.88 % | +14.29 % | +22.70 % | +29.45 % | -5.10 % | +13.10 % |
| 3k/6k, 40k/12k | +15.70 % | +0.08 % | +4.57 % | +11.91 % | +19.82 % | +32.42 % | -4.39 % | +8.73 % |
| 3k/6k, 60k/15k | +17.75 % | +3.82 % | +7.89 % | +15.37 % | +24.86 % | +35.01 % | -4.57 % | +13.10 % |
| 3k/6k, 80k/24k | +19.08 % | +9.96 % | +12.52 % | +21.77 % | +30.49 % | +37.34 % | -7.36 % | +17.47 % |
| 3k/6k, 99k/30k | +21.83 % | +10.89 % | +18.14 % | +27.05 % | +35.94 % | +40.10 % | -7.16 % | +21.61 % |

## Kapitalbindung, Skips und Konzentration im Hauptlauf

| Szenario | Ø investiert | Spitze | Umsatz | Tageslimit | Portfolio | Ticker | Cash | Top-Senator | Top-Ticker |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Ausgangsstand 3k/7k, 20k/5k | 15142 USD | 20068 USD | 62424 USD | 53 | 135 | 0 | 0 | 42.9 % | 14.3 % |
| 3k/7k, 40k/10k | 34621 USD | 49215 USD | 113559 USD | 37 | 139 | 2 | 0 | 58.3 % | 8.3 % |
| 3k/7k, 60k/15k | 52536 USD | 70911 USD | 155530 USD | 31 | 132 | 6 | 0 | 57.6 % | 6.1 % |
| 3k/7k, 80k/20k | 67895 USD | 90075 USD | 199832 USD | 28 | 121 | 9 | 0 | 50.0 % | 4.5 % |
| 3k/7k, 100k/30k | 87022 USD | 110524 USD | 298364 USD | 19 | 111 | 9 | 0 | 57.1 % | 3.2 % |
| 2k/6k, 60k/16k | 51362 USD | 67195 USD | 181278 USD | 23 | 117 | 5 | 0 | 49.1 % | 5.3 % |
| 2,5k/7,5k, 60k/15k | 51748 USD | 68629 USD | 169289 USD | 28 | 127 | 4 | 0 | 60.5 % | 4.7 % |
| 3k/6k, 40k/12k | 35597 USD | 48871 USD | 101497 USD | 34 | 139 | 8 | 0 | 47.6 % | 9.5 % |
| 3k/6k, 60k/15k | 52654 USD | 70419 USD | 161501 USD | 30 | 123 | 15 | 0 | 58.8 % | 5.9 % |
| 3k/6k, 80k/24k | 69176 USD | 91167 USD | 237665 USD | 23 | 108 | 21 | 0 | 54.0 % | 4.0 % |
| 3k/6k, 99k/30k | 85372 USD | 110645 USD | 283678 USD | 19 | 101 | 22 | 0 | 48.3 % | 5.0 % |

## Monatsrenditen der gewählten Variante

| Monat | Monatsende | Rendite | Kontowert |
|---|---|---:|---:|
| 2025-08 | 2025-08-29 | +0.30 % | 100300.15 USD |
| 2025-09 | 2025-09-30 | +1.08 % | 101383.46 USD |
| 2025-10 | 2025-10-31 | +2.10 % | 103511.66 USD |
| 2025-11 | 2025-11-28 | -0.82 % | 102667.21 USD |
| 2025-12 | 2025-12-31 | -0.19 % | 102469.40 USD |
| 2026-01 | 2026-01-30 | +0.69 % | 103173.37 USD |
| 2026-02 | 2026-02-27 | -1.16 % | 101972.93 USD |
| 2026-03 | 2026-03-31 | -2.13 % | 99799.76 USD |
| 2026-04 | 2026-04-30 | +4.84 % | 104629.77 USD |
| 2026-05 | 2026-05-29 | +3.98 % | 108789.81 USD |
| 2026-06 | 2026-06-30 | +0.16 % | 108968.25 USD |
| 2026-07 | 2026-07-31 | +1.73 % | 110849.87 USD |
| 2026-08 | 2026-08-13 | +2.80 % | 113952.59 USD |

Bester Monat: 2026-04 mit +4.84 %; schlechtester Monat: 2026-03 mit -2.13 %. Median: +0.69 %. Positiv waren 9 von 13 Monaten, **mindestens 7 % erreichte 0 Monat(e)**. Der erste und letzte Monat sind wegen der Stichtage 13.08. nur Teilmonate. Das Ziel stabiler 7 % pro Monat ist damit nicht belegt.

## Kosten-/Slippage-Sensitivität der gewählten Variante

| Kosten je Seite | Rendite | Liquidationsrendite | Endwert |
|---:|---:|---:|---:|
| 0.00 % | +14.15 % | +14.15 % | 114148.08 USD |
| 0.10 % | +13.95 % | +13.89 % | 113952.59 USD |
| 0.25 % | +13.17 % | +13.02 % | 113171.52 USD |
| 0.50 % | +12.70 % | +12.40 % | 112700.35 USD |

## Konzentration der gewählten Variante

Ausgeführte Käufe nach den fünf größten Senatoren: John Boozman 28, Angus S. King Jr. 8, John Fetterman 6, John W. Hickenlooper 4, Sheldon Whitehouse 3.

Ausgeführte Käufe nach den fünf größten Tickern: MSFT 3, GOOGL 2, IEF 2, IEI 2, JMBS 2.

## Grenzen

- Die Watchlist wurde anhand desselben Jahres gewählt: Dieser Test ist in-sample und enthält Universums-Look-ahead.
- Die Variante wurde aus derselben Szenarienmatrix gewählt. Das ist kein unabhängiger Out-of-sample-Nachweis und keine Renditezusage.
- Gleichzeitige Signale bleiben reihenfolgeabhängig; deshalb stehen neben dem Hauptlauf 200 deterministische Zufallsreihenfolgen.
- Kadoa ist nicht der Live-Quiver-Feed. Tickerweite Verkäufe können Positionen schließen, die ein anderer Senator eröffnet hat.
- 0,10 % je Seite ist der Hauptfall; 0,25 % und 0,50 % je Seite zeigen konservativere Reibung. Steuern und Cashzins fehlen.
- Kosten können an einer harten Portfolio-Grenze ändern, welches nachfolgende Signal noch angenommen wird; die Sensitivität muss deshalb nicht streng monoton verlaufen.
- Stop-Loss, Take-Profit und Haltedauer bleiben deaktiviert; sie werden nicht noch einmal an diesem einen Jahr optimiert.
- Das Portfolio bleibt cash-only: maximal 100.000 USD planmäßiges Portfoliolimit, keine Margin und keine Live-Orders.

Die vollständigen Entscheidungen der gewählten Variante stehen in `backtest_1y_capital_results.csv`, alle Kennzahlen in `backtest_1y_capital_summary.json`.
