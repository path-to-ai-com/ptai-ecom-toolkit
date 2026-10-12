# Änderungsstopp: abgelöst seit 0.3.11

Es gibt keinen Änderungsstopp mehr. Das Team arbeitet während der Migration am Live-Theme weiter, und
direkt vor dem Launch zieht der Betreiber den Stand neu (`theme-launch`, Phase 9, "Abgleich vor dem
Launch"). Jede Änderung seit diesem Abgleich hält den Launch an, bis ein Lauf sie übernommen hat.

Grund: Ein Stopp brauchte ein Launch-Datum, lange bevor der Entwurf fertig war. In drei parallelen
Migrationen einer Marke trugen die Teams deshalb Termine und Stopps ein, die niemand entschieden hatte.

`run_state upgrade` entfernt `freeze_from`, `freeze_until` und `theme_migration.freeze` aus älteren
Läufen.
