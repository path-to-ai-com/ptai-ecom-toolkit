// Ecom-Audit PDF report — comprehensive flowing renderer (story-arc layout).
// Designed HTML (A4), rendered to PDF via headless Chrome.
// v2: flowing layout (no height:297mm clip), all findings per chapter, chapter-level skill attribution.
// v3: brand fonts embedded (engine/fonts.mjs, base64) — zero network dependency at render time.
// v4: story-arc — data-driven cover, market + shop-at-a-glance, positioning quadrant, comparison
//     matrix, top-first/compact findings, strategy triage, AI levers, sources. All new sections are
//     OPTIONAL: a missing content.json field simply skips its section (graceful degradation, and an
//     old content.json still renders cover + exec + chapters + fahrplan + closing).

// Marken-Fonts als Dateien, relativ zu diesem Modul. Der alte Stand trug sie als
// base64 im Repo (fonts.mjs allein 712 KB), weil der Renderer ohne Netz
// auskommen musste. Das Plugin hat die echten Dateien unter assets/brand/, und
// Chrome liest sie ueber file:// genauso offline.
import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname, extname, isAbsolute, join } from 'node:path';
import { pathToFileURL } from 'node:url';

const BRAND = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'assets', 'brand');
const asset = (...p) => pathToFileURL(join(BRAND, ...p)).href;

const FONT_FACE_CSS = `
@font-face{font-family:'Archivo';font-weight:900;font-style:normal;font-display:block;src:url("${asset('fonts','archivo-black.woff2')}") format('woff2')}
@font-face{font-family:'Archivo';font-weight:900;font-style:italic;font-display:block;src:url("${asset('fonts','archivo-black-italic.woff2')}") format('woff2')}
@font-face{font-family:'Inter';font-weight:400;font-style:normal;font-display:block;src:url("${asset('fonts','inter-regular.woff2')}") format('woff2')}
@font-face{font-family:'Inter';font-weight:600;font-style:normal;font-display:block;src:url("${asset('fonts','inter-semibold.woff2')}") format('woff2')}
@font-face{font-family:'JetBrains Mono';font-weight:500;font-style:normal;font-display:block;src:url("${asset('fonts','jetbrains-mono-medium.woff2')}") format('woff2')}
`;

export const esc = (s) =>
  String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// Common named HTML entities the consolidator agents emit in prose. Numeric entities (&#NNNN; /
// &#xNN;) are handled generically below — this map only covers names that have no numeric escape
// in the source text. Unknown names are left untouched (they get esc'd → render literally, safely).
const NAMED_ENTITIES = {
  nbsp: ' ', amp: '&', lt: '<', gt: '>', quot: '"', apos: "'",
  mdash: '—', ndash: '–', hellip: '…', euro: '€',
  copy: '©', reg: '®', trade: '™', deg: '°', times: '×',
  rarr: '→', larr: '←', laquo: '«', raquo: '»',
  bdquo: '„', ldquo: '“', rdquo: '”', sbquo: '‚', lsquo: '‘', rsquo: '’',
};

// Decode HTML entities to real Unicode. The Phase-2 agents naturally write &nbsp; (glue spaces),
// numeric entities like &#8222;/&#8220; (German quotes) and &#8902; (⋆) — without this they'd
// render LITERALLY as "&nbsp;"/"&#8222;" in the PDF. Single pass over each &…; token; unknown
// entities are returned verbatim so esc() can render them as harmless literal text.
export const decodeEntities = (s) =>
  String(s ?? '').replace(/&(#x[0-9a-f]+|#\d+|[a-z][a-z0-9]*);/gi, (m, ent) => {
    if (ent[0] === '#') {
      const cp = ent[1].toLowerCase() === 'x' ? parseInt(ent.slice(2), 16) : parseInt(ent.slice(1), 10);
      return Number.isFinite(cp) && cp > 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : m;
    }
    const c = NAMED_ENTITIES[ent.toLowerCase()];
    return c === undefined ? m : c;
  });

// Decode entities → escape ALL tags → restore a safe inline-formatting allowlist. Decoding first
// means agent-emitted &nbsp;/&#8222;/&amp; become real characters (then esc re-escapes any bare
// & < > " into valid HTML). Escaping then restoring lets finding bodies/intros QUOTE raw site HTML
// (e.g. <title>, <h1>, <meta>) as readable literal text without the browser parsing it as real
// elements — while still rendering intentional <span class='hl'> / <b> emphasis and <code> spans.
export const safeHtml = (s) => {
  let out = esc(decodeEntities(s));
  out = out.replace(/&lt;(\/?)(b|i|em|strong|code)&gt;/gi, '<$1$2>');
  out = out.replace(/&lt;br\s*\/?&gt;/gi, '<br>');
  // <span>-Allowlist: genau ein Attribut, class=hl — die einzige Inline-Klasse, die das Report-CSS
  // kennt (.lead .hl / .ch-intro .hl). Der Wert darf in doppelten Quotes stehen (esc() hat die zu
  // diesem Zeitpunkt schon in &quot; verwandelt), in einfachen oder in gar keinen; content.json
  // darf also beide Schreibweisen benutzen. Die Quotes werden nur INNERHALB dieser gematchten Form
  // zurückgewandelt, die Zeichenklasse bleibt zu. Alles andere — fremde Klasse, style/onclick,
  // nacktes <span> — bleibt escapter Text, denn das sind Befunde, die Shop-Markup ZITIEREN.
  // Ein </span> wird nur zurückgewandelt, wenn es ein geöffnetes Highlight schließt: sonst würde
  // ein zitiertes </span> die echte Hervorhebung vorzeitig beenden.
  let open = 0;
  out = out.replace(/&lt;span\s+class=(&quot;|'|)(?:hl)\1\s*&gt;|&lt;\/span&gt;/gi, (m, q) => {
    if (m.startsWith('&lt;/')) {
      if (open === 0) return m;
      open--;
      return '</span>';
    }
    open++;
    const quote = q === '&quot;' ? '"' : q;
    return `<span class=${quote}hl${quote}>`;
  });
  return out;
};

// ---------- shared bits ----------

// Neue CI kennt kein Gelb/Grün: Rot = Handlungsbedarf (laut), Tinte = teilweise, Blau = ruhig/ok.
const SEVERITY_COLOR = { crit: '#C62F14', warn: '#14150F', info: '#1F3F8F', ok: '#1F3F8F' };

// Cover headline: plaintext in; colour the sentence-ending periods in signal orange.
function coverHeadline(d) {
  const h = d.cover && d.cover.headline;
  if (!h) return `Gefunden<span class="dot">.</span> Empfohlen<span class="dot">.</span> Gekauft<span class="dot">.</span>`;
  return esc(h).replace(/\.(\s|$)/g, '<span class="dot">.</span>$1');
}

// Harvey ball for the comparison matrix (0 = empty, 1 = half, 2 = full). Inline SVG so it renders
// identically in headless Chrome regardless of font glyph coverage.
function hb(n) {
  const c = '#1F3F8F';
  if (n >= 2) return `<svg width="14" height="14" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="${c}"/></svg>`;
  if (n === 1) return `<svg width="14" height="14" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="none" stroke="${c}" stroke-width="1.5"/><path d="M8 1 A7 7 0 0 1 8 15 Z" fill="${c}"/></svg>`;
  return `<svg width="14" height="14" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="none" stroke="${c}" stroke-width="1.5"/></svg>`;
}

// ---------- exec / fahrplan sub-renderers ----------

// Ampel-Variante (exec.scoreStyle === 'ampel'): Status statt 0-100-Zahl.
function ampelLevel(score) {
  const s = Math.max(0, Math.min(100, Number(score) || 0));
  if (s >= 75) return { color: '#1F3F8F', word: 'Stark', idx: 2 };
  if (s >= 50) return { color: '#14150F', word: 'Ausbaufähig', idx: 1 };
  return { color: '#C62F14', word: 'Handlungsbedarf', idx: 0 };
}

function ampelDots(level, size) {
  const cols = ['#C62F14', '#14150F', '#1F3F8F'];
  return `<div class="ampel">${cols.map((c, i) => `<span class="ad${i === level.idx ? ' on' : ''}" style="${i === level.idx ? `background:${c}` : `border:1.5px solid ${c};opacity:.35`};width:${size}px;height:${size}px"></span>`).join('')}</div>`;
}

function scoreCol(s, style) {
  const score = Math.max(0, Math.min(100, s.score));
  const target = Math.max(0, Math.min(100, s.target ?? 0));
  if (style === 'potenzial') {
    const lvl = ampelLevel(score);
    return `<div class="scol">
    <div class="mono lbl">${esc(s.label)}</div>
    <div class="num">${score}<span class="den">/100</span></div>
    <div class="bar"><div class="fill" style="width:${score}%;background:${lvl.color}"></div>
      ${s.target ? `<div class="mark" style="left:${target}%"></div><div class="goal mono" style="left:${target}%">Ziel ${target}</div>` : ''}
    </div>
    ${s.target && target > score ? `<div class="pot mono">+${target - score} PUNKTE ERREICHBAR</div>` : ''}
    <div class="cap">${esc(s.caption)}</div>
  </div>`;
  }
  if (style === 'ampel') {
    const now = ampelLevel(score);
    const goal = s.target ? ampelLevel(target) : null;
    return `<div class="scol">
    <div class="mono lbl">${esc(s.label)}</div>
    ${ampelDots(now, 13)}
    <div class="aword">${esc(now.word)}</div>
    ${goal ? `<div class="agoal mono">ZIEL NACH UMSETZUNG: <span style="color:${goal.color}">${esc(goal.word.toUpperCase())}</span></div>` : ''}
    <div class="cap">${esc(s.caption)}</div>
  </div>`;
  }
  return `<div class="scol">
    <div class="mono lbl">${esc(s.label)}</div>
    <div class="num">${score}<span class="den">/100</span></div>
    <div class="bar"><div class="fill" style="width:${score}%"></div>
      ${s.target ? `<div class="mark" style="left:${target}%"></div><div class="goal mono" style="left:${target}%">Ziel ${target}</div>` : ''}
    </div>
    <div class="cap">${esc(s.caption)}</div>
  </div>`;
}

function stageCol(s) {
  return `<div class="stage">
    <div class="mono slbl">${esc(s.stage)}</div>
    <div class="stitle">${esc(s.title)}</div>
    <ul>${s.items.map((it) => `<li>${esc(it)}</li>`).join('')}</ul>
  </div>`;
}

// ---------- findings ----------

// Das Badge oben rechts trug bis zum 21.09.2026 das Aufwands-Label (Sehr gering, Gering bis
// mittel). Es stand damit an der Stelle, an der ein Leser die Wichtigkeit erwartet, und ohne
// Bezugswort las es sich als Urteil ueber den Befund selbst. Yves: *"Was soll eigentlich dieses
// 'gering bis mittel' oder 'sehr gering'? Das versteht doch niemand. Das scheint, als wuerde man
// sagen, dass es nichts bringt."* Jetzt benennt es die Schwere, also dasselbe, was der farbige
// Strich links zeigt, nur in Worten. Der Aufwand geht nicht verloren: er steht als Satz am Ende
// der Empfehlung, wo er zur Massnahme gehoert.
const SEVERITY_LABEL = { crit: 'Kritisch', warn: 'Wichtig', info: 'Hinweis', ok: 'Läuft' };

function findingBlock(f, i) {
  const dot = SEVERITY_COLOR[f.severity] || SEVERITY_COLOR.info;
  const label = SEVERITY_LABEL[f.severity];
  // f.evidence is intentionally NOT rendered in the client-facing PDF — raw evidence lives in
  // findings.json, the job-folder .md reports, and the aggregated Sources section.
  return `<div class="fcard">
    <div class="fsev" style="background:${dot}"></div>
    <div class="fbody">
      <div class="fhead"><span class="fnum mono">Befund ${String(i + 1).padStart(2, '0')}</span>${label ? `<span class="fbadge fbadge--${esc(f.severity)} mono">${esc(label)}</span>` : ''}</div>
      <div class="ftitle">${esc(f.title)}</div>
      <div class="ftext">${safeHtml(f.body)}</div>
      ${f.recommendation ? `<div class="frec"><span class="mono frec-lbl">EMPFEHLUNG</span> ${esc(f.recommendation)}</div>` : ''}
      ${f.impact ? `<div class="fimpact"><span class="mono">Wirkung</span> ${esc(f.impact)}</div>` : ''}
      ${f.skill_source ? `<div class="fskill mono">${esc(f.skill_source)}</div>` : ''}
      ${f.url ? `<a class="floc mono" href="${esc(f.url)}">↗ zur Stelle ansehen</a>` : ''}
    </div>
  </div>`;
}

function compactFinding(f) {
  const dot = SEVERITY_COLOR[f.severity] || SEVERITY_COLOR.info;
  return `<div class="fcrow"><span class="fcdot" style="background:${dot}"></span><div><div class="fct">${esc(f.title)}</div>${f.impact ? `<div class="fci">${esc(f.impact)}</div>` : ''}</div></div>`;
}

// ---------- Befund als Entscheidungsvorlage ----------
//
// Bis zum 01.10.2026 war jeder ausführliche Befund ein Textblock: Befund, Empfehlung, Wirkung,
// alles als Fließtext mit den Messwerten mittendrin, und zwei mögliche Wege standen als
// "alternativ" im Empfehlungssatz. Am 30.09.2026 kam aus einem Gespräch mit einem Geschäftsführer
// das Feedback, was er braucht: Entscheidungsvorlagen statt Informationen, ein Entweder-oder.
// Am 01.10.2026 sind zwei Audits in diesem Format entstanden, aber nur als Einzelskripte im
// Kundenordner; der Renderer blieb unverändert, und der nächste Lauf am 02.10.2026 kam wieder mit
// der Textlatte. Yves: "Da sind immer noch die riesigen Texte." Deshalb steht das Format jetzt
// hier, als optionale Felder je Befund:
//
//   facts     kurze Zeilen mit Label (WARUM ES ZÄHLT, URSACHE, SOFORT UMSETZBAR ...)
//   proof     der Beleg als Bild: Kennzahlen, Zitate, Raster, Bildschirmaufnahmen
//   decision  zwei Wege nebeneinander, mein Vorschlag markiert, ein Satz Begründung
//
// Ein Befund mit `decision` bekommt eine eigene Seite, einer ohne bleibt kompakt und bricht nie
// in sich. Der alte Fließtext (body, recommendation, impact, evidence) geht nicht verloren: er
// steht unter "+ Herleitung und Belege", im PDF zugeklappt, im Portal aufklappbar. Ein Befund
// ganz ohne die neuen Felder rendert wie bisher, alte content.json bleiben also gültig.

const MIME_BY_EXT = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', gif: 'image/gif', svg: 'image/svg+xml' };
const imageCache = new Map();

export const hasDecisionFormat = (f) => Boolean(f && (f.decision || (Array.isArray(f.facts) && f.facts.length) || f.proof));

// Bilder werden als data:-URI eingebettet. Die HTML-Datei bleibt damit in sich vollständig, wenn
// sie ins Portal geladen oder aus dem Lauf-Ordner kopiert wird; ein relativer Pfad auf die
// Screenshots im Material zeigte danach ins Leere. Relative Pfade gelten ab dem Ordner der
// content.json. Fehlt die Datei, steht der Alternativtext da und eine Zeile geht auf stderr.
function imageUri(src, ctx) {
  if (!src) return '';
  if (/^(data:|https?:)/i.test(src)) return src;
  const path = isAbsolute(src) ? src : join(ctx.baseDir || process.cwd(), src);
  if (imageCache.has(path)) return imageCache.get(path);
  const mime = MIME_BY_EXT[extname(path).slice(1).toLowerCase()];
  let uri = '';
  try {
    if (!mime) throw new Error('unbekanntes Bildformat');
    uri = `data:${mime};base64,${readFileSync(path).toString('base64')}`;
  } catch (err) {
    ctx.warn?.(`Belegbild nicht lesbar, Alternativtext steht an seiner Stelle: ${path} (${err.message})`);
  }
  imageCache.set(path, uri);
  return uri;
}

// Zitate dürfen zusätzlich zu safeHtml eine Ergänzung (<ins>, blau) und eine Abweichung (<mark>,
// rot) zeigen, etwa den vorgeschlagenen Halbsatz in einem bestehenden Satz der Website.
const quoteHtml = (s) => safeHtml(s).replace(/&lt;(\/?)(ins|mark)&gt;/gi, '<$1$2>');

const pct = (n) => `${Math.max(0, Math.min(100, Number(n) || 0))}%`;

function ringsHtml(rings) {
  return (rings || []).map((r) => `<div class="fx-ring" style="left:${pct(r.left)};top:${pct(r.top)};width:${pct(r.width)};height:${pct(r.height)}"></div>`).join('');
}

const GRID_STATES = { both: 'gg-both', brand: 'gg-brand', other: 'gg-other', domain: 'gg-domain', none: 'gg-none' };

function gridCell(state) {
  if (state === 'x') return '<span class="fx-x">✕</span>';
  if (state === 'check') return '<span class="fx-check">✓</span>';
  return `<span class="ggdot ${GRID_STATES[state] || 'gg-none'}"></span>`;
}

function proofBlock(b, ctx) {
  if (!b || typeof b !== 'object') return '';
  switch (b.type) {
    case 'metric':
      return `<div class="fx-kv"><div class="fx-kvn">${esc(String(b.value ?? ''))}${b.unit ? ` <small>${esc(b.unit)}</small>` : ''}</div>${b.label ? `<div class="fx-kvl">${safeHtml(b.label)}</div>` : ''}</div>`;
    case 'note':
      return `<div class="fx-note">${safeHtml(b.text)}</div>`;
    case 'quote':
      return `<div class="fx-quote">${quoteHtml(b.text)}</div>${b.source ? `<div class="fx-qsrc">${esc(b.source)}</div>` : ''}`;
    case 'chips':
      return (b.groups || []).map((g) => `<div class="fx-srcg">${g.label ? `<div class="fx-gl">${esc(g.label)}</div>` : ''}${(g.items || []).map((it) => {
        const item = typeof it === 'string' ? { text: it } : it || {};
        return `<span class="fx-chip${item.own || g.own ? ' fx-chip--own' : ''}">${esc(item.text)}</span>`;
      }).join('')}</div>`).join('');
    case 'rows':
      return (b.rows || []).map((r) => `<div class="fx-vrow"><span class="fx-vk">${esc(r.label)}${r.sub ? `<small>${esc(r.sub)}</small>` : ''}</span>${r.quote ? `<span class="fx-quote">${quoteHtml(r.quote)}</span>` : `<span class="fx-vv">${safeHtml(r.text)}</span>`}</div>`).join('');
    case 'pairs':
      return `<table class="fx-pairs"><tbody>${(b.rows || []).map((r) => `<tr><td>${esc(r.from)}</td><td class="fx-arrow">→</td><td class="fx-to">${esc(r.to)}</td></tr>`).join('')}</tbody></table>`;
    case 'grid': {
      const cols = b.columns || [];
      const head = `<tr><th></th>${cols.map((c) => `<th class="mono">${esc(c)}</th>`).join('')}</tr>`;
      const rows = (b.rows || []).map((r) => `<tr><td>${esc(r.label)}</td>${(r.cells || []).map((c) => `<td class="fx-c">${gridCell(c)}</td>`).join('')}</tr>`).join('');
      const used = new Set((b.rows || []).flatMap((r) => r.cells || []));
      const legendText = { both: 'genannt, eigene Adresse als Quelle', brand: 'genannt, ohne Quellen', other: 'genannt, fremde Quellen', domain: 'nur als Quelle', none: 'nicht genannt' };
      const legend = b.legend === false ? '' : Object.keys(legendText).filter((k) => used.has(k)).map((k) => `<span>${gridCell(k)}${legendText[k]}</span>`).join('');
      return `<table class="fx-grid"><thead>${head}</thead><tbody>${rows}</tbody></table>${legend ? `<div class="fx-gleg">${legend}</div>` : ''}`;
    }
    case 'dist': {
      const total = Number(b.total) || (b.parts || []).reduce((s, p) => s + (Number(p.value) || 0), 0) || 1;
      const tone = (t) => (t === 'bad' ? 'var(--accent-deep)' : t === 'good' ? 'var(--blue)' : 'rgba(31,63,143,.45)');
      const bars = (b.parts || []).map((p) => `<span style="width:${((Number(p.value) || 0) / total * 100).toFixed(1)}%;background:${tone(p.tone)}"></span>`).join('');
      const legend = (b.parts || []).map((p) => `<span><i style="background:${tone(p.tone)}"></i>${esc(p.label)}</span>`).join('');
      return `<div class="fx-dist">${bars}</div><div class="fx-dlegend">${legend}</div>`;
    }
    case 'image': {
      const uri = imageUri(b.src, ctx);
      const img = uri ? `<img src="${esc(uri)}" alt="${esc(b.alt || '')}">` : `<div class="fx-missing">${esc(b.alt || b.src || 'Bild fehlt')}</div>`;
      // `addition` ist die vorgeschlagene Ergänzung direkt unter dem Ausschnitt, etwa die
      // fehlende Zeile unter einer Preisangabe.
      const addition = b.addition ? `<div class="fx-addl">${safeHtml(b.addition)}</div>` : '';
      return `<div class="fx-shot">${img}${ringsHtml(b.rings)}${addition}</div>${b.caption ? `<div class="fx-note">${safeHtml(b.caption)}</div>` : ''}`;
    }
    case 'phone': {
      // Ein Ausschnitt aus einer Ganzseiten-Aufnahme vom Handy: die Erstansicht hell, alles
      // darunter abgedunkelt, an der Seite die Messpunkte. Alle Angaben in CSS-Pixeln der Seite.
      const shown = 112;
      const scale = shown / (Number(b.width) || 390);
      const height = Math.round((Number(b.height) || 1700) * scale);
      const fold = Number(b.fold) || 0;
      const uri = imageUri(b.src, ctx);
      const img = uri ? `<img src="${esc(uri)}" alt="${esc(b.alt || '')}">` : `<div class="fx-missing">${esc(b.alt || b.src || 'Bild fehlt')}</div>`;
      const marks = (b.markers || []).map((m) => `<div class="fx-pmk" style="top:${Math.round((Number(m.y) || 0) * scale)}px"><b>${esc(m.label)}</b>${esc(m.text || '')}</div>`).join('');
      return `<div class="fx-stack" style="height:${height}px"><div class="fx-phone" style="height:${height}px">${img}${fold ? `<div class="fx-shade" style="top:${Math.round(fold * scale)}px"></div><div class="fx-fold" style="top:${Math.round(fold * scale)}px"></div>` : ''}</div>${marks}</div>`;
    }
    default:
      ctx.warn?.(`Unbekannter Belegtyp im Befund, ausgelassen: ${String(b.type)}`);
      return '';
  }
}

function proofLayout(p) {
  const columns = (Array.isArray(p) ? p : p?.columns || []).filter(Boolean);
  const firstIsPhone = columns[0]?.blocks?.[0]?.type === 'phone';
  return { columns, layout: p?.layout || (columns.length === 1 ? 'wide' : firstIsPhone ? 'phone' : 'split') };
}

// Im Handy-Layout stehen die Fakten rechts neben dem schmalen Ausschnitt, nicht darunter: der
// Ausschnitt ist so hoch wie zweieinhalb Bildschirme, und darunter passte die Entscheidung nicht
// mehr auf die Seite.
function proofHtml(p, ctx, tail = '') {
  if (!p) return '';
  const { columns, layout } = proofLayout(p);
  if (!columns.length) return '';
  const cols = columns.map((c, i) => `<div>${c.label ? `<div class="fx-plbl mono">${esc(c.label)}</div>` : ''}${(c.blocks || []).map((b) => proofBlock(b, ctx)).join('')}${i === columns.length - 1 ? tail : ''}</div>`).join('');
  return `<div class="fx-proof fx-proof--${esc(layout)}">${cols}</div>`;
}

// Labels je Art eines Fakts (reference/finding-format.md). `kind` geht vor einem
// freien `label`: so legt jede Oberfläche ihr eigenes Wort fest, das Portal
// etwa "Auswirkung" statt "WARUM ES ZÄHLT".
const FACT_LABEL = {
  effect: 'WARUM ES ZÄHLT',
  cause: 'URSACHE',
  present: 'VORHANDEN',
  open: 'OFFEN',
  next: 'NÄCHSTER SCHRITT',
};

function factsHtml(facts) {
  if (!Array.isArray(facts) || !facts.length) return '';
  return `<div class="fx-facts">${facts.map((r) => {
    const label = FACT_LABEL[r.kind] || r.label || (r.now ? 'SOFORT UMSETZBAR' : '');
    return `<div class="fx-fact"><div class="fx-fk mono${r.now ? ' fx-fk--now' : ''}">${esc(label)}</div><div class="fx-fv">${safeHtml(r.text)}</div></div>`;
  }).join('')}</div>`;
}

const recommendedIndex = (dec) => (dec.recommended === 1 || dec.recommended === 'b' || dec.recommended === 'B' ? 1 : 0);

function decisionHtml(dec, ctx) {
  if (!dec || !Array.isArray(dec.options) || dec.options.length < 2) return '';
  const rec = recommendedIndex(dec);
  const opts = dec.options.slice(0, 2).map((o, i) => {
    const letter = 'AB'[i];
    const meta = [['AUFWAND', o.effort], ['ERGEBNIS', o.result]].filter(([, v]) => v);
    return `<div class="fx-opt${i === rec ? ' fx-opt--rec' : ''}">
        <div class="fx-ol mono">${letter}${i === rec ? ' · MEIN VORSCHLAG' : ''}</div>
        <div class="fx-ot">${esc(o.title)}</div>
        ${o.image ? proofBlock(o.image, ctx) : ''}
        ${o.text ? `<div class="fx-od">${safeHtml(o.text)}</div>` : ''}
        ${meta.length ? `<dl>${meta.map(([k, v]) => `<dt class="mono">${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : ''}
      </div>`;
  }).join('');
  return `<div class="fx-dblock">
      <div class="fx-dhead mono">ENTSCHEIDUNG</div>
      <div class="fx-dq">${esc(dec.question)}</div>
      <div class="fx-opts">${opts}</div>
      ${dec.reason ? `<div class="fx-why">${safeHtml(dec.reason)}</div>` : ''}
    </div>`;
}

// Der ausführliche Text des Befunds, zugeklappt. Im PDF steht nur die Zeile, im Portal lässt er
// sich aufklappen. Der Beleg (evidence) steht hier zum ersten Mal im Report selbst.
function derivationHtml(f) {
  const parts = [
    f.body ? `<div class="ftext">${safeHtml(f.body)}</div>` : '',
    f.recommendation ? `<div class="frec"><span class="mono frec-lbl">EMPFEHLUNG</span> ${esc(f.recommendation)}</div>` : '',
    f.impact ? `<div class="fimpact"><span class="mono">Wirkung</span> ${esc(f.impact)}</div>` : '',
    f.evidence ? `<div class="frec"><span class="mono frec-lbl">BELEG</span> ${esc(f.evidence)}</div>` : '',
  ].join('');
  if (!parts) return '';
  return `<details class="fx-more"><summary class="mono">+ Herleitung und Belege</summary><div class="fx-more-body">${parts}</div></details>`;
}

function decisionCard(f, i, ctx) {
  const dot = SEVERITY_COLOR[f.severity] || SEVERITY_COLOR.info;
  const label = SEVERITY_LABEL[f.severity];
  const kind = f.decision ? 'fx-card fx-card--decision' : 'fx-card fx-card--compact';
  return `<div class="${kind}">
    <div class="fsev" style="background:${dot}"></div>
    <div class="fbody">
      <div class="fhead"><span class="fnum mono">Befund ${String(i + 1).padStart(2, '0')}</span>${label ? `<span class="fbadge fbadge--${esc(f.severity)} mono">${esc(label)}</span>` : ''}</div>
      <div class="ftitle fx-title">${esc(f.title)}</div>
      ${f.proof && proofLayout(f.proof).layout === 'phone'
        ? proofHtml(f.proof, ctx, factsHtml(f.facts))
        : `${proofHtml(f.proof, ctx)}${factsHtml(f.facts)}`}
      ${decisionHtml(f.decision, ctx)}
      <div class="fx-foot">${f.url ? `<a class="floc mono" href="${esc(f.url)}">↗ zur Stelle ansehen</a>` : ''}${derivationHtml(f)}</div>
    </div>
  </div>`;
}

const PILLAR_SHORT = { found: 'AKQUISITION', convince: 'CRO', trust: 'TRUST' };

// Alle Entscheidungen des Reports in der Reihenfolge, in der sie in den Kapiteln stehen. Gezählt
// werden nur die ausführlichen Befunde (topN), denn nur dort rendert die Entscheidung.
export function collectDecisions(chapters) {
  const out = [];
  (chapters || []).forEach((ch) => {
    (ch.findings || []).slice(0, ch.topN ?? 4).forEach((f, i) => {
      if (f?.decision?.options?.length >= 2) {
        out.push({ finding: f, source: `${PILLAR_SHORT[ch.pillar] || String(ch.pillar || '').toUpperCase()} · BEFUND ${String(i + 1).padStart(2, '0')}` });
      }
    });
  });
  return out;
}

const COUNT_WORDS = ['null', 'eine', 'zwei', 'drei', 'vier', 'fünf', 'sechs', 'sieben', 'acht', 'neun', 'zehn', 'elf', 'zwölf'];
const countWord = (n) => COUNT_WORDS[n] ?? String(n);
const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// "Nicht verfolgen" zieht von der Strategieseite auf die Entscheidungsseite. Vorrang hat
// decisions.avoid ({title, text}); sonst die passende Spalte aus triage, deren Einträge als
// "Titel: Satz" geschrieben sind.
function avoidItems(d) {
  if (Array.isArray(d.decisions?.avoid)) return d.decisions.avoid;
  const col = (d.triage?.columns || []).find((c) => /NICHT|IGNOR/i.test(c.label || ''));
  return (col?.items || []).map((it) => {
    const s = String(it);
    const cut = s.indexOf(': ');
    return cut > 0 ? { title: s.slice(0, cut), text: s.slice(cut + 2) } : { title: s, text: '' };
  });
}

function decisionsSection(d, head, decisions) {
  const total = (d.chapters || []).reduce((s, ch) => s + (ch.findings || []).length, 0);
  const n = decisions.length;
  const heading = d.decisions?.headline || (n === 1 ? 'Eine Entscheidung aus dem Audit' : `${capitalize(countWord(n))} Entscheidungen aus dem Audit`);
  const lead = d.decisions?.lead || `Aus den ${total} Befunden ${n === 1 ? 'ergibt sich eine Entscheidung' : `ergeben sich ${countWord(n)} Entscheidungen`}. Je Entscheidung stehen zwei Wege nebeneinander, mein Vorschlag ist markiert.`;
  const choice = (o, i, rec, summary) => {
    const s = summary || { title: o.title, text: o.result };
    return `<div class="fx-choice${i === rec ? ' fx-choice--rec' : ''}"><div class="fx-cl mono"><span class="fx-box"></span>${'AB'[i]}${i === rec ? ' · MEIN VORSCHLAG' : ''}</div><b>${esc(s.title)}</b>${s.text ? `<br><span class="fx-csub">${esc(s.text)}</span>` : ''}</div>`;
  };
  const rows = decisions.map(({ finding, source }, idx) => {
    const dec = finding.decision;
    const rec = recommendedIndex(dec);
    return `<div class="fx-drow"><div class="fx-no">${idx + 1}</div><div><div class="fx-q">${esc(dec.question)}</div><div class="fx-src mono">${esc(source)}</div></div>${dec.options.slice(0, 2).map((o, i) => choice(o, i, rec, dec.summary?.[i])).join('')}</div>`;
  }).join('');
  const avoid = avoidItems(d);
  const pointer = d.decisions?.pointer ?? 'Alles, was ohne Entscheidung umsetzbar ist, steht bei jedem Befund unter „Sofort umsetzbar“ und gesammelt im Fahrplan.';
  return `<section class="chapter">
  ${head}
  <div class="eyebrow2 mono">ENTSCHEIDUNGEN</div>
  <h2>${esc(heading)}<span class="dot">.</span></h2>
  <p class="fx-lead">${safeHtml(lead)}</p>
  <div class="fx-thead mono"><span>NR.</span><span>ENTSCHEIDUNG</span><span>WEG A</span><span>WEG B</span></div>
  <div class="fx-dlist">${rows}</div>
  ${avoid.length ? `<div class="eyebrow2 mono" style="margin-top:11mm">NICHT VERFOLGEN</div>
  <div class="fx-nogo">${avoid.map((a) => `<div><b>${esc(a.title)}</b>${esc(a.text || '')}</div>`).join('')}</div>` : ''}
  ${pointer ? `<div class="fx-pointer">${safeHtml(pointer)}</div>` : ''}
</section>`;
}

const PILLAR_LABEL = { found: 'AKQUISITION', convince: 'CONVERSION RATE OPTIMIERUNG', trust: 'TRUST UND COMPLIANCE', market: 'MARKT & WETTBEWERB' };

// Die Herkunftsangabe eines Kapitels: womit geprueft wurde und worauf die Zahlen
// beruhen. Sie baut Vertrauen auf, steht dafuer aber hinter dem Kapiteltext, nicht
// vor ihm: bis zum 16.09.2026 lief sie als eine lange Monospace-Zeile in Fliesstext-
// groesse direkt unter dem Intro. Yves dazu: "weil das ja viel groesser ist als der
// Text drueber, denkt man, das ist das Wichtigere, aber man kann es auch nicht
// wirklich gut lesen." Jetzt: kleiner als der Fliesstext, gedeckte Farbe, eine
// Trennlinie mit Abstand darueber, und je Eintrag eine eigene Zeile.
//
// Seit 24.09.2026 steht der Block am Kapitelende statt vor den Befunden. Er ist eine
// Quellenangabe, und vor den Befunden brach er ueber den Seitenumbruch. Yves: "Das ist ja
// so ein bisschen was wie die Quellenangabe. Das reicht am Ende des Kapitels."
//
// `skills` sind die tatsaechlich geladenen Skills, `methoden` ist die Messgrundlage.
// Beides gehoert in den Report und wird getrennt ausgewiesen, weil ein Skillname
// und ein Pruefschritt zwei verschiedene Dinge sind. Aeltere content.json-Dateien
// tragen nur `skills`, dort steht die Gruppe allein und ueber die volle Breite.
function chapterMetaHtml(ch) {
  const gruppen = [];
  if (ch.skills && ch.skills.length) gruppen.push(['GEPRÜFT MIT', ch.skills]);
  if (ch.methoden && ch.methoden.length) gruppen.push(['GRUNDLAGE', ch.methoden]);
  if (!gruppen.length) return '';
  const spalten = gruppen.map(([label, items]) => `<div class="ch-meta-col">
      <div class="ch-meta-lbl mono">${esc(label)}</div>
      ${items.map((i) => `<div class="ch-meta-item">${esc(i)}</div>`).join('')}
    </div>`).join('');
  return `<div class="ch-meta${gruppen.length === 1 ? ' ch-meta--single' : ''}">${spalten}</div>`;
}

// Der Bereichswert im Kapitelkopf. Auf Seite eins stehen die drei Werte nebeneinander,
// danach folgen 20 Seiten Befunde: wer im dritten Kapitel ankommt, weiss nicht mehr, wie
// dieser Bereich stand. Yves am 16.09.2026: *"Können wir noch den ptai score in jedes
// Kapitel integrieren. Damit man noch mal weiss, wie die einzelnen Unterpunkte scoren."*
// Dieselbe Optik wie die Saeulenkarte auf Seite eins, nur einzeilig, damit sie den
// Kapiteleinstieg nicht verdraengt.
function chapterScoreHtml(ch) {
  if (typeof ch.score !== 'number') return '';
  const score = Math.max(0, Math.min(100, ch.score));
  const target = typeof ch.target === 'number' ? Math.max(0, Math.min(100, ch.target)) : null;
  const lvl = ampelLevel(score);
  // Woraus der Wert entsteht, steht direkt unter ihm. Er rechnet 100 minus Strafpunkte je
  // Befund; ohne diese Zeile bleibt eine nackte Zahl stehen, und der Leser sucht die Erklaerung
  // in der Kachelleiste darunter, die das Gegenteil misst. Yves am 21.09.2026: *"Die Befunde und
  // Erklaerung, wie man auf die 39/100 kommt, eher oben irgendwie passend bei dem Scoring."*
  const n = Array.isArray(ch.findings) ? ch.findings.length : 0;
  const crit = Array.isArray(ch.findings) ? ch.findings.filter((f) => f.severity === 'crit').length : 0;
  const basis = n > 0
    ? `aus ${n} ${n === 1 ? 'Befund' : 'Befunden'}${crit > 0 ? `, davon ${crit} kritisch` : ''}`
    : '';
  return `<div class="chscore">
    <div class="chscore-num">
      <div class="chscore-lbl mono">PTAI E-COM SCORE</div>
      <div class="chscore-val">${score}<span class="chscore-den">/100</span></div>
      ${basis ? `<div class="chscore-src">${esc(basis)}</div>` : ''}
    </div>
    <div class="chscore-bar">
      <div class="bar"><div class="fill" style="width:${score}%;background:${lvl.color}"></div>
        ${target !== null ? `<div class="mark" style="left:${target}%"></div><div class="goal mono" style="left:${target}%">Ziel ${target}</div>` : ''}
      </div>
      ${target !== null && target > score ? `<div class="chscore-pot mono">+${target - score} PUNKTE NACH UMSETZUNG DER MASSNAHMEN IN DIESEM KAPITEL</div>` : ''}
    </div>
  </div>`;
}

// Was in diesem Bereich nachweislich traegt, als Zahlenleiste statt als Textblock.
// Bis zum 16.09.2026 standen die belegten Stärken als gleich lange Befundbloecke
// zwischen den Maengeln, mit demselben Gewicht und derselben Textmenge. Yves dazu:
// *"Das ist viel zu viel Text. Können wir da nicht noch mit weiteren visuellen
// Elementen arbeiten. Also vielleicht grafisch anzeigen, was schon funktioniert."*
// Jede Kachel traegt eine gemessene Zahl; ein Eintrag ohne Zahl gehoert nicht hierher,
// sondern bleibt ein Befund.
// Die Leiste zeigt wieder ausschliesslich, was traegt. Die Gegenseite, also woraus der
// Bereichswert entsteht, stand am 21.09.2026 kurz als fuenfte Kachel hier und ist von dort
// nach oben unter die Score-Zahl gewandert: sie erklaert den Wert und gehoert deshalb an den
// Wert, nicht in eine Reihe, die etwas anderes misst. Yves dazu: *"Jetzt ist aber viel in
// einer Spalte, und vielleicht sollten wir die Befunde und Erklaerung eher oben bei dem
// Scoring."*
function signalsHtml(signals) {
  if (!signals || !signals.length) return '';
  const cells = signals.map((s) => `<div class="sig">
      <div class="sigval">${esc(String(s.value))}${s.unit ? `<span class="sigunit">${esc(s.unit)}</span>` : ''}</div>
      <div class="siglbl">${esc(s.label)}</div>
    </div>`).join('');
  return `<div class="sigwrap">
    <div class="sighead mono">WAS HIER TRÄGT</div>
    <div class="sigrow">${cells}</div>
  </div>`;
}

// Anteilsbalken. Eine Zahl wie "759 von 765" ist im Fliesstext eine Behauptung, die
// der Leser nachrechnen muss; als Balken ist sie auf einen Blick eingeordnet. Der
// Balken zeigt IMMER Zaehler und Nenner im Klartext daneben, damit die Grafik nichts
// verbirgt und der Wert zitierbar bleibt.
function barsHtml(bars, title) {
  if (!bars || !bars.length) return '';
  const rows = bars.map((b) => {
    const anteil = b.total > 0 ? Math.max(0, Math.min(1, b.value / b.total)) : 0;
    const pct = Math.round(anteil * 100);
    const ton = b.tone === 'good' ? 'barfill--good' : b.tone === 'neutral' ? 'barfill--neutral' : 'barfill--bad';
    return `<div class="barrow">
      <div class="barlbl">${esc(b.label)}</div>
      <div class="bartrack"><div class="barfill ${ton}" style="width:${pct}%"></div></div>
      <div class="barval mono">${esc(String(b.value))} von ${esc(String(b.total))}</div>
    </div>`;
  }).join('');
  return `<div class="barwrap">
    ${title ? `<div class="barhead mono">${esc(title)}</div>` : ''}
    ${rows}
  </div>`;
}

// Das Raster der KI-Sichtbarkeit: je Frage eine Zeile, je Plattform eine Spalte.
// Der Kernbefund dieses Reports ist ein Muster ueber 27 Antworten, und ein Muster
// gehoert in ein Raster, nicht in einen Absatz. Gefuellt heisst: die Marke kam vor.
function geoGridSection(g, head) {
  const plats = g.platforms || [];
  const kopf = plats.map((p) => `<th class="ggp mono">${esc(p)}</th>`).join('');
  const gruppen = (g.groups || []).map((grp) => {
    const zeilen = (grp.rows || []).map((r) => {
      const zellen = (r.cells || []).map((c) => {
        // Die Stufe steckt in der Flaeche, nicht in einem Zeichen: ein Glyph im Kreis
        // rendert im PDF als Ring und liest sich wie ein leerer Zustand.
        // Seit 24.09.2026 ein fuenfter Zustand: 'other' heisst, die Marke wird genannt, als Quelle
        // stehen aber fremde Seiten (Haendler, Wettbewerber). Ohne ihn sah eine Plattform, die gar
        // keine Quellen ausgibt, genauso aus wie eine, die den Klick zu Otto schickt.
        const kl = c === 'brand' ? 'gg-brand' : c === 'other' ? 'gg-other' : c === 'domain' ? 'gg-domain' : c === 'both' ? 'gg-both' : 'gg-none';
        return `<td class="ggc"><span class="ggdot ${kl}"></span></td>`;
      }).join('');
      return `<tr><td class="ggq">${esc(r.query)}</td>${zellen}</tr>`;
    }).join('');
    return `<tr class="ggsep"><td class="ggglbl mono" colspan="${plats.length + 1}">${esc(grp.label)}</td></tr>${zeilen}`;
  }).join('');
  return `<div class="chapter">
  ${head}
  ${g.eyebrow ? `<div class="eyebrow2 mono">${esc(g.eyebrow)}</div>` : ''}
  <h2>${esc(g.headline || '')}</h2>
  ${g.intro ? `<p class="lead">${safeHtml(g.intro)}</p>` : ''}
  <table class="ggrid"><thead><tr><th></th>${kopf}</tr></thead><tbody>${gruppen}</tbody></table>
  <div class="gglegend">
    <span class="qleg"><span class="ggdot gg-both"></span>Marke genannt und eigene Adresse als Quelle</span>
    <span class="qleg"><span class="ggdot gg-brand"></span>Marke genannt, keine Quellen angegeben</span>
    <span class="qleg"><span class="ggdot gg-other"></span>Marke genannt, verlinkt werden andere Seiten</span>
    <span class="qleg"><span class="ggdot gg-domain"></span>nur als Quelle geführt</span>
    <span class="qleg"><span class="ggdot gg-none"></span>kommt nicht vor</span>
  </div>
  ${g.note ? `<div class="ggnote">${esc(g.note)}</div>` : ''}
</div>`;
}

function chapterSection(ch, idx, headHtml, ctx = {}) {
  const pillarLabel = PILLAR_LABEL[ch.pillar] || (ch.pillar || '').toUpperCase();
  const skillsHtml = chapterMetaHtml(ch);
  const topN = ch.topN ?? 4;
  const top = ch.findings.slice(0, topN);
  const rest = ch.findings.slice(topN);
  const restHtml = rest.length
    ? `<div class="fcompact-lbl mono">WEITERE BEFUNDE</div><div class="fcompact">${rest.map(compactFinding).join('')}</div>`
    : '';
  return `<div class="chapter">
  ${headHtml}
  <div class="eyebrow2 mono">KAPITEL ${idx + 1} · ${esc(pillarLabel)}</div>
  <h2>${esc(ch.title)}</h2>
  ${ch.about ? `<div class="ch-about">${safeHtml(ch.about)}</div>` : ''}
  ${chapterScoreHtml(ch)}
  <div class="lead ch-intro">${safeHtml(ch.intro)}</div>
  ${signalsHtml(ch.signals)}
  ${barsHtml(ch.bars, ch.barsTitle)}
  <div class="findings">${top.map((f, i) => (hasDecisionFormat(f) ? decisionCard(f, i, ctx) : findingBlock(f, i))).join('')}</div>
  ${restHtml}
  ${skillsHtml}
</div>`;
}

// ---------- new story-arc sections (all optional) ----------

function marketProfileSection(d, head) {
  const m = d.market || {};
  const p = d.profile || {};
  const callouts = (m.callouts || []).map((c) => `<div class="callout">
    <div class="cval disp">${esc(c.value)}${c.unit ? `<span class="cunit"> ${esc(c.unit)}</span>` : ''}</div>
    <div class="cbody">${safeHtml(c.body)}</div>
  </div>`).join('');
  const narrative = (m.narrative || []).map((para) => `<p class="lead">${safeHtml(para)}</p>`).join('');
  const rows = (p.rows || []).map((r) => `<div class="prow"><span class="pk mono">${esc(r.k)}</span><span class="pv">${esc(r.v)}</span></div>`).join('');
  return `<div class="chapter">
  ${head}
  ${m.eyebrow ? `<div class="eyebrow2 mono">${esc(m.eyebrow)}</div>` : ''}
  ${m.headline ? `<h2>${esc(m.headline.replace(/\s*\.\s*$/, ''))}<span class="dot">.</span></h2>` : ''}
  ${narrative}
  ${callouts ? `<div class="callouts">${callouts}</div>` : ''}
  ${p.eyebrow ? `<div class="eyebrowmini mono">${esc(p.eyebrow)}</div>` : ''}
  ${rows ? `<div class="pgrid">${rows}</div>` : ''}
  ${p.positioningLine ? `<div class="posline">${safeHtml(p.positioningLine)}</div>` : ''}
  ${p.note ? `<div class="pnote">${esc(p.note)}</div>` : ''}
</div>`;
}

function quadrantSection(d, head) {
  const p = d.positioning;
  const PL = 72, PR = 612, PT = 40, PB = 380;
  const W = PR - PL, H = PB - PT, CX = (PL + PR) / 2, CY = (PT + PB) / 2;
  const hqMap = { tl: [PL, PT], tr: [CX, PT], bl: [PL, CY], br: [CX, CY] };
  const hq = hqMap[p.highlightQuadrant] || null;
  const hl = hq ? `<rect x="${hq[0]}" y="${hq[1]}" width="${W / 2}" height="${H / 2}" fill="#E6ECFA" opacity="0.6"></rect>` : '';
  const tierFill = { self: '#E2381B', direct: '#1F3F8F', heritage: '#888780', indirect: 'none' };
  const pts = (p.points || []).map((pt) => {
    const px = PL + (pt.x || 0) * W, py = PT + (pt.y || 0) * H;
    const isSelf = pt.tier === 'self';
    const r = isSelf ? 8 : 5;
    const fill = tierFill[pt.tier] || '#1F3F8F';
    const circle = fill === 'none'
      ? `<circle cx="${px}" cy="${py}" r="${r}" fill="none" stroke="#5A5E57" stroke-width="1.4"></circle>`
      : `<circle cx="${px}" cy="${py}" r="${r}" fill="${fill}"></circle>`;
    const labelFill = pt.tier === 'indirect' ? '#5A5E57' : '#14150F';
    const labelAttr = isSelf ? `fill="${labelFill}" style="font-size:12.5px;font-weight:600"` : `fill="${labelFill}" style="font-size:11px"`;
    // Flip labels to the left for points near the right plot edge so long names don't clip off-page.
    const flip = px > PR - 140;
    const off = isSelf ? 14 : 10;
    const lblX = flip ? px - off : px + off;
    const anchorAttr = flip ? ' text-anchor="end"' : '';
    return `${circle}<text x="${lblX}" y="${py + 3}"${anchorAttr} ${labelAttr}>${esc(pt.label)}</text>`;
  }).join('');
  const ax = p.axisX || {}, ay = p.axisY || {};
  const legend = [
    [d.shop || 'Shop', '#E2381B', false],
    ['Direkte Wettbewerber', '#1F3F8F', false],
    ['Heritage', '#888780', false],
    ['Indirekt / Marktplatz', null, true],
  ].map(([lab, col, open]) => `<span class="qleg"><span class="qdot" style="${open ? 'border:1.4px solid #5A5E57' : `background:${col}`}"></span>${esc(lab)}</span>`).join('');
  return `<div class="chapter">
  ${head}
  ${p.eyebrow ? `<div class="eyebrow2 mono">${esc(p.eyebrow)}</div>` : ''}
  <h2>${esc(p.headline || '')}</h2>
  ${p.intro ? `<p class="lead">${safeHtml(p.intro)}</p>` : ''}
  <svg viewBox="0 0 640 430" width="100%" style="margin-top:8mm" role="img">
    ${hl}
    <line x1="${PL}" y1="${PT}" x2="${PL}" y2="${PB}" stroke="#14150F" stroke-width="1"></line>
    <line x1="${PL}" y1="${PB}" x2="${PR}" y2="${PB}" stroke="#14150F" stroke-width="1"></line>
    <line x1="${CX}" y1="${PT}" x2="${CX}" y2="${PB}" stroke="#14150F" stroke-opacity="0.15" stroke-width="1"></line>
    <line x1="${PL}" y1="${CY}" x2="${PR}" y2="${CY}" stroke="#14150F" stroke-opacity="0.15" stroke-width="1"></line>
    <text x="${CX}" y="30" text-anchor="middle" class="mono" fill="#5A5E57" style="font-size:9.5px">${esc(ay.top || '')}</text>
    <text x="${CX}" y="404" text-anchor="middle" class="mono" fill="#5A5E57" style="font-size:9.5px">${esc(ay.bottom || '')}</text>
    <text x="58" y="${CY}" text-anchor="middle" transform="rotate(-90 58 ${CY})" class="mono" fill="#5A5E57" style="font-size:9.5px">${esc(ax.left || '')}</text>
    <text x="626" y="${CY}" text-anchor="middle" transform="rotate(90 626 ${CY})" class="mono" fill="#5A5E57" style="font-size:9.5px">${esc(ax.right || '')}</text>
    ${pts}
  </svg>
  <div class="quad-legend">${legend}${p.note ? `<span class="qnote">${esc(p.note)}</span>` : ''}</div>
</div>`;
}

function matrixSection(d, head) {
  const m = d.matrix;
  const cols = m.columns || [];
  const headCells = cols.map((c, i) => `<td class="mh${i === 0 ? ' mself' : ''}">${esc(c)}</td>`).join('');
  const body = (m.capabilities || []).map((cap) => {
    const cells = (cap.ratings || []).map((r, i) => `<td class="mcell${i === 0 ? ' mself' : ''}">${hb(r)}</td>`).join('');
    return `<tr><td class="mcap">${esc(cap.label)}</td>${cells}</tr>`;
  }).join('');
  return `<div class="chapter">
  ${head}
  ${m.eyebrow ? `<div class="eyebrow2 mono">${esc(m.eyebrow)}</div>` : ''}
  <h2>${esc(m.headline || '')}</h2>
  ${m.intro ? `<p class="lead">${safeHtml(m.intro)}</p>` : ''}
  <table class="mtx"><thead><tr><td></td>${headCells}</tr></thead><tbody>${body}</tbody></table>
  <div class="mlegend"><span>${hb(2)} stark / führend</span><span>${hb(1)} solide / vorhanden</span><span>${hb(0)} schwach / fehlt</span></div>
  ${m.takeaway ? `<div class="mtake">${safeHtml(m.takeaway)}</div>` : ''}
</div>`;
}

// triage renders INSIDE the combined strategy+fahrplan section (no own page break), so the short
// triage and the roadmap share one well-filled page instead of two sparse ones.
function triageInner(t) {
  const cols = (t.columns || []).map((c) => `<div class="tcol">
    <div class="tlbl mono">${esc(c.label)}</div>
    <ul>${(c.items || []).map((it) => `<li>${esc(it)}</li>`).join('')}</ul>
  </div>`).join('');
  return `${t.eyebrow ? `<div class="eyebrow2 mono">${esc(t.eyebrow)}</div>` : ''}
  <h2>${esc(t.headline || '')}</h2>
  <div class="triage">${cols}</div>`;
}

function leversSection(l, head, tail = '') {
  const pillClass = (r) => ({ OFFEN: 'pill-open', 'TEILWEISE': 'pill-part', VORREITER: 'pill-lead' }[(r || '').toUpperCase()] || 'pill-part');
  const rows = (l.rows || []).map((r) => `<tr>
    <td class="lh">${esc(r.hebel)}</td>
    <td>${esc(r.wirkung)}</td>
    <td><span class="pill ${pillClass(r.reife)} mono">${esc(r.reife)}</span></td>
  </tr>`).join('');
  return `<div class="chapter">
  ${head}
  ${l.eyebrow ? `<div class="eyebrow2 mono">${esc(l.eyebrow)}</div>` : ''}
  <h2>${esc(l.headline || '')}</h2>
  ${l.intro ? `<p class="lead">${safeHtml(l.intro)}</p>` : ''}
  <table class="lev"><thead><tr><th>HEBEL</th><th>WIRKUNG</th><th>STAND HEUTE</th></tr></thead><tbody>${rows}</tbody></table>${tail}
</div>`;
}

function sourcesSection(s, head, tail = '') {
  const groups = (s.groups || []).map((g) => `<div class="srcgroup">
    <div class="sgt mono">${esc(g.title)}</div>
    ${(g.items || []).map((it) => `<div class="srcitem"><div class="sl">${esc(it.label)}</div>${it.url ? `<div class="su">${esc(it.url)}</div>` : ''}</div>`).join('')}
  </div>`).join('');
  return `<div class="chapter">
  ${head}
  ${s.eyebrow ? `<div class="eyebrow2 mono">${esc(s.eyebrow)}</div>` : ''}
  <h2>${esc(s.headline || '')}</h2>
  <div class="srcgrid">${groups}</div>
  ${s.methodik ? `<div class="methodik">${esc(s.methodik)}</div>` : ''}${tail}
</div>`;
}

// ---------- Schluss: Schlussseite des Betreibers oder neutraler Schluss ----------
//
// Entscheidung vom 15.09.2026, zweiter Teil: jedes Dokument des Plugins endet
// mit derselben Schlussseite, auch dieser Report. Sie liegt als HTML-Datei
// außerhalb des Repos, PTAI_CLOSING_FILE zeigt darauf, und ihr Inhalt wird
// unverändert als letzte Seite eingesetzt, ohne ihn zu lesen. Ohne sie endet der
// Report mit dem neutralen Schluss aus scripts/audit/closing.py: dieselben
// Fakten und Regeln, im Satz dieses Reports. Bis dahin stand hier ein fester
// Schluss mit Porträt, Kontaktzeilen, Terminlink und Stationen eines einzelnen
// Betreibers.
//
// Gesucht wird wie in db.mjs: zuerst die Umgebung, dann die zentrale Datei aus
// PTAI_ENV_FILE, sonst ~/.config/ptai-ecom/.env. Ein leeres PTAI_ENV_FILE heißt
// "keine zentrale Datei" (`??`, nicht `||`). Einen Workspace hat audit-light
// nicht. Aufgelöst wird beim Rendern, nie beim Laden des Moduls.

const ENV_LINE = /^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$/;

/** Die Suche nach Einstellungen des Betreibers: Umgebung, dann zentrale Datei. */
export function operatorSettings(env = process.env) {
  let central = null;
  return (name) => {
    if (env[name]) return env[name];
    if (central === null) {
      central = {};
      try {
        const text = readFileSync(env.PTAI_ENV_FILE ?? join(homedir(), '.config', 'ptai-ecom', '.env'), 'utf8');
        for (const line of text.split('\n')) {
          // Umschließende Quotes weg, ein leerer Wert zählt nicht, der letzte gewinnt.
          const m = line.match(ENV_LINE);
          const value = m ? m[2].replace(/^(["'])(.*)\1$/, '$2') : '';
          if (value) central[m[1]] = value;
        }
      } catch { /* keine zentrale Datei, dann bleibt es bei der Umgebung */ }
    }
    return central[name];
  };
}

const ORIGIN_HTML = 'Erstellt mit ptai-ecom von <a href="https://path-to-ai.com">Path to AI</a>.';

// Eine Adresse der Form name@beispiel.example, wie `_EMAIL` in closing.py. Dort
// ist \w Unicode, hier deshalb \p{L}\p{N}_.
const EMAIL = /^[\p{L}\p{N}_.%+-]+@[\p{L}\p{N}_-]+(?:\.[\p{L}\p{N}_-]+)+$/u;

const settingValue = (setting, name) => String(setting(name) ?? '').trim();

// Der Terminlink, nur mit http oder https und einem Host, wie urlsplit in
// closing.py. Alles andere fällt weg statt im href zu landen, auch javascript:.
function bookingUrl(value) {
  if (!value || /\s/.test(value)) return null;
  const m = /^([A-Za-z][A-Za-z0-9+.-]*):\/\/([^/?#]*)/.exec(value);
  if (!m || !['http', 'https'].includes(m[1].toLowerCase()) || !m[2]) return null;
  if (m[2].includes('[') !== m[2].includes(']')) return null;
  return value;
}

// Sichtbarer Linktext: ohne Schema, ohne Schrägstrich am Ende.
const linkText = (url) => url.replace(/^https?:\/\//, '').replace(/\/+$/, '');

const contactRow = (label, valueHtml) =>
  `<div class="contact-row"><div class="ck mono">${label}</div><div class="cv">${valueHtml}</div></div>`;

// Eine Kontaktzeile je gesetztem und gültigem Wert, darunter immer die
// Herkunftszeile, kein Satz. Der Firmenname nur, wenn er ausdrücklich gesetzt ist.
function neutralClosing(setting, head) {
  const name = settingValue(setting, 'PTAI_OPERATOR_NAME');
  const contact = settingValue(setting, 'PTAI_OPERATOR_CONTACT');
  const email = settingValue(setting, 'PTAI_OPERATOR_EMAIL');
  const url = bookingUrl(settingValue(setting, 'PTAI_OPERATOR_BOOKING_URL'));
  const rows = [];
  if (name) rows.push(contactRow('Unternehmen', esc(name)));
  if (contact) rows.push(contactRow('Ansprechpartner', esc(contact)));
  if (EMAIL.test(email)) rows.push(contactRow('E-Mail', `<a href="mailto:${esc(email)}">${esc(email)}</a>`));
  if (url) rows.push(contactRow('Termin', `<a href="${esc(url)}">${esc(linkText(url))}</a>`));
  const contactBlock = rows.length
    ? `\n  <div class="eyebrow2 mono">Kontakt</div>\n  <div class="contact-rows">${rows.join('')}</div>`
    : '';
  return `<section class="closing">
  ${head}${contactBlock}
  <p class="fine">${ORIGIN_HTML}</p>
</section>`;
}

// Die Schlussseite aus PTAI_CLOSING_FILE, unverändert, oder null. Ist die
// Einstellung gesetzt, die Datei aber nicht brauchbar, meldet `warn` das in
// einer Zeile, und der Report bekommt den neutralen Schluss.
function closingFile(setting, warn) {
  const value = settingValue(setting, 'PTAI_CLOSING_FILE');
  if (!value) return null;
  const path = value === '~' ? homedir() : value.startsWith('~/') ? join(homedir(), value.slice(2)) : value;
  let reason;
  try {
    // fatal: eine Datei, die kein UTF-8 ist, gilt wie in closing.py als nicht lesbar.
    const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(readFileSync(path));
    if (text.trim()) return text;
    reason = 'ist leer';
  } catch (err) {
    reason = err?.code === 'ENOENT' ? 'gibt es nicht' : 'ist nicht lesbar';
  }
  warn(`Hinweis: PTAI_CLOSING_FILE zeigt auf ${value}, die Datei ${reason}. Das Dokument endet mit dem neutralen Schluss.`);
  return null;
}

// ---------- main renderer ----------

// `setting` und `warn` lassen sich für Tests ersetzen. Ohne sie gelten die
// Einstellungen zum Zeitpunkt des Renderns, und Warnungen gehen auf stderr.
export function renderReportHtml(d, { setting = operatorSettings(), warn = (message) => console.error(message), baseDir = process.cwd() } = {}) {
  const ctx = { baseDir, warn };
  // Sobald ein Befund eine Entscheidung trägt, steht hinter der Zusammenfassung die Seite
  // "Entscheidungen", und die Triage entfällt: ihr "Nicht verfolgen" zieht dorthin, "Doppelt
  // drauf setzen" und "Nachziehen" stehen schon in den Befunden und im Fahrplan.
  const decisions = collectDecisions(d.chapters);
  const head = `<div class="phead"><span class="wm">Path to AI<span class="dot">.</span></span><span class="mono vt">VERTRAULICH · FÜR ${esc(d.meta?.erstelltFuer || d.shop)}</span></div>`;

  const takeawaysList = d.exec.takeaways && d.exec.takeaways.length
    ? `<ul class="takeaways">${d.exec.takeaways.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>`
    : '';

  // Der Kleindruck steht am Ende der letzten Inhaltsseite: die Schlussseite
  // gehört dem Betreiber, und mit PTAI_CLOSING_FILE fiele er sonst weg. Das
  // Copyright nennt den Betreiber, nur wenn PTAI_OPERATOR_NAME ausdrücklich
  // gesetzt ist, sonst entfällt der Satz. Bis zum 15.09.2026 stand hier fest ein
  // einzelner Betreiber, in jedem Report jedes Betreibers.
  const operator = settingValue(setting, 'PTAI_OPERATOR_NAME');
  const copyright = operator ? ` © ${esc(d.meta?.year || '2026')} ${esc(operator)}.` : '';
  const fine = `<div class="fine">Dieser Audit basiert auf öffentlich zugänglichen Daten von ${esc(d.shop)} (Stand ${esc(d.meta?.stand || '')}) und mehreren strukturierten Audits: SEO, E-Commerce, KI-Sichtbarkeit/GEO und Wettbewerb. Mit „~"/„Schätzung" markierte Werte sind Orientierung, keine geprüften Zahlen. Die Scores sind Orientierung, keine Garantie.${copyright}</div>`;
  const last = d.sources ? 'sources' : d.levers ? 'levers' : 'fahrplan';
  const closing = closingFile(setting, warn) ?? neutralClosing(setting, head);

  // Der Dokumenttitel wandert beim Druck in die PDF-Metadaten und ist das, was ein Empfaenger
  // im Reader-Tab und in der Dateivorschau sieht. Ohne ihn stand dort bis zum 21.09.2026 nur
  // "Chromium", auch in der Fassung, die an einen Kunden geht.
  const docTitle = `E-Commerce-Audit ${d.meta?.erstelltFuer || d.shop || ''}`.trim()
    + (d.meta?.stand ? ` · ${d.meta.stand}` : '');

  return `<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>${esc(docTitle)}</title>
<style>
${FONT_FACE_CSS}

/* ---- PRINT / PAGE SETUP ---- */
@page { size: A4; margin: 0; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; margin: 0; }

/* ---- DESIGN TOKENS (Styleguide von Path to AI: weisser Grund, ein lautes Rot, ein ruhiges Blau) ---- */
:root {
  --paper: #FFFFFF;
  --ink:   #14150F;
  --ink-80: rgba(20,21,15,.80);
  --ink-soft: #5A5E57;
  --accent: #E2381B;        /* laut: grosse Typo, Marker, Flächen ohne Kleintext */
  --accent-deep: #C62F14;   /* Buttons, Links, Kleintext */
  --blue: #1F3F8F;          /* ruhig: Labels, Links, positive Signale */
  --blue-wash: #E6ECFA;     /* Callout-Flächen */
  --line: rgba(20,21,15,.13);
}
html, body { font-family: 'Inter', system-ui, sans-serif; color: var(--ink); background: var(--paper); }
.disp  { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; letter-spacing: -0.02em; }
.mono  { font-family: 'JetBrains Mono', monospace; }
code   { font-family: 'JetBrains Mono', monospace; font-size: .9em; background: rgba(31,63,143,.08); color: var(--blue); padding: .05em .35em; border-radius: 3px; }
.dot   { color: var(--accent); }
.wm    { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; font-style: italic; text-transform: uppercase; letter-spacing: -0.015em; }

/* ---- COVER — full-bleed dark page ---- */
.cover { width: 210mm; height: 297mm; padding: 20mm 18mm; position: relative; overflow: hidden; page-break-after: always; background: var(--ink); color: var(--paper); }
.cover .wm { font-size: 21px; color: var(--paper); }
.cover .eyebrow { display: flex; align-items: center; gap: 14px; margin-top: 120mm; font-size: 11px; letter-spacing: .22em; color: rgba(255,255,255,.7); }
.cover .eyebrow .ln { width: 34px; height: 2px; background: var(--accent); }
.cover h1 { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; font-style: italic; letter-spacing: -0.02em; font-size: 44px; line-height: 1.02; margin-top: 14px; color: var(--paper); }
.cover .intro { font-size: 16px; line-height: 1.55; color: rgba(255,255,255,.82); max-width: 128mm; margin-top: 20px; }
.cover .ghost { position: absolute; right: -16mm; bottom: -42mm; font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; font-style: italic; font-size: 400px; line-height: 1; color: rgba(255,255,255,.09); }
.cover .meta { position: absolute; left: 18mm; right: 18mm; bottom: 18mm; display: flex; gap: 24px; border-top: 1px solid rgba(255,255,255,.18); padding-top: 14px; }
.cover .meta .mb { flex: 1; }
.cover .meta .mk { font-size: 9.5px; letter-spacing: .18em; color: rgba(255,255,255,.55); }
.cover .meta .mv { font-size: 13px; color: var(--paper); margin-top: 6px; }

/* ---- SECTION HEADER ---- */
.phead { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid rgba(20,21,15,.12); padding-bottom: 8px; }
.phead .wm { font-size: 15px; color: var(--ink); }
.phead .vt { font-size: 10px; letter-spacing: .16em; color: var(--ink-soft); }

/* ---- FLOWING SECTIONS ---- */
.section, .chapter { padding: 16mm 16mm 14mm; -webkit-box-decoration-break: clone; box-decoration-break: clone; }
.chapter { page-break-before: always; }
.fcard, .scol, .stage, .proj, .callout, .tcol, .srcgroup, .sigwrap, .barwrap, .ggrid, .chscore { break-inside: avoid; }
svg { break-inside: avoid; }

/* ---- TYPOGRAPHY ---- */
.eyebrow2 { font-size: 10.5px; letter-spacing: .18em; color: var(--blue); margin-top: 8mm; }
h2 { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; font-style: italic; letter-spacing: -0.02em; font-size: 27px; line-height: 1.06; color: var(--ink); margin-top: 10px; }
.lead { font-size: 14px; line-height: 1.6; color: var(--ink-80); margin-top: 14px; }
.lead .hl, .ch-intro .hl { color: var(--ink); font-weight: 500; }
/* Was der Bereich ist und was geprueft wurde, vor dem Score. Seit 24.09.2026, Yves: "Was ist das
   eigentlich? Was wird in der Sektion ausgegeben? Was wurde hier geprueft?" */
.ch-about { font-size: 12.5px; line-height: 1.6; color: var(--ink-80); margin: 4mm 0 8mm; max-width: 165mm; }

/* ---- KAPITEL-HERKUNFT (geprueft mit / Grundlage) ----
   Tritt hinter den Kapiteltext zurueck: 11px gegen 14px im Fliesstext, gedeckte
   Farbe, Trennlinie mit 9mm Abstand nach oben. Je Eintrag eine eigene Zeile. */
.ch-meta { break-inside: avoid; margin-top: 7mm; padding-top: 10px; border-top: 1px solid var(--line);
           display: grid; grid-template-columns: 1fr 2fr; gap: 0 26px; }
.ch-meta--single { grid-template-columns: 1fr; }
.ch-meta-lbl { font-size: 9px; letter-spacing: .16em; color: var(--ink-soft); margin-bottom: 7px; }
.ch-meta-item { font-size: 11px; line-height: 1.5; color: var(--ink-soft); margin-bottom: 3px; }

/* ---- EXECUTIVE SCORES ---- */
.scores { display: flex; gap: 10mm; margin-top: 16mm; }
.scol { flex: 1; }
.scol .lbl { font-size: 10px; letter-spacing: .12em; color: var(--ink-soft); border-top: 2px solid var(--ink); padding-top: 10px; }
.scol .num { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; letter-spacing: -0.02em; font-size: 44px; color: var(--ink); line-height: 1; margin-top: 8px; }
.scol .den { font-size: 18px; color: var(--ink-soft); }
.bar { position: relative; height: 6px; background: rgba(20,21,15,.10); margin-top: 18px; }
.bar .fill { height: 100%; background: var(--blue); }
.bar .mark { position: absolute; top: -3px; width: 2px; height: 12px; background: var(--accent-deep); transform: translateX(-1px); }
.bar .goal { position: absolute; top: -18px; font-size: 9px; color: var(--accent-deep); transform: translateX(-50%); white-space: nowrap; }
.scol .cap { font-size: 12.5px; line-height: 1.5; color: var(--ink-soft); margin-top: 14px; }

/* ---- POTENZIAL-VARIANTE (exec.scoreStyle === 'potenzial') + STÄRKEN ---- */
.pot { font-size: 9px; letter-spacing: .14em; color: var(--blue); margin-top: 8px; }
.sgrid { display: flex; gap: 8mm; margin-top: 6mm; break-inside: avoid; }
.sitem { flex: 1; font-size: 12.5px; line-height: 1.5; color: var(--ink); border-top: 2px solid var(--blue); padding-top: 10px; }
.scheck { color: var(--blue); font-weight: 600; margin-right: 6px; }
.cto { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; letter-spacing: -0.015em; font-size: 21px; color: var(--blue); line-height: 1.1; }

/* ---- AMPEL-VARIANTE (exec.scoreStyle === 'ampel') ---- */
.ampel { display: flex; gap: 8px; align-items: center; margin-top: 16px; }
.ampel .ad { border-radius: 50%; display: inline-block; box-sizing: border-box; }
.ampel .ad.on { transform: scale(1.3); }
.aword { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; letter-spacing: -0.015em; font-size: 22px; color: var(--ink); line-height: 1.1; margin-top: 10px; }
.agoal { font-size: 9px; letter-spacing: .14em; color: var(--ink-soft); margin-top: 8px; }
.composite .ampel { margin-top: 0; }

/* ---- COMPOSITE SCORE ---- */
.composite { display: flex; align-items: baseline; gap: 16px; margin-top: 16mm; border-top: 2px solid var(--ink); padding-top: 14px; }
.composite .cnum { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; letter-spacing: -0.02em; font-size: 50px; color: var(--ink); line-height: .9; }
.composite .cden { font-size: 22px; color: var(--ink-soft); }
.composite .clbl { font-size: 10px; letter-spacing: .14em; color: var(--ink-soft); line-height: 1.5; text-transform: uppercase; }

/* ---- TAKEAWAYS ---- */
.takeaways { list-style: none; padding: 0; margin-top: 12mm; }
.takeaways li { font-size: 13px; line-height: 1.55; color: var(--ink-80); padding-left: 18px; position: relative; margin-bottom: 10px; }
.takeaways li:before { content: ''; position: absolute; left: 0; top: 7px; width: 6px; height: 6px; background: var(--accent-deep); border-radius: 50%; }

/* ---- MARKET CALLOUTS (Hauptpotenziale) ---- */
.callouts { display: flex; gap: 8mm; margin-top: 14mm; }
.callout { flex: 1; border-top: 2px solid var(--accent-deep); padding-top: 12px; }
.callout .cval { font-size: 30px; line-height: 1; color: var(--ink); }
.callout .cunit { font-size: 15px; color: var(--ink-soft); }
.callout .cbody { font-size: 12px; line-height: 1.5; color: var(--ink-80); margin-top: 8px; }
.callout .cbody b { color: var(--ink); }

/* ---- PROFILE / COMPANY CARD ---- */
.eyebrowmini { font-size: 10px; letter-spacing: .16em; color: var(--blue); margin-top: 16mm; }
.pgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14mm; margin-top: 10px; }
.prow { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; border-bottom: .5px solid rgba(20,21,15,.14); padding: 9px 0; }
.prow .pk { letter-spacing: .10em; font-size: 9.5px; color: var(--ink-soft); white-space: nowrap; }
.prow .pv { font-size: 12.5px; color: var(--ink); text-align: right; }
.posline { background: var(--blue-wash); padding: 12px 16px; margin-top: 14px; font-size: 13px; line-height: 1.5; color: var(--ink); }
.posline b { font-weight: 600; }
.pnote { font-size: 9px; color: var(--ink-soft); margin-top: 12px; }

/* ---- QUADRANT ---- */
.quad-legend { display: flex; flex-wrap: wrap; gap: 14px; border-top: .5px solid rgba(20,21,15,.12); padding-top: 10px; margin-top: 6px; align-items: center; }
.qleg { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--ink-80); }
.qdot { width: 10px; height: 10px; border-radius: 50%; }
.qnote { font-size: 9.5px; color: var(--ink-soft); margin-left: auto; }

/* ---- COMPARISON MATRIX ---- */
.mtx { width: 100%; border-collapse: collapse; margin-top: 10mm; table-layout: fixed; }
.mtx td { padding: 11px 0; }
.mtx thead .mh { font-size: 9.5px; letter-spacing: .08em; color: var(--ink-soft); text-align: center; }
.mtx .mself { background: rgba(226,56,27,.06); }
.mtx .mcap { font-size: 12.5px; color: var(--ink); padding-right: 8px; width: 32%; }
.mtx tbody tr { border-top: .5px solid rgba(20,21,15,.12); }
.mtx .mcell { text-align: center; }
.mlegend { display: flex; gap: 18px; margin-top: 12px; font-size: 10px; color: var(--ink-soft); align-items: center; }
.mlegend span { display: flex; align-items: center; gap: 6px; }
.mtake { background: var(--blue-wash); padding: 14px 18px; margin-top: 12mm; font-size: 13px; line-height: 1.55; color: var(--ink); }
.mtake b { color: var(--blue); }

/* ---- STRATEGY TRIAGE ---- */
.triage { display: flex; gap: 8mm; margin-top: 12mm; }
.tcol { flex: 1; }
.tcol + .tcol { border-left: 1px solid rgba(20,21,15,.12); padding-left: 8mm; }
.tcol .tlbl { font-size: 10px; letter-spacing: .12em; color: var(--blue); }
.tcol ul { list-style: none; margin-top: 14px; }
.tcol li { font-size: 12px; line-height: 1.45; color: var(--ink-80); padding-left: 14px; position: relative; margin-bottom: 11px; }
.tcol li:before { content: ''; position: absolute; left: 0; top: 7px; width: 5px; height: 5px; background: var(--accent-deep); }

/* ---- AI LEVERS ---- */
.lev { width: 100%; border-collapse: collapse; margin-top: 10mm; }
.lev th { text-align: left; font-size: 9.5px; letter-spacing: .10em; color: var(--ink-soft); font-weight: 400; padding-bottom: 8px; border-bottom: 1px solid rgba(20,21,15,.12); }
.lev td { padding: 13px 0; border-bottom: .5px solid rgba(20,21,15,.12); font-size: 12.5px; color: var(--ink-80); vertical-align: top; }
.lev td:nth-child(2) { padding-left: 8px; padding-right: 8px; }
.lev .lh { font-weight: 500; color: var(--ink); }
.pill { display: inline-block; font-size: 9px; letter-spacing: .08em; padding: 4px 9px; border-radius: 3px; white-space: nowrap; }
.pill-open { background: rgba(226,56,27,.10); color: var(--accent-deep); }
.pill-part { background: rgba(20,21,15,.06); color: var(--ink-soft); }
.pill-lead { background: rgba(31,63,143,.10); color: var(--blue); }

/* ---- SOURCES & METHODOLOGY ---- */
.srcgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 8mm 12mm; margin-top: 10mm; }
.srcgroup .sgt { font-size: 9.5px; letter-spacing: .10em; color: var(--blue); border-bottom: 1px solid rgba(20,21,15,.12); padding-bottom: 6px; }
.srcitem { padding: 8px 0; border-bottom: .5px solid rgba(20,21,15,.10); }
.srcitem .sl { font-size: 12px; color: var(--ink); }
.srcitem .su { font-size: 9px; color: var(--ink-soft); word-break: break-all; margin-top: 3px; }
/* Der Methodik-Block steht am Fuss der Quellenseite und ist nur wenige Zeilen hoch.
   Ohne avoid reisst Chrome ihn mitten im Satz auf und schiebt zwei Zeilen auf eine
   sonst leere Folgeseite. Wie bei .roadmap gilt: passt er nicht mehr, wandert er
   ganz auf die naechste Seite. */
.methodik { font-size: 10px; line-height: 1.5; color: var(--ink-soft); margin-top: 10mm; border-top: 1px solid rgba(20,21,15,.12); padding-top: 12px; break-inside: avoid; }

/* ---- FINDING BLOCKS ---- */
.findings { margin-top: 10mm; }
.fcard { display: flex; gap: 12px; padding: 16px 0; border-top: 1px solid rgba(20,21,15,.10); break-inside: avoid; }
.fcard:last-child { border-bottom: 1px solid rgba(20,21,15,.10); }
.fsev { width: 4px; flex-shrink: 0; border-radius: 2px; align-self: stretch; min-height: 14px; }
.fbody { flex: 1; }
.fhead { display: flex; justify-content: space-between; align-items: baseline; }
.fnum { font-size: 9.5px; letter-spacing: .14em; color: var(--blue); margin-bottom: 4px; }
.fbadge { font-size: 8.5px; letter-spacing: .10em; color: var(--ink-soft); border: .5px solid rgba(20,21,15,.2); padding: 2px 8px; border-radius: 3px; }
/* Das Schwere-Badge nimmt die Farbe des Strichs links auf, damit beide als dieselbe Angabe
   lesbar sind und die Legende im Kopf des Lesers entsteht statt in einer Fussnote. */
.fbadge--crit { color: var(--accent-deep); border-color: rgba(198,47,20,.45); }
.fbadge--warn { color: var(--ink); border-color: rgba(20,21,15,.35); }
.ftitle { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; letter-spacing: -0.015em; font-size: 15.5px; line-height: 1.2; color: var(--ink); }
.ftext { font-size: 13px; line-height: 1.55; color: var(--ink-80); margin-top: 8px; }
.frec { font-size: 12.5px; line-height: 1.5; color: var(--ink); margin-top: 10px; }
.frec-lbl { font-size: 9px; letter-spacing: .14em; color: var(--ink-soft); display: block; margin-bottom: 2px; }
.fimpact { font-size: 12px; line-height: 1.5; color: var(--blue); margin-top: 8px; }
.fimpact .mono { font-size: 9.5px; letter-spacing: .12em; color: var(--ink-soft); display: block; margin-bottom: 2px; }
.fskill { font-size: 9px; letter-spacing: .10em; color: var(--ink-soft); margin-top: 6px; }
.floc { display: inline-block; font-size: 9.5px; letter-spacing: .04em; color: var(--accent-deep); text-decoration: none; margin-top: 8px; border-bottom: .5px solid rgba(198,47,20,.35); }

/* ---- COMPACT FINDINGS (the long tail) ---- */
.fcompact-lbl { font-size: 9.5px; letter-spacing: .14em; color: var(--ink-soft); margin-top: 10mm; break-after: avoid; page-break-after: avoid; }
.fcompact { margin-top: 6px; display: grid; grid-template-columns: 1fr 1fr; gap: 0 10mm; }
.fcrow { display: flex; gap: 8px; padding: 9px 0; border-top: .5px solid rgba(20,21,15,.10); break-inside: avoid; }
.fcrow .fcdot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; margin-top: 5px; }
.fcrow .fct { font-size: 11.5px; line-height: 1.35; color: var(--ink); }
.fcrow .fci { font-size: 10px; line-height: 1.4; color: var(--ink-soft); margin-top: 2px; }

/* ---- BEREICHSWERT IM KAPITELKOPF ---- */
.chscore { display: grid; grid-template-columns: 52mm 1fr; gap: 9mm; align-items: start;
           margin: 7mm 0 9mm; padding: 11px 0 13px; border-top: 2px solid var(--ink);
           border-bottom: 1px solid var(--line); break-inside: avoid; }
.chscore-lbl { font-size: 8.5px; letter-spacing: .14em; color: var(--ink-soft); }
.chscore-val { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; letter-spacing: -0.03em;
               font-size: 34px; line-height: 1; color: var(--ink); margin-top: 6px; }
.chscore-den { font-size: 15px; color: var(--ink-soft); letter-spacing: 0; }
/* Woraus der Wert entsteht, direkt unter der Zahl und bewusst klein: die Zahl bleibt das
   Element, die Herkunft ist ihre Fussnote. */
.chscore-src { font-size: 10px; line-height: 1.35; color: var(--ink-soft); margin-top: 4px; }
.chscore-bar { padding-top: 21px; }
.chscore-pot { font-size: 8.5px; letter-spacing: .1em; color: var(--blue); margin-top: 15px; }

/* ---- SIGNALE: was in diesem Bereich traegt, als Zahlenleiste ---- */
.sigwrap { margin-top: 11mm; break-inside: avoid; }
.sighead { font-size: 9px; letter-spacing: .16em; color: var(--ink-soft); margin-bottom: 9px; }
.sigrow { display: flex; gap: 7mm; }
.sig { flex: 1; border-top: 2px solid var(--blue); padding-top: 9px; break-inside: avoid; }
.sigval { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; letter-spacing: -0.02em;
          font-size: 23px; line-height: 1; color: var(--ink); }
.sigunit { font-family: 'Inter', system-ui, sans-serif; font-weight: 400; font-size: 12px;
           color: var(--ink-soft); margin-left: 5px; letter-spacing: 0; }
.siglbl { font-size: 10.5px; line-height: 1.4; color: var(--ink-80); margin-top: 7px; }

/* ---- ANTEILSBALKEN ---- */
.barwrap { margin-top: 10mm; break-inside: avoid; }
.barhead { font-size: 9px; letter-spacing: .16em; color: var(--ink-soft); margin-bottom: 10px; }
.barrow { display: grid; grid-template-columns: 62mm 1fr 26mm; align-items: center; gap: 6mm;
          padding: 5px 0; break-inside: avoid; }
.barlbl { font-size: 11px; line-height: 1.35; color: var(--ink-80); }
.bartrack { height: 7px; background: rgba(20,21,15,.08); }
.barfill { height: 7px; }
.barfill--bad { background: var(--accent-deep); }
.barfill--good { background: var(--blue); }
.barfill--neutral { background: #888780; }
.barval { font-size: 10px; color: var(--ink-soft); text-align: right; }

/* ---- RASTER DER KI-SICHTBARKEIT ---- */
.ggrid { width: 100%; border-collapse: collapse; margin-top: 12mm; break-inside: avoid; }
.ggrid th.ggp { font-size: 9px; letter-spacing: .12em; color: var(--ink-soft); text-align: center;
                padding-bottom: 8px; width: 30mm; font-weight: 400; }
.ggglbl { font-size: 9px; letter-spacing: .16em; color: var(--blue); padding: 11px 0 5px; }
.ggsep td { border-top: 1px solid rgba(20,21,15,.12); }
.ggq { font-size: 11px; line-height: 1.35; color: var(--ink-80); padding: 6px 8mm 6px 0; }
.ggc { text-align: center; padding: 6px 0; }
.ggdot { display: inline-flex; align-items: center; justify-content: center; width: 15px; height: 15px;
         border-radius: 50%; font-size: 11px; line-height: 1; }
/* Bis 24.09.2026 war der beste Zustand rot. Yves: "Marke genannt und eigene Adresse als Quelle ist ja
   das Beste. Dann wuerde ich das nicht rot machen." Rot bleibt dem Handlungsbedarf vorbehalten
   (Styleguide), die guten Zustaende laufen als Blau-Abstufung, je dunkler desto besser. */
.gg-both { background: var(--blue); }
.gg-brand { background: rgba(31,63,143,.55); }
.gg-other { background: var(--accent-deep); }
.gg-domain { background: rgba(31,63,143,.22); }
.gg-none { background: rgba(20,21,15,.07); }
.gglegend { display: flex; flex-wrap: wrap; gap: 5mm 8mm; margin-top: 9mm;
            border-top: 1px solid var(--line); padding-top: 10px; }
.ggnote { font-size: 10px; line-height: 1.5; color: var(--ink-soft); margin-top: 7px; }

/* ---- FAHRPLAN ---- */
.stages { display: flex; gap: 9mm; margin-top: 14mm; }
.stage { flex: 1; }
.stage + .stage { border-left: 1px solid rgba(20,21,15,.12); padding-left: 8mm; }
.slbl { font-size: 10px; letter-spacing: .12em; color: var(--blue); }
.stitle { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; letter-spacing: -0.015em; font-size: 16.5px; line-height: 1.15; color: var(--ink); margin-top: 8px; }
.stage ul { list-style: none; margin-top: 14px; }
.stage li { font-size: 12.5px; line-height: 1.45; color: var(--ink-80); padding-left: 14px; position: relative; margin-bottom: 11px; }
.stage li:before { content: ''; position: absolute; left: 0; top: 7px; width: 5px; height: 5px; background: var(--accent-deep); }
/* Der Fahrplan ist EINE Einheit: Überschrift, Lead, Etappen und Projektion gehören zusammen.
   Ohne diese Klammer zerlegt der Fragmentierer sie auf zwei Arten, beide gemessen über 22 Läufe:
   die Projektion landet allein auf einer sonst leeren Seite (12 Läufe), oder Überschrift und Lead
   bleiben unten auf der Vorseite stehen, während Etappen und Projektion umbrechen (6 Läufe).
   Passt die Einheit auf die laufende Seite, ändert die Klammer nichts; sonst wandert sie komplett
   auf die nächste. Ist sie höher als eine Seite, ignoriert Chrome das avoid und bricht wie bisher. */
.roadmap { break-inside: avoid; }
.proj { display: flex; gap: 24px; align-items: center; background: var(--blue-wash); padding: 20px 24px; margin-top: 14mm; break-inside: avoid; }
.proj .big { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; letter-spacing: -0.02em; font-size: 30px; color: var(--ink); white-space: nowrap; }
.proj .big .to { color: var(--accent-deep); }
.proj .plbl { font-size: 9.5px; letter-spacing: .14em; color: var(--ink-soft); margin-top: 4px; }
.proj .ptext { font-size: 13px; line-height: 1.55; color: var(--ink); }
.proj .ptext b { color: var(--blue); }

/* ---- SCHLUSS: der neutrale Schluss ohne PTAI_CLOSING_FILE, eine eigene Seite mit
   den Kontaktzeilen des Betreibers und darunter der Herkunftszeile ---- */
.closing { page-break-before: always; background: var(--paper); padding: 16mm 16mm 14mm; }
.closing .eyebrow2 { text-transform: uppercase; }
.contact-rows { margin-top: 6mm; max-width: 120mm; }
.contact-row { border-top: 1px solid var(--line); padding: 9px 0; }
.ck { font-size: 9px; letter-spacing: .16em; color: var(--ink-soft); text-transform: uppercase; }
.cv { font-size: 13px; color: var(--ink); margin-top: 3px; }
.cv a { color: inherit; text-decoration: none; }
/* Kleindruck: der Hinweis zur Datengrundlage am Ende der letzten Inhaltsseite und
   die Herkunftszeile im neutralen Schluss. */
.fine { font-size: 9px; line-height: 1.5; color: var(--ink-soft); margin-top: 4mm; border-top: 1px solid var(--line); padding-top: 8px; break-inside: avoid; }
.fine a { color: var(--accent-deep); text-decoration: none; }

ul { padding: 0; }

/* ---- BEFUND ALS ENTSCHEIDUNGSVORLAGE (Format vom 01.10.2026) ----
   Präfix fx-, weil die kurzen Namen der Vorlage (.mk, .plbl) hier schon belegt sind. */
.fx-card { display: flex; gap: 14px; }
.fx-card--decision { break-before: page; page-break-before: always; padding-top: 0; }
.fx-card--compact { break-inside: avoid; page-break-inside: avoid; margin-top: 7mm; padding-top: 14px; border-top: 1px solid rgba(20,21,15,.10); }
.fx-title { font-size: 17.5px; line-height: 1.25; margin-top: 2px; }
.fx-plbl { font-size: 9px; letter-spacing: .14em; color: var(--ink-soft); margin-bottom: 8px; }
.fx-proof { display: grid; gap: 13mm; margin-top: 8mm; break-inside: avoid; }
.fx-proof--split { grid-template-columns: 1fr 1fr; }
.fx-proof--phone { grid-template-columns: 52mm 1fr; gap: 11mm; }
.fx-proof--wide { grid-template-columns: 1fr; }
.fx-card--compact .fx-proof { margin-top: 5mm; }
.fx-note { font-size: 10.5px; line-height: 1.45; color: var(--ink-soft); margin-top: 11px; }
.fx-note b { color: var(--accent-deep); font-weight: 600; }
.fx-kv { border-top: 2px solid var(--ink); padding-top: 8px; margin-bottom: 18px; }
.fx-kvn { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; font-size: 26px; line-height: 1; color: var(--ink); }
.fx-kvn small { font-size: 13px; color: var(--ink-soft); font-family: 'Inter', sans-serif; font-weight: 400; }
.fx-kvl { font-size: 11px; line-height: 1.4; color: var(--ink-80); margin-top: 4px; }
.fx-card--compact .fx-kv { margin-bottom: 14px; }
.fx-card--compact .fx-kvn { font-size: 24px; }
.fx-grid { width: 100%; border-collapse: collapse; }
.fx-grid th { font-size: 8.5px; letter-spacing: .1em; color: var(--ink-soft); font-weight: 400; text-align: center; padding-bottom: 6px; }
.fx-grid td { font-size: 11.5px; color: var(--ink-80); padding: 7px 0; border-top: .5px solid rgba(20,21,15,.12); }
.fx-grid td.fx-c { text-align: center; }
.fx-x, .fx-check { display: inline-flex; width: 18px; height: 18px; border-radius: 50%; font-size: 11px; align-items: center; justify-content: center; font-weight: 600; }
.fx-x { background: rgba(198,47,20,.10); color: var(--accent-deep); }
.fx-check { background: var(--blue-wash); color: var(--blue); }
.fx-gleg { display: flex; flex-wrap: wrap; gap: 5px 12px; margin-top: 9px; font-size: 9.5px; color: var(--ink-soft); }
.fx-gleg .ggdot, .fx-gleg .fx-x, .fx-gleg .fx-check { width: 10px; height: 10px; margin-right: 4px; vertical-align: -1px; font-size: 7px; }
.fx-srcg { margin-bottom: 13px; }
.fx-gl { font-size: 11px; color: var(--ink); font-weight: 600; margin-bottom: 4px; }
.fx-chip { display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 9.5px; color: var(--ink-80); background: rgba(20,21,15,.05); padding: 3px 7px; border-radius: 3px; margin: 0 4px 4px 0; }
.fx-chip--own { background: var(--blue-wash); color: var(--blue); }
.fx-quote { font-size: 12px; line-height: 1.55; color: var(--ink); border-left: 2px solid rgba(20,21,15,.2); padding: 2px 0 2px 11px; display: block; }
.fx-qsrc { font-size: 9.5px; color: var(--ink-soft); margin-top: 6px; padding-left: 13px; }
.fx-quote ins { text-decoration: none; background: var(--blue-wash); color: var(--blue); padding: 0 2px; border-radius: 2px; }
.fx-quote mark { background: rgba(198,47,20,.12); color: var(--accent-deep); padding: 0 2px; border-radius: 2px; }
.fx-vrow { display: grid; grid-template-columns: 34mm 1fr; gap: 5mm; padding: 9px 0; border-top: .5px solid rgba(20,21,15,.12); }
.fx-vk { font-size: 11px; line-height: 1.4; color: var(--ink); font-weight: 600; }
.fx-vk small { display: block; font-weight: 400; color: var(--ink-soft); font-size: 10px; margin-top: 2px; }
.fx-vv { font-size: 12px; line-height: 1.5; color: var(--ink-80); }
.fx-pairs { width: 100%; border-collapse: collapse; }
.fx-pairs td { font-family: 'JetBrains Mono', monospace; font-size: 9.5px; color: var(--ink-80); padding: 7px 0; border-top: .5px solid rgba(20,21,15,.12); }
.fx-pairs td.fx-arrow { color: var(--ink-soft); text-align: center; width: 18px; }
.fx-pairs td.fx-to { color: var(--blue); }
.fx-dist { display: flex; height: 16px; border-radius: 3px; overflow: hidden; margin-top: 6px; background: rgba(20,21,15,.06); }
.fx-dist span { display: block; height: 100%; }
.fx-dlegend { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 7px; margin-bottom: 14px; font-size: 10.5px; color: var(--ink-80); }
.fx-dlegend i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
.fx-shot { position: relative; border: 1px solid rgba(20,21,15,.12); border-radius: 6px; overflow: hidden; background: #fff; }
.fx-shot img { display: block; width: 100%; }
.fx-ring { position: absolute; border: 2px solid var(--accent-deep); border-radius: 999px; }
.fx-addl { margin: 0 4% 9px; font-size: 10.5px; line-height: 1.35; color: var(--blue); background: rgba(230,236,250,.9); outline: 1.5px solid rgba(31,63,143,.55); padding: 2px 6px; border-radius: 3px; }
.fx-proof--phone > div:first-child .fx-shot { width: 120px; }
.fx-proof--phone .fx-facts { margin-top: 2mm; }
.fx-missing { font-size: 10px; color: var(--ink-soft); padding: 18px 12px; background: rgba(20,21,15,.04); }
.fx-stack { position: relative; }
.fx-phone { position: relative; width: 112px; border: 1px solid rgba(20,21,15,.15); border-radius: 10px; overflow: hidden; }
.fx-phone img { display: block; width: 112px; }
.fx-fold { position: absolute; left: 0; right: 0; height: 0; border-top: 2px solid var(--accent-deep); }
.fx-shade { position: absolute; left: 0; right: 0; bottom: 0; background: rgba(20,21,15,.28); }
.fx-pmk { position: absolute; left: 124px; font-size: 10.5px; line-height: 1.3; white-space: nowrap; transform: translateY(-50%); }
.fx-pmk b { font-family: 'JetBrains Mono', monospace; font-weight: 500; font-size: 9.5px; color: var(--accent-deep); display: block; letter-spacing: .04em; }
.fx-facts { margin-top: 8mm; border-top: 1px solid var(--line); }
.fx-card--compact .fx-facts { margin-top: 5mm; }
.fx-fact { display: grid; grid-template-columns: 35mm 1fr; gap: 6mm; padding: 11px 0; border-bottom: 1px solid var(--line); break-inside: avoid; }
.fx-card--compact .fx-fact { padding: 9px 0; }
.fx-fk { font-size: 9px; letter-spacing: .14em; color: var(--ink-soft); padding-top: 2px; }
.fx-fk--now { color: var(--blue); }
.fx-fv { font-size: 13px; line-height: 1.55; color: var(--ink); }
.fx-dblock { margin-top: 9mm; break-inside: avoid; }
.fx-dhead { font-size: 9px; letter-spacing: .14em; color: var(--ink-soft); }
.fx-dq { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; letter-spacing: -0.01em; font-size: 16.5px; color: var(--ink); margin-top: 6px; break-after: avoid; }
.fx-opts { display: grid; grid-template-columns: 1fr 1fr; gap: 8mm; margin-top: 16px; }
.fx-opt { border: 1px solid rgba(20,21,15,.18); border-radius: 4px; padding: 17px 19px 16px; }
.fx-opt--rec { border: 1.5px solid var(--blue); background: rgba(230,236,250,.45); }
.fx-ol { font-size: 9px; letter-spacing: .14em; color: var(--ink-soft); }
.fx-opt--rec .fx-ol { color: var(--blue); }
.fx-ot { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; font-size: 16px; color: var(--ink); margin-top: 6px; }
.fx-opt .fx-shot { margin-top: 12px; }
.fx-od { font-size: 12px; line-height: 1.55; color: var(--ink-80); margin-top: 8px; }
.fx-opt dl { margin-top: 14px; border-top: 1px solid var(--line); padding-top: 11px; display: grid; grid-template-columns: 17mm 1fr; row-gap: 6px; }
.fx-opt dt { font-size: 8.5px; letter-spacing: .12em; color: var(--ink-soft); padding-top: 2px; }
.fx-opt dd { font-size: 11px; color: var(--ink); margin: 0; }
.fx-why { font-size: 11.5px; line-height: 1.5; color: var(--blue); margin-top: 14px; }
.fx-foot { display: flex; gap: 18px; align-items: baseline; margin-top: 6mm; }
.fx-card--compact .fx-foot { margin-top: 4mm; }
.fx-foot .floc { margin-top: 0; }
.fx-more summary { font-size: 9.5px; letter-spacing: .04em; color: var(--ink-soft); border-bottom: .5px dashed rgba(20,21,15,.35); list-style: none; cursor: pointer; display: inline-block; }
.fx-more summary::-webkit-details-marker { display: none; }
.fx-more[open] summary { margin-bottom: 8px; }
.fx-more-body { border-left: 2px solid var(--line); padding-left: 12px; }
/* Entscheidungsseite hinter der Zusammenfassung */
.fx-lead { font-size: 13px; line-height: 1.6; color: var(--ink-80); margin-top: 10px; max-width: 160mm; }
.fx-thead { display: grid; grid-template-columns: 9mm 1fr 44mm 44mm; gap: 5mm; padding: 0 0 6px; font-size: 8.5px; letter-spacing: .12em; color: var(--ink-soft); margin-top: 9mm; }
.fx-dlist { border-top: 2px solid var(--ink); }
.fx-drow { display: grid; grid-template-columns: 9mm 1fr 44mm 44mm; gap: 5mm; padding: 15px 0; border-bottom: 1px solid var(--line); align-items: start; break-inside: avoid; }
.fx-no { font-family: 'Archivo', system-ui, sans-serif; font-weight: 900; font-size: 20px; color: var(--ink); line-height: 1; }
.fx-q { font-size: 13px; line-height: 1.4; color: var(--ink); font-weight: 600; }
.fx-src { font-size: 9px; letter-spacing: .1em; color: var(--ink-soft); margin-top: 5px; }
.fx-choice { border: 1px solid rgba(20,21,15,.18); border-radius: 4px; padding: 8px 10px; font-size: 11.5px; line-height: 1.35; color: var(--ink); }
.fx-cl { font-size: 8.5px; letter-spacing: .12em; color: var(--ink-soft); display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.fx-box { width: 11px; height: 11px; border: 1.2px solid rgba(20,21,15,.45); border-radius: 2px; display: inline-block; }
.fx-choice--rec { border: 1.5px solid var(--blue); background: rgba(230,236,250,.45); }
.fx-choice--rec .fx-cl { color: var(--blue); }
.fx-choice--rec .fx-box { border-color: var(--blue); }
.fx-csub { color: var(--ink-soft); }
.fx-nogo { display: grid; grid-template-columns: 1fr 1fr; gap: 8mm; margin-top: 4mm; }
.fx-nogo div { font-size: 12px; line-height: 1.5; color: var(--ink-80); border-top: 2px solid var(--accent-deep); padding-top: 9px; }
.fx-nogo b { color: var(--ink); font-weight: 600; display: block; margin-bottom: 2px; }
.fx-pointer { font-size: 11.5px; line-height: 1.5; color: var(--ink-soft); margin-top: 9mm; border-top: 1px solid var(--line); padding-top: 10px; }
</style></head><body>

<!-- COVER -->
<section class="cover">
  <span class="wm">Path to AI<span class="dot">.</span></span>
  <div class="eyebrow"><span class="ln"></span><span class="mono">${d.cover?.eyebrow ? esc(d.cover.eyebrow) : 'E&#8209;COMMERCE&#8209;AUDIT · SEO · KI&#8209;SICHTBARKEIT · WETTBEWERB'}</span></div>
  <h1>${coverHeadline(d)}</h1>
  <p class="intro">${d.cover?.intro ? safeHtml(d.cover.intro) : `Ein ehrlicher Blick auf <b>${esc(d.shop)}</b>: klassisches SEO bei Google, Sichtbarkeit in der KI-Suche, eure Produktdaten und der direkte Vergleich mit dem Wettbewerb.`}</p>
  <div class="ghost">P</div>
  <div class="meta">
    <div class="mb"><div class="mk">ERSTELLT FÜR</div><div class="mv">${esc(d.meta?.erstelltFuer || d.shop)}</div></div>
    <div class="mb"><div class="mk">ANALYSIERT</div><div class="mv">${esc(d.shop)}</div></div>
    <div class="mb"><div class="mk">VON</div><div class="mv">Path to AI</div></div>
    <div class="mb"><div class="mk">STAND</div><div class="mv">${esc(d.meta?.stand || '')}</div></div>
  </div>
</section>

<!-- DER MARKT & SHOP AUF EINEN BLICK -->
${(d.market || d.profile) ? marketProfileSection(d, head) : ''}

<!-- EXECUTIVE SUMMARY -->
<section class="chapter">
  ${head}
  <div class="eyebrow2 mono">AUF EINEN BLICK</div>
  <h2>${esc(d.exec.headline)}</h2>
  ${d.exec.summary.map((p) => `<p class="lead">${safeHtml(p)}</p>`).join('')}
  ${d.exec.strengths?.length ? `<div class="eyebrow2 mono" style="margin-top:12mm">WAS SCHON STEHT</div><div class="sgrid">${d.exec.strengths.map((x) => `<div class="sitem"><span class="scheck">✓</span>${esc(x)}</div>`).join('')}</div>` : ''}
  ${d.exec.composite ? (d.exec.scoreStyle === 'potenzial'
    ? `<div class="composite"><div class="cnum">${d.exec.composite}<span class="cden">/100</span></div><div>${d.fahrplan?.proj?.to ? `<div class="cto">→ ${esc(d.fahrplan.proj.to)} erreichbar</div>` : ''}<div class="clbl mono">PTAI E-Com Score · heute und nach Umsetzung der Maßnahmen</div></div></div>`
    : d.exec.scoreStyle === 'ampel'
    ? `<div class="composite"><div>${ampelDots(ampelLevel(d.exec.composite), 18)}<div class="aword" style="font-size:44px">${esc(ampelLevel(d.exec.composite).word)}</div></div><div class="clbl mono">GESAMT-STATUS<br>ÜBER ALLE DREI SÄULEN</div></div>`
    : `<div class="composite"><div class="cnum">${d.exec.composite}<span class="cden">/100</span></div><div class="clbl mono">GESAMT-SCORE<br>ÜBER ALLE DREI SÄULEN</div></div>`) : ''}
  <div class="scores">${d.exec.scores.map((s) => scoreCol(s, d.exec.scoreStyle)).join('')}</div>
  ${takeawaysList}
</section>

<!-- ENTSCHEIDUNGEN -->
${decisions.length ? decisionsSection(d, head, decisions) : ''}

<!-- EUER QUADRANT -->
${d.geoGrid ? geoGridSection(d.geoGrid, head) : ''}

${d.positioning ? quadrantSection(d, head) : ''}

<!-- IM VERGLEICH -->
${d.matrix ? matrixSection(d, head) : ''}

<!-- MASSNAHMEN — chapters, top-first + compact tail -->
${d.chapters.map((ch, i) => chapterSection(ch, i, head, ctx)).join('\n')}

<!-- STRATEGIE & FAHRPLAN -->
<section class="chapter">
  ${head}
  ${d.triage && !decisions.length ? triageInner(d.triage) : ''}
  <div class="roadmap">
  <div class="eyebrow2 mono"${d.triage && !decisions.length ? ' style="margin-top:18mm"' : ''}>DER WEG NACH VORN</div>
  <h2>${esc(d.fahrplan.headline)}</h2>
  <p class="lead">${esc(d.fahrplan.lead)}</p>
  <div class="stages">${d.fahrplan.stages.map(stageCol).join('')}</div>
  ${d.fahrplan.proj ? (d.exec.scoreStyle === 'ampel'
    ? `<div class="proj"><div><div class="big" style="font-size:26px"><span style="color:${ampelLevel(parseInt(d.fahrplan.proj.from, 10)).color}">●</span> ${esc(ampelLevel(parseInt(d.fahrplan.proj.from, 10)).word)} <span style="color:#5A5E57">→</span> <span style="color:${ampelLevel(parseInt(d.fahrplan.proj.to, 10)).color}">●</span> ${esc(ampelLevel(parseInt(d.fahrplan.proj.to, 10)).word)}</div><div class="plbl">${esc(d.fahrplan.proj.label)}</div></div><div class="ptext">${safeHtml(d.fahrplan.proj.text)}</div></div>`
    : `<div class="proj"><div><div class="big">${esc(d.fahrplan.proj.from)} <span style="color:#5A5E57">→</span> <span class="to">${esc(d.fahrplan.proj.to)}</span></div><div class="plbl">${esc(d.fahrplan.proj.label)}</div></div><div class="ptext">${safeHtml(d.fahrplan.proj.text)}</div></div>`) : ''}
  </div>${last === 'fahrplan' ? fine : ''}
</section>

<!-- WO WIR ANDOCKEN -->
${d.levers ? leversSection(d.levers, head, last === 'levers' ? fine : '') : ''}

<!-- QUELLEN & METHODIK -->
${d.sources ? sourcesSection(d.sources, head, fine) : ''}

<!-- SCHLUSS: Schlussseite aus PTAI_CLOSING_FILE oder neutraler Schluss -->
${closing}

</body></html>`;
}
