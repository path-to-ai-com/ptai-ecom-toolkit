# Herkunft dieser Fixtures

**Von Hand gebaut, nicht aufgezeichnet.** Grundlage ist die REST-Referenz von
`customers.googleAds.search` und die Feldliste der Google Ads API, Stand
07.09.2026.

Der Grund: zum Zeitpunkt des Baus gab es keinen API-Zugang, also keinen
einzigen echten Aufruf. Anders als bei den
DataForSEO-Pulls, deren Fixtures aus echten Produktiv-Antworten stammen, sind
diese Dateien nur so gut wie die Doku.

**Was sie beweisen und was nicht.** Sie beweisen, dass der Code die
dokumentierte Struktur richtig liest: Paginierung über `nextPageToken`,
Micros-Umrechnung, Monatsaggregation, die Rechnung des Impression Share. Sie
beweisen **nicht**, dass die echte Antwort so aussieht.

**Seit dem 02.10.2026 ist die Struktur gegen ein echtes Konto bestätigt**
(Verifikationsliste in `skills/pull-ads/SKILL.md`). Die Fixtures bleiben
trotzdem von Hand gebaut: aufgezeichnete Antworten enthielten Kampagnennamen
und Zahlen eines Kunden, und die gehören nicht ins Repo.
