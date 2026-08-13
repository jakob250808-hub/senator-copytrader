# Senatoren-Copytrading: Veröffentlichungstag-Backtest

Stand: 13. August 2026

## Kurzurteil

Die belastbar auswertbaren historischen Kaufsignale schlagen SPY im Mittel nur
um **0,151 Prozentpunkte** über 90 Kalendertage. Der Median des Vorsprungs ist
mit **−0,056 Prozentpunkten negativ**, und exakt die Hälfte der 686 Signale
schlägt SPY. Das Ergebnis bestätigt daher **keine robuste kopierbare Alpha**.

Der Test ist erstmals konsequent ab dem tatsächlichen Meldungseingang gerechnet,
nicht ab dem dem Markt bereits bekannten Transaktionsdatum. Er bleibt trotzdem
eine Forschungsrechnung und keine realistische Kontosimulation: Das Archiv endet
2021, vier der zehn ausgewählten Personen liefern keine maschinenlesbaren
Transaktionen, und 74 sonst geeignete Signale lassen sich beim heutigen
Kursanbieter nicht mehr auflösen. Letzteres kann Survivorship Bias verursachen.

## Methodik

Die Berechnung in `scripts/run_backtest.py` verwendet die tagesweisen JSON-Dateien
aus `work/senate-stock-watcher-data/data` und arbeitet nach folgenden festen
Regeln:

1. Die zehn Personen sind unverändert aus der vorigen Kadoa-Voranalyse
   übernommen. Diese Auswahl wurde anhand später bekannter Gesamtaktivität
   getroffen und ist daher **keine look-ahead-freie Universumsauswahl**.
2. Berücksichtigt werden nur als `Purchase` und `Stock` gekennzeichnete Zeilen
   mit eindeutigem Ticker. Tatsächliche Verkaufsmeldungen werden nicht als
   Signal verwendet; jeder Kauf wird stattdessen nach derselben festen Frist
   geschlossen.
3. Signalzeitpunkt ist `date_recieved`, also der Tag, an dem die Meldung im
   Archiv einging. Das frühere Transaktionsdatum entscheidet nie über den
   Einstieg.
4. Einstieg ist der **adjustierte Eröffnungskurs des nächsten SPY-Handelstags**.
   Fehlt für den Titel genau an diesem Tag ein Kurs, wird das Signal verworfen;
   es wird nicht heimlich bis zum nächsten verfügbaren Titelkurs gewartet.
5. Ausstieg ist der adjustierte Schlusskurs des ersten SPY-Handelstags am oder
   nach 90 Kalendertagen ab Einstieg.
6. Pro Signal werden 1.000 USD eingesetzt. Für Kauf und Verkauf werden jeweils
   0,10 % Kosten/Slippage abgezogen, zusammen rund 0,20 %.
7. SPY erhält denselben Einstiegstag, Ausstiegstag, Betrag und Kostenansatz.
8. Der Kursanbieter muss den Titel als `EQUITY` oder `ETF` klassifizieren.
   Fonds, Anleihen, Optionen, unklare Ticker sowie fehlende Kursfenster werden
   ausgeschlossen und in `backtest_results.csv` mit Grund ausgewiesen.
9. Mehrfach im Archiv vorhandene identische Meldungen werden anhand PTR-Link,
   Transaktionsinhalt und Vorkommen dedupliziert.

Adjustierte Kurse berücksichtigen Splits und ausgeschüttete Dividenden nach der
Methodik des Kursanbieters. Je Signal werden Bruchteile von Aktien und
ausreichend unabhängiges Kapital angenommen. Die Summenzeile ist deshalb keine
Simulation eines begrenzten 100.000-USD-Kontos und enthält weder Steuern noch
Bid-Ask-Spreads, Marktimpact oder Liquiditätsprüfung.

## Datenabdeckung

Das lokale Senate-Stock-Watcher-Archiv umfasst Meldungseingänge vom 25. Juli
2012 bis 10. März 2021. Für die ausgewählte Gruppe enthält es 1.161 Käufe. Nach
den konservativen Filtern bleiben 780 grundsätzlich kursfähige Aktienkäufe;
686 davon (**87,9 %**) besitzen ein vollständiges, passendes 90-Tage-Kursfenster.
Die bewerteten Signale reichen vom 29. Januar 2015 bis 18. Februar 2021.

| Person | Meldungen | Transaktionen | Käufe | bewertet | Rendite | SPY | Differenz |
|---|---:|---:|---:|---:|---:|---:|---:|
| Thomas H Tuberville | 0 | 0 | 0 | 0 | – | – | – |
| Sheldon Whitehouse | 88 | 670 | 384 | 235 | 3,266 % | 3,845 % | −0,579 Pp. |
| Shelley M Capito | 44 | 357 | 214 | 191 | 5,417 % | 5,350 % | +0,067 Pp. |
| Susan M Collins | 112 | 389 | 165 | 29 | 2,616 % | 3,749 % | −1,133 Pp. |
| Markwayne Mullin | 0 | 0 | 0 | 0 | – | – | – |
| John Boozman | 43 | 0 | 0 | 0 | – | – | – |
| David H McCormick | 0 | 0 | 0 | 0 | – | – | – |
| Rick Scott | 19 | 146 | 123 | 0 | – | – | – |
| Ron L Wyden | 12 | 223 | 195 | 162 | 9,551 % | 8,026 % | +1,524 Pp. |
| Jerry Moran | 5 | 138 | 80 | 69 | 5,099 % | 4,918 % | +0,181 Pp. |
| **Alle bewerteten Signale** |  |  |  | **686** | **5,506 %** | **5,355 %** | **+0,151 Pp.** |

John Boozman ist im Archiv mit 43 Meldungen vertreten, aber ohne extrahierte
Transaktionen (überwiegend nur Papier-/PDF-Meldungen). Rick Scotts 123 Käufe
sind sämtlich nicht als Aktien klassifiziert. Tuberville, Mullin und McCormick
kommen im historischen Archivzeitraum nicht vor.

## Ergebnis

Bei 1.000 USD pro auswertbarem Signal werden rechnerisch 686.000 USD eingesetzt.
Nach jeweils 90 Tagen und Kosten entstehen in der Strategie zusammen
**723.770,84 USD**, gegenüber **722.735,66 USD** bei den zeitgleichen
SPY-Investments: ein Unterschied von nur **1.035,18 USD** über alle unabhängigen
Tranchen.

- Durchschnittlicher 90-Tage-Ertrag der Signale: **+5,506 %**
- Durchschnittlicher zeitgleicher SPY-Ertrag: **+5,355 %**
- Mittlere Differenz: **+0,151 Prozentpunkte**
- Median der Differenz: **−0,056 Prozentpunkte**
- Signale oberhalb SPY: **343 von 686 (50,0 %)**

Das kleine positive Mittel wird nicht von einer breiten Trefferquote getragen.
Auch die Personenresultate sind gemischt: Zwei liegen unter SPY, drei knapp bis
deutlich darüber; für fünf Personen gibt es gar keine Bewertung. Aus diesen
Daten lässt sich weder ein stabiler Vorteil noch eine verlässliche Rangfolge der
Senatoren ableiten.

## Ausschlüsse und bekannte Verzerrungen

| Ausschlussgrund | Käufe |
|---|---:|
| Quelle klassifiziert das Asset nicht als Aktie | 338 |
| Kursanbieter liefert HTTP 404 für historischen Ticker | 56 |
| ungültiger oder fehlender Ticker | 43 |
| Kursanbieter liefert HTTP 400 für historischen Ticker | 18 |
| Kursanbieter klassifiziert Ticker als Investmentfonds | 10 |
| kein Kursverlauf im benötigten Zeitraum | 6 |
| kein Titelkurs genau am regelkonformen Einstiegstag | 4 |

Die 74 HTTP-Ausschlüsse betreffen unter anderem später übernommene, delistete
oder umbenannte Unternehmen. Sie pauschal auf heutige Nachfolgeticker umzubiegen
wäre ebenfalls fehleranfällig, weil Unternehmensidentität, Kapitalmaßnahmen und
Kursreihen nicht immer eins zu eins fortbestehen. Das bewusste Ausschließen ist
nachvollziehbar, kann das Ergebnis aber zugunsten überlebender Unternehmen
verzerren. Für einen publikationsreifen Test wäre deshalb eine historische
Point-in-time-Kursdatenbank mit delisteten Wertpapieren nötig.

Weitere Grenzen:

- Die zehnköpfige Gruppe wurde rückblickend anhand späterer Aktivität gewählt.
- Mehrere Signale derselben Person oder Aktie sind korreliert und keine
  unabhängigen statistischen Beobachtungen.
- Offenlegungen nennen Wertspannen; der Test ignoriert diese absichtlich und
  setzt immer denselben Betrag ein.
- Das Archiv deckt neuere Mitglieder und heutige Marktregime nicht ab.
- Negative oder ungewöhnliche Meldeverzögerungen werden nicht repariert; die
  veröffentlichte Eingangsangabe bleibt maßgeblich.

## Mentor-Fazit

Der echte Veröffentlichungstag-Test ist deutlich aussagekräftiger als die
vorige Langfrist-Voranalyse, ändert aber die Entscheidung nicht: **Paper-Bot als
Experiment ja, Echtgeld nein.** Ein durchschnittlicher Vorsprung von 0,151
Punkten bei negativem Median, 50-%-Trefferquote, unvollständiger Personenabdeckung
und möglichem Survivorship Bias ist keine belastbare Handelsgrundlage.

Der nächste sinnvolle Forschungsstand wäre eine vorab festgelegte Kohorte in
einem vollständigeren Archiv samt delisteter Titel sowie ein zeitlich getrenntes
Out-of-sample-Fenster. Erst danach wären Varianten wie Konsenssignale mehrerer
Senatoren oder Liquiditäts-/Momentumfilter seriös vergleichbar.

## Reproduzierbarkeit und Quellen

- Programm: `scripts/run_backtest.py`
- Einzelergebnisse samt Ausschlussgrund und verwendeten Preisen:
  `backtest_results.csv`
- Offenlegungsarchiv, verwendeter Commit
  `384e08e84d809477cdfba7d52479147fbe5e6bd7`:
  https://github.com/timothycarambat/senate-stock-watcher-data
- Historische adjustierte Tageskurse: Yahoo Finance Chart API
- Offizielle Senate-Finanzoffenlegung:
  https://www.ethics.senate.gov/public/index.cfm/financialdisclosure
- Frühere Kohortenauswahl: https://www.kadoa.com/congress

Lokaler Aufruf aus dem Projektverzeichnis:

```bash
PYTHONPATH=src python3 scripts/run_backtest.py
```

Der Abrufcache liegt absichtlich im ignorierten Ordner `work/`. Die für jedes
bewertete Signal tatsächlich verwendeten vier Preise stehen dagegen in der
versionierten CSV, sodass das veröffentlichte Ergebnis prüfbar bleibt.
