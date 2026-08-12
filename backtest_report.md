# Senatoren-Copytrading: ehrlicher Vorab-Backtest

Stand: 12. August 2026

## Kurzurteil

Die Idee besteht den ersten Realitätstest **nicht als robuste Copytrading-Strategie**. In der neutral gewählten Gruppe der zehn aktivsten echten Senatoren ist die Datenqualität uneinheitlich, fast jede fünfte Meldung verspätet und das scheinbar positive Gruppenergebnis von zwei extremen Langfrist-Ausreißern abhängig. Sobald Sheldon Whitehouse entfernt wird, wird die nach Zahl der auswertbaren Käufe gewichtete relative Rendite der übrigen Profile negativ.

## Auswahl

Ausgewählt wurden die zehn Senatoren mit den meisten Meldungen im Kadoa Congress Trading Monitor. Der fehlerhafte Datensatz-Eintrag „Alan Armstrong“ (keine Partei, kein Staat, 100 % verspätete Meldungen) wurde nicht als echter Senator akzeptiert. Damit lautet die Gruppe:

| Senator | Meldungen | Käufe | Verkäufe | verspätet | auswertbare Käufe | gewichtetes Ergebnis vs. SPY* |
|---|---:|---:|---:|---:|---:|---:|
| Thomas H. Tuberville | 1.499 | 587 | 912 | 278 | 455 | -35,0 % |
| Sheldon Whitehouse | 1.025 | 533 | 466 | 250 | 409 | +499,7 % |
| Shelley M. Capito | 746 | 365 | 370 | 157 | 336 | -68,4 % |
| Susan M. Collins | 603 | 262 | 336 | 196 | 156 | -224,0 % |
| Markwayne Mullin | 559 | 364 | 195 | 98 | 300 | +9,2 % |
| John Boozman | 434 | 226 | 208 | 22 | 211 | -11,9 % |
| David H. McCormick | 359 | 279 | 80 | 1 | 25 | -51,5 % |
| Rick Scott | 352 | 231 | 118 | 45 | 0 | nicht auswertbar |
| Ron L. Wyden | 303 | 228 | 74 | 52 | 170 | +251,5 % |
| Jerry Moran | 281 | 131 | 149 | 107 | 112 | -5,0 % |
| **Gesamt** | **6.161** | **3.206** | **2.908** | **1.206** | **2.174** |  |

\* Kadoas offen ausgewiesene, nach Positionsgröße gewichtete Langfrist-Überrendite der auswertbaren Käufe gegen einen zeitgleichen SPY-Kauf. Die Seite nimmt für diese Kennzahl an, dass die Käufe bis heute gehalten und die gemeldeten Verkäufe ignoriert werden.

## Ergebnisse

- 3 von 9 auswertbaren Senatoren schlagen SPY; 6 von 9 liegen darunter.
- Median der neun Ergebnisse: **-11,9 Prozentpunkte** gegen SPY.
- Nach Zahl der auswertbaren Käufe gewichtet: **+79,0 Prozentpunkte**. Diese Zahl ist jedoch nicht robust.
- Ohne den größten Ausreißer Sheldon Whitehouse: **-18,5 Prozentpunkte** gewichtet.
- Ohne Whitehouse und Wyden: **-47,3 Prozentpunkte** gewichtet.
- 1.206 von 6.161 Meldungen sind als verspätet markiert: **19,6 %**.
- Rick Scott ist für einen Aktien-Copytest praktisch unbrauchbar: Das Profil besteht überwiegend aus nicht über Alpaca handelbaren Kommunalobligationen; deshalb gibt es keine bewerteten Aktienkäufe.

## Warum dies noch kein echter Paper-Trading-Backtest ist

Das offene Archiv stellt seine fertige Renditekennzahl ab dem **Transaktionsdatum** bereit und bewertet Käufe bis zum heutigen Kurs. Ein echter Bot kennt den Trade aber erst am **Veröffentlichungstag**, häufig Wochen später. Die große historische Kursdatei ließ sich in dieser Sitzung wegen der Browser-Sicherheitsgrenze nicht exportieren; die Grenze wurde nicht umgangen. Deshalb wäre es unseriös, aus diesen Zahlen einen simulierten Kontostand oder eine 90-Tage-Rendite zu erfinden.

Der nächste belastbare Test muss deshalb separat berechnen:

1. Signal erst am Veröffentlichungsdatum;
2. Kauf am folgenden Handelstag;
3. gleicher Dollarbetrag je Signal;
4. Verkauf nach 90 Kalendertagen;
5. 0,20 % Kosten/Slippage;
6. identisches Zeitfenster für SPY;
7. Verkäufe erst berücksichtigen, wenn der Paperbestand aus früheren Signalen vorhanden ist;
8. keine Anleihen, Optionen, Privatfonds oder nicht bei Alpaca handelbaren Werte.

## Mentor-Fazit

Als Forschungsprojekt und Paper-Bot: **ja**. Als Strategie, der ich heute Echtgeld geben würde: **nein**. Die Hypothese „aktive Senatoren liefern kopierbare Alpha“ wird durch diesen Vorabtest nicht bestätigt. Interessanter wäre eine engere, vorab festgelegte Regel – etwa nur fristgerecht gemeldete liquide US-Aktien, mehrere Senatoren kaufen denselben Titel, und ein Vergleich gegen einfache Momentum- und SPY-Benchmarks.

## Quellen

- Kadoa Congress Trading Monitor: https://www.kadoa.com/congress
- Methodik: https://www.kadoa.com/congress/about
- Offener Datensatz/Code: https://github.com/kadoa-org/congress-trading-monitor
- Offizielle Senate-Ethics-Seite zu Periodic Transaction Reports: https://www.ethics.senate.gov/public/index.cfm/financialdisclosure

