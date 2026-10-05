// Säulen- und Gesamtscore aus den gegateten Befunden.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { computeScores, compositeOf, hatAbdeckung } from './score.mjs';

const f = (lens, severity, confidence = 'high', effort = '1 bis 2 Tage') =>
  ({ lens, severity, confidence, effort, title: `${lens}/${severity}` });

test('Linsen landen in ihrer Säule, markt in keiner', () => {
  const r = computeScores([
    f('auffindbarkeit', 'crit'), f('ki-sichtbarkeit', 'warn'),
    f('kaufstrecke', 'crit'), f('sortiment', 'warn'),
    f('vertrauen', 'warn'), f('markt', 'crit'),
  ]);
  assert.equal(r.debug.gefunden.befunde, 2);
  assert.equal(r.debug.kaufen.befunde, 2);
  assert.equal(r.debug.vertrauen.befunde, 1);
  assert.deepEqual(r.ohne_saeule.map((x) => x.lens), ['markt']);
});

test('Kaufen wiegt am schwersten, Suche nicht mehr', () => {
  const r = computeScores([]);
  assert.equal(r.gewichte.kaufen, 0.45);
  assert.equal(r.gewichte.gefunden, 0.30);
  assert.equal(r.gewichte.vertrauen, 0.25);
  assert.equal(r.gewichte.gefunden + r.gewichte.kaufen + r.gewichte.vertrauen, 1);
});

test('makellose Säule bekommt 100, seit dem 11.09.2026 ohne Deckel bei 92', () => {
  const r = computeScores([f('kaufstrecke', 'ok')]);
  assert.equal(r.scores.kaufen, 100);
});

test('viele crits fallen unter die alte Grenze 35, aber nie unter 0', () => {
  // Bis 11.09.2026 hielt ein Boden die Säule bei 35 fest, egal wie schwer die Lücken waren.
  const r = computeScores(Array.from({ length: 20 }, () => f('kaufstrecke', 'crit')));
  assert.ok(r.scores.kaufen < 35 && r.scores.kaufen >= 0, `${r.scores.kaufen} muss zwischen 0 und 35 liegen`);
});

test('niedrige Confidence straft schwächer als hohe', () => {
  const hoch = computeScores([f('kaufstrecke', 'crit', 'high')]).scores.kaufen;
  const niedrig = computeScores([f('kaufstrecke', 'crit', 'low')]).scores.kaufen;
  assert.ok(niedrig > hoch, `${niedrig} muss über ${hoch} liegen`);
});

test('der Warn-Deckel verhindert, dass Prüftiefe allein die Note macht', () => {
  const zehn = computeScores(Array.from({ length: 10 }, () => f('sortiment', 'warn'))).scores.kaufen;
  const zwanzig = computeScores(Array.from({ length: 20 }, () => f('sortiment', 'warn'))).scores.kaufen;
  assert.equal(zehn, zwanzig, 'ab der elften Warnung darf sich nichts mehr ändern');
});

test('aber die ersten zehn Warnungen zählen spürbar, nicht nur die ersten fünf', () => {
  // Bis 09.09.2026 galt: fünf warns == zwanzig warns, weil WARN_CAP bei 5 lag und
  // WARN_DIM (0,55) danach ohnehin fast nichts mehr beitrug. Eine Säule ganz ohne
  // crit-Befund landete damit unabhängig von der Warn-Menge bei 88 bis 92 (belegt an
  // zwei realen Läufen: Kaufen 0 crit/7 warn = 90, Vertrauen 0 crit/9
  // warn = 89). Fünf echte warns müssen jetzt spürbar mehr kosten als eine einzelne.
  const eine = computeScores([f('sortiment', 'warn')]).scores.kaufen;
  const fuenf = computeScores(Array.from({ length: 5 }, () => f('sortiment', 'warn'))).scores.kaufen;
  assert.ok(fuenf <= eine - 8, `fünf warns (${fuenf}) müssen deutlich unter einer warn (${eine}) liegen`);
});

test('Ziel liegt über dem Score und nie über 100', () => {
  const r = computeScores([f('kaufstrecke', 'crit'), f('kaufstrecke', 'warn')]);
  assert.ok(r.targets.kaufen > r.scores.kaufen);
  assert.ok(r.targets.kaufen <= 100);
});

test('Gesamtscore ist das gewichtete Mittel', () => {
  const c = compositeOf({ gefunden: 60, kaufen: 80, vertrauen: 40 });
  assert.equal(c, Math.round(0.30 * 60 + 0.45 * 80 + 0.25 * 40));
});

test('ohne Abdeckung gibt es keinen Score, sondern eine ausgewiesene Lücke', () => {
  const coverage = { kaufstrecke: { checked: [], not_checkable: [{ what: 'alles', reason: 'geblockt' }] },
                     sortiment:   { checked: [], not_checkable: [{ what: 'alles', reason: 'geblockt' }] } };
  const r = computeScores([f('auffindbarkeit', 'warn')], coverage);
  assert.equal(r.scores.kaufen, null, 'eine geblockte Säule darf keinen Wert bekommen');
  assert.ok(r.ohne_score.includes('kaufen'));
  assert.equal(r.targets.kaufen, null);
});

test('eine von zwei Linsen mit Abdeckung reicht der Säule', () => {
  const coverage = { kaufstrecke: { checked: ['Kaufbutton'], not_checkable: [] },
                     sortiment:   { checked: [], not_checkable: [{ what: 'x', reason: 'y' }] } };
  assert.equal(hatAbdeckung('kaufen', coverage), true);
  assert.notEqual(computeScores([], coverage).scores.kaufen, null);
});

test('fehlende Abdeckungsangabe löscht keinen Score', () => {
  // Ein alter Lauf ohne coverage-Dateien soll nicht rueckwirkend leer werden.
  assert.equal(computeScores([f('kaufstrecke', 'warn')], null).scores.kaufen !== null, true);
  assert.equal(computeScores([f('kaufstrecke', 'warn')], {}).scores.kaufen !== null, true);
});

test('der Gesamtscore verteilt das Gewicht einer ausgefallenen Säule um', () => {
  const coverage = { vertrauen: { checked: [], not_checkable: [{ what: 'x', reason: 'y' }] } };
  const r = computeScores([f('auffindbarkeit', 'warn'), f('kaufstrecke', 'warn')], coverage);
  assert.equal(r.scores.vertrauen, null);
  // Ohne Umverteilung waere der Gesamtscore allein deshalb niedriger, weil eine
  // Saeule nicht messbar war. Das waere ein Urteil ueber die Messung, nicht ueber den Shop.
  assert.ok(r.composite > 0 && r.composite <= 100);
});

test('faellt alles aus, gibt es keinen Gesamtscore', () => {
  const leer = { checked: [], not_checkable: [{ what: 'x', reason: 'y' }] };
  const r = computeScores([], { auffindbarkeit: leer, 'ki-sichtbarkeit': leer,
                                kaufstrecke: leer, sortiment: leer, vertrauen: leer });
  assert.equal(r.composite, null);
  assert.equal(r.ohne_score.length, 3);
});

test('unbekannte Linse verschwindet nicht still', () => {
  const r = computeScores([f('tippfehler-linse', 'crit')]);
  assert.equal(r.ohne_saeule.length, 1);
  assert.equal(r.ohne_saeule[0].lens, 'tippfehler-linse');
});

// --- Das Ziel, seit 16.09.2026 ---------------------------------------------
// Bis dahin galt `score + min(24, 8 + quickWins*3)`, wobei quickWins das Wort
// "woche" im Feld `effort` suchte. Dort steht laut Vertrag ein Label aus einer
// festen Liste, in dem es nie vorkommt: das Ziel war damit in jedem Report
// exakt score+24. Diese drei Tests halten die neue Regel fest.

test('ohne bleibende Befunde ist das Ziel der Deckel, nicht score+24', () => {
  const r = computeScores([f('vertrauen', 'crit'), f('vertrauen', 'crit'), f('vertrauen', 'warn')]);
  assert.ok(r.scores.vertrauen < 80, 'Ausgangswert soll deutlich unter dem Deckel liegen');
  assert.equal(r.targets.vertrauen, 92, 'alles umsetzbar, also der Deckel');
  assert.notEqual(r.targets.vertrauen - r.scores.vertrauen, 24, 'der feste Abstand von 24 ist weg');
});

test('ein bleibender Befund drueckt das Ziel unter den Deckel', () => {
  const bleibt = { ...f('vertrauen', 'crit'), persists: true };
  const r = computeScores([bleibt, f('vertrauen', 'crit'), f('vertrauen', 'warn')]);
  assert.ok(r.targets.vertrauen < 92, 'was bleibt, kostet auch im Ziel Punkte');
  assert.ok(r.targets.vertrauen > r.scores.vertrauen, 'das Ziel liegt trotzdem ueber dem Ausgangswert');
});

test('das Ziel faellt nie unter den Ausgangswert', () => {
  // Konstruiert: jeder Befund bleibt, das Ziel waere sonst der Ausgangswert selbst.
  const alle = [1, 2, 3, 4].map(() => ({ ...f('kaufstrecke', 'crit'), persists: true }));
  const r = computeScores(alle);
  assert.ok(r.targets.kaufen >= r.scores.kaufen);
});

test('unterschiedliche Saeulen bekommen unterschiedliche Zielabstaende', () => {
  const r = computeScores([
    f('auffindbarkeit', 'warn'),
    f('kaufstrecke', 'crit'), f('kaufstrecke', 'crit'), f('kaufstrecke', 'crit'),
    { ...f('vertrauen', 'crit'), persists: true },
  ]);
  const abstaende = new Set([
    r.targets.gefunden - r.scores.gefunden,
    r.targets.kaufen - r.scores.kaufen,
    r.targets.vertrauen - r.scores.vertrauen,
  ]);
  assert.ok(abstaende.size > 1, 'drei identische Abstaende waren der alte Fehler');
});
