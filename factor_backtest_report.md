# Momentum-/Qualitäts-Research-Backtest

Stand: 14.08.2026

## Ergebnis des ersten Forschungsbausteins

Der vorläufige, ungehebelte Lauf erzielt von 2015-01-02 bis 2026-06-30 insgesamt +104.12 %, entsprechend +6.41 % CAGR. Der maximale Drawdown liegt bei -33.07 %. SPY erzielt im selben Fenster +337.62 %.

Es wurden 138 monatliche Rebalances ausgeführt, davon 25 im Defensivmodus. Durchschnittlich waren 89744 USD investiert; der Umsatz betrug 10126798 USD und die modellierten Kosten 10127 USD.

Der fundamentale Qualitätsfaktor ist noch deaktiviert. Ohne eine Point-in-Time-Datei werden keine heutigen Fundamentaldaten rückwirkend eingesetzt.

**Research-Gate nicht bestanden:** Gefordert waren zunächst mindestens 25 % robuste ungehebelte CAGR bei höchstens 20 % Drawdown. Gemessen wurden +6.41 % CAGR und -33.07 % Drawdown. Dieser Baustein wird daher weder gehebelt noch in die Paper-Konfiguration übernommen.

## Jahresergebnisse

| Jahr | Rendite | Jahresendwert |
|---|---:|---:|
| 2015 | +0.50 % | 100504.79 USD |
| 2016 | -3.37 % | 97122.46 USD |
| 2017 | +13.45 % | 110189.46 USD |
| 2018 | -15.62 % | 92980.38 USD |
| 2019 | +4.57 % | 97229.99 USD |
| 2020 | +15.77 % | 112566.79 USD |
| 2021 | +5.16 % | 118378.05 USD |
| 2022 | -16.92 % | 98352.41 USD |
| 2023 | -3.85 % | 94565.99 USD |
| 2024 | +30.53 % | 123438.60 USD |
| 2025 | +10.36 % | 136230.30 USD |
| 2026 (Teiljahr bis 06-30) | +49.83 % | 204118.21 USD |

## Rollierende 5-Jahre-/1-Jahr-Prüfung

Die Regeln bleiben in allen Fenstern unverändert; das Fünfjahresfenster dient nur zur Diagnose und wählt keine nachträglich beste Variante.

| Testjahr | Training-CAGR | Training-DD | Test | Test-DD | SPY-Test |
|---|---:|---:|---:|---:|---:|
| 2020 | -0.56 % | -33.07 % | +15.00 % | -14.23 % | +17.60 % |
| 2021 | +2.68 % | -33.07 % | +4.06 % | -18.18 % | +28.11 % |
| 2022 | +3.90 % | -33.07 % | -17.54 % | -21.39 % | -18.49 % |
| 2023 | -2.38 % | -33.07 % | -2.88 % | -16.61 % | +25.41 % |
| 2024 | +0.72 % | -30.03 % | +31.71 % | -15.48 % | +25.59 % |
| 2025 | +4.75 % | -30.03 % | +9.29 % | -20.62 % | +16.94 % |
| 2026 | +3.68 % | -30.03 % | +47.06 % | -12.13 % | +9.37 % |

Über die 7 Testfenster sind 5 positiv und 3 schlagen SPY. Die unabhängig zusammengesetzte Testreihe ergibt +102.88 %. 2026 ist nur bis 30.06. enthalten.

## Kostenstress

| Kosten je Seite | CAGR | Gesamtrendite | Drawdown |
|---:|---:|---:|---:|
| 0.00 % | +7.28 % | +124.30 % | -32.87 % |
| 0.10 % | +6.41 % | +104.12 % | -33.07 % |
| 0.25 % | +5.11 % | +77.23 % | -35.49 % |
| 0.50 % | +2.98 % | +40.12 % | -41.94 % |

## Datenqualität und Aussagegrenze

Die historische S&P-500-Mitgliedschaft enthält im Testfenster 768 Ticker. Für 627 davon (81.6 %) waren beim kostenlosen Kursanbieter Daten verfügbar; 141 fehlten vollständig.

Der Mitgliedschaftsdatensatz ist ein MIT-lizenziertes, aus öffentlichen Änderungen rekonstruiertes Forschungsdataset am Commit `c31ac3cc56f28cf9a02b4e694eff7ceab596a0ff`. Er ist keine offizielle S&P-Datei. Yahoo-Daten decken insbesondere delistete oder umbenannte Titel nicht zuverlässig ab; dadurch bleibt Survivorship- und Delisting-Bias.

Dieser Lauf prüft daher Strategiecode, Look-ahead-Schutz, Kosten- und Risikomechanik. Er ist **kein Freigabesignal für 50–70 % Renditeziel oder Hebel**. Das nächste Gate verlangt vollständige Point-in-Time-Preise inklusive Delistings sowie Fundamentaldaten mit tatsächlichem Veröffentlichungsdatum.

## Feste Regeln – nicht nachträglich optimiert

- S&P-500-Mitgliedschaft am Signaltag, nicht heutige Mitglieder.
- Monatlicher Einstieg am nächsten Tages-Open.
- 12-zu-1-Momentum: 252 Handelstage Rückblick, letzte 21 ausgelassen.
- Nur Kurse ab 5 USD und durchschnittlich mindestens 10 Mio. USD Tagesumsatz.
- Höchstens 20 Titel, gleich gewichtet, maximal 10 % je Titel.
- Cash bei SPY unter seinem 200-Tage-Durchschnitt.
- Long-only, kein Hebel, keine Änderung der Senatoren-Paper-Config.
