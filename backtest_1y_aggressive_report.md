# Aggressiver Einjahres-Backtest – Variante C

Stand: 14.08.2026

Zeitraum: 2025-08-13 bis 2026-08-13

## Kurzurteil

Die verlangte Variante C investiert mit 40.000 USD Portfolio- und 10.000 USD Tageslimit aggressiver, lässt Kaufgröße (1.000 USD) und Tickerlimit (3.000 USD) aber unverändert. Ohne neue Exit-Regeln endet sie bei **109925.00 USD (+9.93 %)**; der maximale Drawdown beträgt **-2.57 %**.

Durchschnittlich waren 33675.75 USD investiert, maximal 44965.00 USD. Die Live-Config wurde nicht verändert; dies ist ausschließlich eine historische Paper-Simulation.

Der C-Hauptlauf liegt 1.19 Prozentpunkte über seinem risikogleichen 40.000-USD-SPY-Mix (+8.73 %), aber klar unter 100 % SPY (+21.83 %). Über 200 Signalreihenfolgen beträgt der Median +9.72 % und das 5.–95. Perzentil +6.51 bis +12.76 %.

## Szenarienvergleich

| Szenario | Rendite | Liquidation | Max. Drawdown | Ø investiert | Käufe | Regel-Exits | Reihenfolge P05–P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Aktuelle Limits, Exits aus | +5.92 % | +5.90 % | -1.56 % | 17512 USD | 33000 USD | 0 | +2.76 bis +8.17 % |
| C: 40k/10k, Exits aus | +9.93 % | +9.88 % | -2.57 % | 33676 USD | 74000 USD | 0 | +6.51 bis +12.76 % |
| C: SL 12 %, Haltedauer 90 Tage | +3.36 % | +3.34 % | -1.66 % | 23530 USD | 153000 USD | 74 | +1.77 bis +4.04 % |
| C: SL 12 %, TP 25 %, 90 Tage | +1.45 % | +1.43 % | -1.42 % | 21877 USD | 153000 USD | 77 | +0.11 bis +2.24 % |
| C: SL 15 %, TP 30 %, 120 Tage | +2.12 % | +2.10 % | -2.25 % | 26268 USD | 149000 USD | 66 | +0.90 bis +3.39 % |

## Einordnung der Exit-Regeln

Die Exit-Schwellen sind Forschungsvarianten, keine nachträglich gewählten Live-Parameter. Stop-Loss, Take-Profit und maximale Haltedauer werden im Backtest am adjustierten Open jedes Handelstags vor neuen Signalen geprüft. Intraday-Auslösungen und exakte Stop-Preise lassen sich mit Tagesdaten nicht simulieren.

Alle neuen Config-Felder bleiben standardmäßig `null`. Ein Take-Profit kann starke Gewinner abschneiden; eine maximale Haltedauer kann dagegen gebundenes Kapital freigeben. Deshalb wird keine Variante allein aufgrund dieses einen In-sample-Jahres automatisch aktiviert.

In diesem Fenster senken alle drei getesteten Exit-Sets die Rendite deutlich. Sie reduzieren zwar teilweise den Drawdown, verkaufen aber die wenigen starken Gewinner zu früh und erzeugen viel höheren Umsatz. Das spricht für implementierte, aber vorerst deaktivierte Regeln.

## Unveränderte Grenzen der Aussage

- Die 30er-Watchlist wurde anhand desselben Jahres ausgewählt: Universums-Look-ahead.
- Verkäufe aufgrund von Senatorensignalen wirken weiterhin tickerweit, nicht senatorbezogen.
- Gleichzeitige Meldungen bleiben reihenfolgeabhängig; die Tabelle zeigt deshalb P05 bis P95 aus 200 Reihenfolgen.
- Kadoa ist nicht die Live-Quiver-API; Parsing und Feedreihenfolge können abweichen.
- Kosten/Slippage betragen weiterhin 0,10 % je Seite; Steuern und Cashzins fehlen.

Die vollständigen Entscheidungen des primären C-Laufs stehen in `backtest_1y_aggressive_results.csv`, alle Szenariokennzahlen in `backtest_1y_aggressive_summary.json`.
