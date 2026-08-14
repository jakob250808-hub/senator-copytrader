# Strategie-Research: unabhängige Bausteine, ehrlich gemessen

Stand: 14.08.2026  ·  Engine: `research_backtest`

## Kurzfassung

Kein getesteter Baustein besteht das Research-Gate. Der wichtigste Befund ist methodisch, nicht strategisch: die bisher berichtete Momentum-CAGR hängt fast vollständig am Teiljahr 2026.

| Baustein | CAGR ohne 2026 | CAGR mit 2026-Teiljahr | Max DD | Vol | Sharpe | Calmar | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| 12-1 Momentum (Referenz, Bestandsstrategie) | +2.98 % | +6.57 % | -33.07 % | 19.72 % | 0.25 | 0.09 | nicht bestanden |
| Residualmomentum (marktbereinigt) | +4.16 % | +7.17 % | -27.93 % | 15.91 % | 0.33 | 0.15 | nicht bestanden |
| Residualmomentum mit 12-%-Volatilitätsziel | +2.22 % | +3.52 % | -27.86 % | 12.00 % | 0.24 | 0.08 | nicht bestanden |
| Kurzfristige Mean-Reversion (1 Woche, sehr liquide) | +2.68 % | +4.18 % | -34.15 % | 16.82 % | 0.24 | 0.08 | nicht bestanden |

Vergleich im selben Fenster ohne 2026: SPY +297.90 %. Ein volatilitätsgleicher SPY-Mix ist je Baustein einzeln ausgewiesen.

## Datenvertrag – was wirklich vorlag

| Anforderung | Status |
|---|---|
| Point-in-Time-Kurse inklusive delisteter Titel | **nein** |
| Finale Delisting-Auszahlungen | **nein** |
| Dauerhafte Security-IDs statt Ticker | **nein** |
| Fundamentaldaten mit Veröffentlichungsdatum | **nein** |
| Historische Analystenschätzungen/Revisionen | **nein** |
| Sektoren/Branchen zum damaligen Zeitpunkt | **nein** |
| Splits, Dividenden, Übernahmen vollständig | **nein** |

**Der Lauf ist damit ein Prototyp.** Kein Ergebnis dieses Berichts darf als publikationsreifer Alpha-Nachweis oder als Hebelfreigabe gelesen werden.

Fehlend für einen belastbaren Lauf:

- Kurse delisteter, übernommener und insolventer Titel (141 von 768 Tickern fehlen vollständig)
- Finale Delisting-Auszahlungen statt eines pauschalen Abschlags
- Dauerhafte Security-IDs (52 Ticker tragen mehr als ein Unternehmen)
- Fundamentaldaten mit tatsächlichem Veröffentlichungsdatum (Qualitätsfaktor)
- Quartalszahlen mit exaktem Announcement-Zeitpunkt (Earnings-Surprise/PEAD)
- Historische Analystenschätzungen und Revisionen
- Sektor-/Branchenzuordnung zum damaligen Zeitpunkt
- Senatorenmeldungen mit Veröffentlichungsdatum und Amendments über mehrere Jahre

## Identitätsprobleme im Universum

52 Ticker haben mehr als ein Mitgliedschaftsintervall, tragen also über die Zeit mehr als ein Unternehmen. Bei 19 Intervallen beginnt die heruntergeladene Kursreihe erst **nach** dem Ende des Intervalls — dort gehören die Kurse beweisbar zu einem anderen Emittenten.

## Kapitalnutzung, Umsatz und Kosten

| Baustein | Ø Exposure | Ø investiert | Spitze | Umsatz p.a. | Kosten (10 bp) |
|---|---:|---:|---:|---:|---:|
| 12-1 Momentum (Referenz, Bestandsstrategie) | 81.9 % | 88,219 USD | 143,990 USD | 8.2× | 9,571 USD |
| Residualmomentum (marktbereinigt) | 81.9 % | 96,420 USD | 161,422 USD | 9.0× | 11,605 USD |
| Residualmomentum mit 12-%-Volatilitätsziel | 65.5 % | 71,872 USD | 129,368 USD | 7.5× | 9,044 USD |
| Kurzfristige Mean-Reversion (1 Woche, sehr liquide) | 81.7 % | 82,713 USD | 145,172 USD | 68.0× | 75,258 USD |

## Kostenstress (ohne 2026-Teiljahr)

| Baustein | 0,00 % | 0,10 % | 0,25 % | 0,50 % |
|---|---:|---:|---:|---:|
| 12-1 Momentum (Referenz, Bestandsstrategie) | +3.83 % | +2.98 % | +1.73 % | -0.34 % |
| Residualmomentum (marktbereinigt) | +5.11 % | +4.16 % | +2.76 % | +0.47 % |
| Residualmomentum mit 12-%-Volatilitätsziel | +2.99 % | +2.22 % | +1.07 % | -0.83 % |
| Kurzfristige Mean-Reversion (1 Woche, sehr liquide) | +9.85 % | +2.68 % | -7.20 % | -21.60 % |

## Rollierende Walk-forward-Prüfung (5 Jahre Diagnose, 1 Jahr ungesehen)

Die Regeln sind in allen Fenstern identisch; im Trainingsfenster wird nichts angepasst. Es ist deshalb eine Stabilitätsprüfung, keine Optimierung.

### 12-1 Momentum (Referenz, Bestandsstrategie)

| Testjahr | Test | Test-DD | SPY | Training-CAGR |
|---|---:|---:|---:|---:|
| 2020 | +15.00 % | -14.23 % | +17.60 % | -0.56 % |
| 2021 | +5.28 % | -17.73 % | +28.11 % | +2.68 % |
| 2022 | -17.54 % | -21.39 % | -18.49 % | +4.14 % |
| 2023 | -2.88 % | -16.61 % | +25.41 % | -2.15 % |
| 2024 | +31.71 % | -15.48 % | +25.59 % | +0.95 % |
| 2025 | +9.57 % | -20.83 % | +16.94 % | +5.00 % |
| 2026 (Teiljahr) | +47.55 % | -12.17 % | +9.37 % | +3.98 % |

5 von 7 Testfenstern positiv, 3 schlagen SPY. Median der vollen Testjahre: +7.43 %.

### Residualmomentum (marktbereinigt)

| Testjahr | Test | Test-DD | SPY | Training-CAGR |
|---|---:|---:|---:|---:|
| 2020 | +19.71 % | -13.10 % | +17.60 % | +1.07 % |
| 2021 | +8.79 % | -15.05 % | +28.11 % | +5.19 % |
| 2022 | -18.80 % | -19.65 % | -18.49 % | +7.63 % |
| 2023 | -4.09 % | -13.67 % | +25.41 % | -1.18 % |
| 2024 | +27.61 % | -8.30 % | +25.59 % | +0.85 % |
| 2025 | +14.36 % | -11.26 % | +16.94 % | +5.17 % |
| 2026 (Teiljahr) | +39.07 % | -13.12 % | +9.37 % | +4.21 % |

5 von 7 Testfenstern positiv, 3 schlagen SPY. Median der vollen Testjahre: +11.58 %.

### Residualmomentum mit 12-%-Volatilitätsziel

| Testjahr | Test | Test-DD | SPY | Training-CAGR |
|---|---:|---:|---:|---:|
| 2020 | +3.98 % | -11.86 % | +17.60 % | +1.48 % |
| 2021 | +3.39 % | -9.44 % | +28.11 % | +2.46 % |
| 2022 | -13.48 % | -14.02 % | -18.49 % | +3.58 % |
| 2023 | -3.26 % | -12.02 % | +25.41 % | -3.56 % |
| 2024 | +20.96 % | -7.83 % | +25.59 % | -1.77 % |
| 2025 | +8.41 % | -8.02 % | +16.94 % | +1.58 % |
| 2026 (Teiljahr) | +16.11 % | -5.45 % | +9.37 % | +2.49 % |

5 von 7 Testfenstern positiv, 2 schlagen SPY. Median der vollen Testjahre: +3.69 %.

### Kurzfristige Mean-Reversion (1 Woche, sehr liquide)

| Testjahr | Test | Test-DD | SPY | Training-CAGR |
|---|---:|---:|---:|---:|
| 2020 | +24.46 % | -13.87 % | +17.60 % | -2.78 % |
| 2021 | +13.52 % | -11.36 % | +28.11 % | +7.93 % |
| 2022 | -11.88 % | -14.11 % | -18.49 % | +9.87 % |
| 2023 | +7.22 % | -14.78 % | +25.41 % | +3.12 % |
| 2024 | +7.17 % | -15.24 % | +25.59 % | +8.09 % |
| 2025 | +11.32 % | -14.95 % | +16.94 % | +7.38 % |
| 2026 (Teiljahr) | +21.31 % | -11.85 % | +9.37 % | +4.14 % |

6 von 7 Testfenstern positiv, 3 schlagen SPY. Median der vollen Testjahre: +9.27 %.

Achtung bei der Lesart: jedes Testfenster startet wieder mit 100.000 USD Cash. Der Median der Testjahre ist deshalb systematisch freundlicher als die durchgerechnete CAGR, weil Verlustjahre nicht in das Folgejahr hineinkompoundieren. Für die Gate-Entscheidung zählt die CAGR, nicht der Fenstermedian.

## Schlechteste Perioden (ohne 2026-Teiljahr)

| Baustein | schlechtestes Jahr | schlechtester Monat | rollierende 12M min | Anteil negativer 12M-Fenster | positive Jahre |
|---|---:|---:|---:|---:|---:|
| 12-1 Momentum (Referenz, Bestandsstrategie) | -16.92 % (2022) | -15.58 % (2018-10) | -28.32 % | 45.62 % | 7/11 |
| Residualmomentum (marktbereinigt) | -18.84 % (2022) | -10.20 % (2022-01) | -20.50 % | 46.38 % | 7/11 |
| Residualmomentum mit 12-%-Volatilitätsziel | -13.53 % (2022) | -9.87 % (2018-10) | -17.88 % | 48.65 % | 7/11 |
| Kurzfristige Mean-Reversion (1 Woche, sehr liquide) | -24.12 % (2015) | -14.40 % (2015-08) | -30.96 % | 40.41 % | 8/11 |

## Volatilitätsgleicher Vergleich

Statt eines pauschalen Cash/SPY-Mixes wird SPY je Baustein so skaliert, dass die realisierte Tagesvolatilität übereinstimmt. Es wird nie über 100 % investiert, damit der Vergleich zu einem Cash-only-Paperkonto passt.

| Baustein | Gewicht SPY | Rendite vol-gleich | Rendite Baustein |
|---|---:|---:|---:|
| 12-1 Momentum (Referenz, Bestandsstrategie) | 1.00 | +299.74 % | +38.18 % |
| Residualmomentum (marktbereinigt) | 0.89 | +250.93 % | +56.54 % |
| Residualmomentum mit 12-%-Volatilitätsziel | 0.67 | +164.50 % | +27.26 % |
| Kurzfristige Mean-Reversion (1 Woche, sehr liquide) | 0.95 | +273.86 % | +33.72 % |

## Konzentration

| Baustein | verschiedene Titel | größter Titel (Haltetage) | Sektor |
|---|---:|---:|---|
| 12-1 Momentum (Referenz, Bestandsstrategie) | 339 | 2.0 % | keine Point-in-Time-Sektordaten |
| Residualmomentum (marktbereinigt) | 400 | 1.2 % | keine Point-in-Time-Sektordaten |
| Residualmomentum mit 12-%-Volatilitätsziel | 400 | 1.2 % | keine Point-in-Time-Sektordaten |
| Kurzfristige Mean-Reversion (1 Woche, sehr liquide) | 296 | 1.4 % | keine Point-in-Time-Sektordaten |

## Korrelation der Bausteine (Tagesrenditen, ohne 2026)

| | B0_momentum_12_1 | B1_residual_momentum | B2_residual_momentum_vol_target | B3_short_term_reversal |
|---|---|---|---|---|
| B0_momentum_12_1 | 1.00 | 0.90 | 0.87 | 0.64 |
| B1_residual_momentum | 0.90 | 1.00 | 0.96 | 0.58 |
| B2_residual_momentum_vol_target | 0.87 | 0.96 | 1.00 | 0.58 |
| B3_short_term_reversal | 0.64 | 0.58 | 0.58 | 1.00 |

Kein Baustein hat das Gate bestanden. Eine Kombination wurde deshalb bewusst **nicht** gerechnet: eine schwache Strategie mit einer anderen zu mischen versteckt ihre Fehler, statt sie zu beheben.

## Gate-Auswertung im Detail

| Baustein | ≥25 % CAGR | DD ≤20 % | ≥60 % positive Jahre | nicht 1-Jahr-abhängig | hält 50 bp |
|---|---|---|---|---|---|
| 12-1 Momentum (Referenz, Bestandsstrategie) | nein | nein | ja | nein | nein |
| Residualmomentum (marktbereinigt) | nein | nein | ja | ja | nein |
| Residualmomentum mit 12-%-Volatilitätsziel | nein | nein | ja | nein | nein |
| Kurzfristige Mean-Reversion (1 Woche, sehr liquide) | nein | nein | ja | nein | nein |

## Bewertung aller geforderten Ideen vor der Implementierung

| Idee | Ökonomische Begründung | Datenbedarf | erwartete Korrelation zu G | Turnover | Overfitting-Risiko | im Paper-Bot umsetzbar | Entscheidung |
|---|---|---|---|---|---|---|---|
| Momentum + Qualität | stark (Novy-Marx) | **PIT-Fundamentals fehlen** | niedrig | mittel | mittel | ja | **verschoben** – Adapter steht, Daten fehlen |
| Residualmomentum | stark (Blitz et al.) | vorhanden | niedrig | mittel | niedrig (2 Parameter) | ja | **getestet** |
| Earnings Surprise / PEAD | stark (Bernard/Thomas) | Announcement-Zeitpunkt je Quartal | niedrig | hoch | niedrig | ja | **verschoben** – Quelle geprüft, Massenabruf offen |
| Analystenrevisionen | mittel | PIT-Schätzungen | niedrig | hoch | mittel | ja | **verworfen für jetzt** – Anbieterplan deckt Historie nicht ab |
| Kurzfristige Mean-Reversion | mittel (Liquiditätsprämie) | vorhanden | niedrig | **sehr hoch** | niedrig | grenzwertig (tägliche Orders) | **getestet** |
| Trend-/Regimefilter, Cashmodus | mittel | vorhanden | mittel | niedrig | niedrig | ja | **als Bestandteil aller Läufe aktiv** |
| Volatilitätssteuerung | mittel (Risiko, nicht Rendite) | vorhanden | – | niedrig | niedrig | ja | **als Overlay getestet** |
| Verbesserte Senatorensignale | schwach bis mittel | **Meldungshistorie über Jahre fehlt** | **hoch (identische Quelle)** | niedrig | hoch (viele Zuschnitte, wenige Ereignisse) | ja | **nicht backtestbar** – siehe unten |
| Gehebelte ETFs als Abkürzung | keine | – | – | – | – | – | **ausgeschlossen (Vorgabe)** |

## Warum die Senatorensignale hier nicht getestet wurden

Die Verbesserungsideen (Meldungsverzögerung, Kauf gegen Verkauf, Depoteigentümer, Ausschusszugehörigkeit zum damaligen Zeitpunkt, Clusterkäufe mehrerer Politiker, Wiederholungskäufe, historische Zuverlässigkeit je Person) brauchen alle **mehrere Jahre** Meldungen mit Veröffentlichungsdatum. Im Repository liegt der offene Kadoa-Auszug mit gut einem Jahr, die tagesaktuelle Datei enthält nur die letzten 5.000 Zeilen (rund zehn Wochen). Der Senats-Endpunkt des in dieser Session verbundenen Datenanbieters ist im aktuellen Tarif gesperrt; ein Kauf wurde vereinbarungsgemäß nicht getätigt. Jede Kennzahl aus einem Ein-Jahres-Fenster mit rund 57 ausgeführten Käufen und einer im selben Jahr ausgewählten Namensliste wäre Rauschen, das wie Alpha aussieht.

## Aussagegrenzen dieses Laufs

- Der Kurscache beginnt am 28.11.2013. **2008 ist nicht getestet.** Für 2006–2026 muss der Lauf mit `--start 2006-01-03` neu geladen werden; der Kursanbieter liefert dann allerdings weiterhin keine delisteten Titel.
- 2020 und 2022 sind enthalten und werden als eigene Testjahre ausgewiesen.
- Fehlende Kursreihen werden nicht ersetzt, sondern gezählt; die Strategie kann sie schlicht nie kaufen. Das verschiebt das Ergebnis systematisch nach oben, weil die fehlenden Titel überwiegend Übernahmen und Delistings sind.

## Was daraus folgt

- Kein Baustein wird gehebelt, in die Paper-Konfiguration übernommen oder mit einem anderen kombiniert.
- Das Ziel von 50–70 % pro Jahr ist mit diesen Signalen und dieser Datenlage nicht belegt und nach diesen Ergebnissen auch nicht plausibel.
- Der nächste sinnvolle Schritt ist Datenbeschaffung, nicht Strategiesuche: ohne delistete Kurse und Point-in-Time-Fundamentaldaten ist jede weitere Zahl ein Prototyp.
