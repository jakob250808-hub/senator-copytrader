# Methodik-Audit der bestehenden Backtester

Stand: 14.08.2026 · geprüfter Stand: `6ea6b13`
Geprüft: `src/senator_copytrader/backtest.py`, `factor_backtest.py`,
`portfolio_backtest.py`, alle Backtest-Skripte, `backtest_1y_capital_report.md`,
`factor_backtest_report.md` und die zugehörigen JSON-/CSV-Artefakte.

Jeder Befund ist mit der Codestelle und, wo möglich, mit einer nachrechenbaren
Zahl belegt. Korrigiert wurde nur, was ein echter Fehler ist. **Es wurde kein
Parameter verändert, um die historische Rendite zu erhöhen.**

---

## Zusammenfassung der Schwere

| Nr. | Befund | Schwere | Status |
|---|---|---|---|
| A1 | Berichtete Momentum-CAGR hängt fast vollständig am Teiljahr 2026 | **kritisch** | korrigiert (Doppelausweis) |
| A2 | Delistete/übernommene Titel: Kurse fehlen vollständig (Survivorship) | **kritisch** | quantifiziert, nicht behebbar ohne Datenkauf |
| A3 | Gehaltene Position ohne Kursreihe wird ewig zum letzten Kurs bewertet | **kritisch** | korrigiert + Test |
| A4 | Ticker statt Security-ID; 52 Ticker tragen mehrere Unternehmen | **hoch** | Detektor + `SecurityId` ergänzt |
| A5 | Look-ahead in der Portfoliolimit-Prüfung von Strategie G | **mittel** | korrigiert + Regressionstest |
| A6 | Kein volatilitätsgleicher Benchmark, unvollständiges Kennzahlenset | **mittel** | ergänzt |
| A7 | Indexaustritte werden nie ausgelöst (Mechanik ungetestet) | **mittel** | Test ergänzt |
| A8 | Benchmark-Kosten nur einseitig gerechnet | niedrig | dokumentiert |
| A9 | Drawdown-Startwert ignoriert das Startkapital | niedrig | korrigiert |
| A10 | 2008 liegt außerhalb des Kurscaches | niedrig | dokumentiert |

Nicht beanstandet, weil korrekt umgesetzt: Signalbildung am Vortagsschluss mit
Ausführung am Folge-Open, Split-/Dividendenadjustierung, Dollarvolumen aus
unadjustiertem Kurs × unadjustiertem Volumen, Cash-Deckung vor jedem Kauf,
Walk-forward-Reset je Fenster.

---

## A1 — Die berichtete CAGR hängt an sechs Monaten

`factor_backtest_report.md` nennt +6,41 % CAGR und +104,12 % Gesamtrendite für
02.01.2015–30.06.2026. Derselbe Code, nur bis 31.12.2025:

| Fenster | Gesamtrendite | CAGR | Max DD |
|---|---:|---:|---:|
| 2015 – 30.06.2026 (Bericht) | +104,12 % | +6,41 % | −33,07 % |
| **2015 – 31.12.2025** | **+36,23 %** | **+2,85 %** | −33,07 % |

Das Halbjahr 2026 allein trägt +49,8 % bei. Es stammt aus sechs stark
korrelierten Speicher-/Halbleiternamen. Die Kursdaten selbst sind intern
konsistent (Volumen, Open/Close, monatlicher Verlauf plausibel) — es ist also
kein Rechenfehler, sondern eine echte, extrem konzentrierte Sektorwette.

Genau das verletzt das vorab gesetzte Gate-Kriterium „keine Abhängigkeit von
einem einzelnen Jahr oder wenigen Aktien".

**Korrektur:** `scripts/run_strategy_research.py` berichtet jede Kennzahl
grundsätzlich zweimal — mit und ohne das Teiljahr — und wertet das Gate
ausschließlich auf dem Fenster ohne 2026 aus. Zusätzlich prüft
`_annual_contribution_share()` mechanisch, welchen Anteil das beste Jahr am
gesamten Logwachstum hat.

## A2 — Survivorship: 141 von 768 Tickern haben überhaupt keine Kurse

`work/factor_prices.json` enthält für 627 der 768 relevanten Ticker Daten. Von
den 141 fehlenden liefern 107 HTTP 404, 2 liefern HTTP 400 und 32 liegen ohne
Fehlermeldung leer vor. Von den 627 vorhandenen Reihen enden nur **12** vor dem
20.06.2026. Das Universum besteht also praktisch vollständig aus Überlebenden.

Konsequenz: Die Strategie kann übernommene, insolvente und umbenannte Titel nie
kaufen — und ihre Verluste damit auch nie erleiden. Die Verzerrung wirkt
systematisch nach oben und ist mit einer kostenlosen Kursquelle nicht
reparierbar. Sie ist in `DataContract` als
`survivorship_free_prices=False` fixiert; jeder Lauf mit dieser Datenlage wird
automatisch als **Prototyp** ausgewiesen und kann das Gate formal nicht
bestehen.

## A3 — Eine tote Position blieb ewig am Leben

`factor_backtest.py:348-358` (`latest_value`) bewertet eine Position ohne
Kurspunkt am aktuellen Tag mit dem letzten verfügbaren Schluss — ohne jede
Obergrenze. Beim Rebalance greift `factor_backtest.py:425-441` nur, wenn ein
Kurspunkt existiert (`if point is None: continue`). Eine Aktie, deren Reihe
endet, konnte damit weder verkauft noch abgeschrieben werden: sie blieb bis
zum Laufende zum letzten Kurs in der Bewertung stehen.

Im vorliegenden Lauf trat der Fall nie auf (`stale_position_day_count = 0`) —
nicht weil die Logik stimmt, sondern weil das Kursuniversum nur Überlebende
enthält. Der Fehler wäre erst mit besseren Daten sichtbar geworden, und dann
hätte er still nach oben verzerrt.

**Korrektur:** `research_backtest.py` liquidiert eine Position, deren Reihe
länger als `max_stale_trading_days` (Standard 5 Handelstage) keinen Kurs mehr
liefert, zum letzten Schlusskurs abzüglich `delisting_haircut` (Standard 30 %).
Der Abschlag ist bewusst pessimistisch und ausdrücklich ein Platzhalter für
echte Delisting-Auszahlungen. Zwei Tests sichern das ab, darunter einer, der
die Größe der Verzerrung ohne Schutz explizit misst
(`DelistingTest.test_without_the_stale_guard_the_position_would_survive`).

## A4 — Der Ticker ist keine Wertpapieridentität

Der Mitgliedschaftsdatensatz enthält 1.259 Intervalle für 1.206 Ticker, also
**52 recycelte Ticker**. Bei **19** Intervallen beginnt die heruntergeladene
Kursreihe erst nach dem Ende des Intervalls — dort gehören die Kurse
beweisbar zu einem anderen Emittenten:

| Ticker | Mitgliedschaft | Kursreihe beginnt |
|---|---|---|
| SNDK | 2006-04-20 – 2016-05-12 | 2025-02-13 (WDC-Spin-off, nicht SanDisk Corp.) |
| APC | 1997-07-28 – 2019-08-09 | 2026-02-12 |
| EMC | 1996-03-28 – 2016-09-07 | 2023-05-15 |
| STI | 1996-01-02 – 2019-12-09 | 2022-05-02 |
| INFO | Eintritt 2017-06-02 | 2024-10-10 |

Im aktuellen Fenster wirkt das nicht auf das Ergebnis, weil die betroffenen
Reihen erst nach dem jeweiligen Intervall beginnen. Es beweist aber, dass das
Identitätsmodell nicht trägt: dieselbe Konstellation mit umgekehrter
Zeitfolge würde stillschweigend die Kurse des falschen Unternehmens verwenden.

**Korrektur:** `SecurityId` (Ticker + Mitgliedschaftsintervall) und
`detect_identifier_conflicts()` ergänzt; der Konfliktbericht steht in
`strategy_research_summary.json`. Ein echter, dauerhafter Identifier
(CUSIP/PERMNO/FIGI) bleibt eine offene Datenanforderung.

## A5 — Look-ahead in der Limitprüfung von Strategie G

`portfolio_backtest.py` bewertete beim Limitcheck den Signalticker am
Tages-Open, **alle anderen Positionen aber am Tagesschluss desselben Tages**:

```python
current_portfolio_value = sum(
    position_value(ticker, current_day, at_open=(ticker == signal.ticker))
    for ticker in positions
)
```

`position_value(..., at_open=False)` fällt auf `_latest_close(series, day,
before=False)` zurück und schließt damit den Schlusskurs des laufenden Tages
ein. Der Bot hätte diese Information beim Absenden der Order nicht gehabt. Die
Wirkung ist klein (es geht um eine Limitschwelle, nicht um einen
Ausführungspreis), aber es ist ein echter Look-ahead.

**Korrektur:** alle Positionen werden am Open bewertet.
`tests/test_portfolio_backtest.py::LimitCheckLookAheadTests` schlägt bei
Rückbau der Änderung fehl (verifiziert).

## A6 — Fehlende Kennzahlen und fehlender fairer Benchmark

Der bisherige Bericht nennt CAGR, Drawdown, Volatilität und Sharpe. Für die
Gate-Entscheidung fehlten: Sortino, Calmar, schlechtestes Jahr, schlechtester
Monat, rollierende 12-Monats-Renditen, Anteil negativer 12-Monats-Fenster,
Anzahl positiver Jahre, Anteil der Jahre über SPY, Umsatzquote, durchschnittliche
und maximale Kapitalbindung sowie Konzentration.

Der Benchmark war ein statischer Cash/SPY-Mix am Portfoliolimit — das ist ein
Kapital-, kein Risikovergleich.

**Korrektur:** `performance_metrics()` liefert das vollständige Set;
`benchmark_paths()` erzeugt zusätzlich einen **volatilitätsgleichen** SPY-Pfad
(Gewicht = σ_Strategie / σ_SPY, nie über 1,0, Rest zinslos in Cash). Ergebnis
ohne 2026: bei gleicher Volatilität erzielt SPY +251 bis +300 %, die
Strategiebausteine +27 bis +57 %.

## A7 — Indexaustritte wurden nie ausgelöst

`forced_membership_exit_count = 0` über 138 Rebalances. Der Pfad ist im alten
Code vorhanden, wurde von den Daten aber nie erreicht. Ohne Test ist damit
unbekannt, ob er funktioniert.

**Korrektur:** `MembershipTest.test_index_deletion_forces_an_exit_outside_the_rebalance`
prüft, dass der Verkauf am ersten Tag ohne Mitgliedschaft und außerhalb des
Rebalance-Kalenders stattfindet. Zusätzlich ist die Inklusiv-Semantik von
`end_date` explizit getestet.

## A8 — Benchmarkkosten einseitig

`factor_backtest.py:510` rechnet `(1 - cost) * spy_end / spy_start`, also nur
die Kaufseite. Für Buy-and-hold ist das vertretbar, weil nicht verkauft wird;
es macht den Benchmark aber minimal freundlicher als die Strategie, die beide
Seiten zahlt. Im neuen Bericht ist die Konvention explizit genannt.

## A9 — Drawdown-Referenzpunkt

`factor_backtest.py:496` setzt `peak = daily_values[0]`, startet den Drawdown
also beim Wert **nach** dem ersten Rebalance statt beim eingezahlten Kapital.
Ein Verlust am ersten Handelstag wäre unsichtbar geblieben. In
`performance_metrics()` beginnt die Spitze jetzt beim Startkapital; für die
Strategie **und** für den Benchmark.

## A10 — 2008 ist nicht getestet

Der Kurscache beginnt am 28.11.2013 (`metadata.start = 2013-11-28`). Die
Aussage „mehrere Marktphasen" gilt für 2020 und 2022, **nicht** für 2008. Für
2006–2026 muss neu geladen werden:

```bash
PYTHONPATH=src python3 scripts/run_strategy_research.py --start 2006-01-03
```

Die kostenlose Quelle liefert auch dann keine delisteten Titel; A2 bleibt.

---

## Was bewusst **nicht** geändert wurde

- Keine Schwelle, kein Lookback und kein Filter wurde angepasst. Die
  Momentumparameter (252/21), der Regimefilter (200 Tage), Holdings (20) und
  die Liquiditätsschwellen sind unverändert aus dem Bestand übernommen.
- Die Paper-Konfiguration (`config.example.json`) ist unverändert:
  2.000 / 6.000 / 60.000 / 16.000 USD, Exit-Felder `null`. Kein Baustein hat
  das Gate bestanden, also gibt es keinen Grund, etwas zu ändern.
- `config.paper-demo.json`, der No-Margin-Schutz und die doppelte
  Ausführungsfreigabe sind unangetastet.
- Der alte `factor_backtest.py` bleibt lauffähig, damit der bereits
  veröffentlichte `factor_backtest_report.md` reproduzierbar bleibt. Die
  Korrekturen leben im neuen `research_backtest.py`.
