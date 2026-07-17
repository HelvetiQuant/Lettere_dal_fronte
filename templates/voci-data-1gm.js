// ════════════════════════════════════════════════════════════════════════════
// voci-data-1gm.js — Dati e funzioni per il frontend dedicato alla 1ª GM
// Re-esporta da voci-data.js filtrando solo soggetti/eventi della Prima GM
// ════════════════════════════════════════════════════════════════════════════
import {
  STRINGS as _BASE_STRINGS, SUBJECTS as ALL_SUBJECTS, EVENTS as ALL_EVENTS,
  PROVIDERS, EXPLORE_TABLES as ALL_EXPLORE,
  buildArchiveUrl, loadSoldierDossier,
} from './voci-data.js';

// ── Filtra solo soggetti 1GM ──────────────────────────────────────────────────
const _ww1SubjectIds = ['baracca', 'toti', 'rossi_ministero'];
export const SUBJECTS = Object.fromEntries(
  Object.entries(ALL_SUBJECTS).filter(([k]) => _ww1SubjectIds.includes(k))
);

// ── Filtra solo eventi 1GM ────────────────────────────────────────────────────
const _ww1EventIds = ['caporetto', 'vittorio_veneto', 'undicesima_isonzo'];
export const EVENTS = Object.fromEntries(
  Object.entries(ALL_EVENTS).filter(([k]) => _ww1EventIds.includes(k))
);

// ── Esplora: solo tabelle rilevanti per la 1GM ────────────────────────────────
export const EXPLORE_TABLES = {
  caduti: ALL_EXPLORE.caduti,
  decorati: ALL_EXPLORE.decorati,
  documenti: ALL_EXPLORE.documenti,
  fonti: ALL_EXPLORE.fonti,
};

// ── Statistiche di default (sostituite dal backend) ───────────────────────────
export const DB_STATS = [
  { id:"caduti",       key:"dbCaduti",       value:0,   sub:"6 fonti nazionali · 1GM" },
  { id:"decorati",     key:"dbDecorati",     value:0,   sub:"ISTORECO + Nastro Azzurro · 1GM" },
  { id:"menzioni",     key:"dbMenzioni",     value:0,   sub:"fondi archivistici SME" },
  { id:"documenti",    key:"dbDocumenti",    value:0,   sub:"fondi archivistici censiti" },
  { id:"fonti",        key:"dbFonti",        value:0,   sub:"schede di collocazione esterne" },
  { id:"entita",       key:"dbEntita",       value:0,   sub:"persone · luoghi · eventi · unità" },
  { id:"collegamenti", key:"dbCollegamenti", value:0,   sub:"star schema cross-dataset" },
  { id:"eventi",       key:"dbEventi",       value:0,   sub:"ricostruzioni multi-prospettiva" },
  { id:"providers",    key:"dbProviders",    value:0,   sub:"archivi nazionali e internazionali" },
];

// ── Carica statistiche reali dal backend (solo 1GM) ───────────────────────────
export async function loadLiveStats() {
  try {
    const [ww1Stats, eventsR, sourceStatsR] = await Promise.all([
      fetch('/api/stats/ww1').then(r=>r.json()).catch(()=>({})),
      fetch('/api/events').then(r=>r.json()).catch(()=>({})),
      fetch('/api/source/stats').then(r=>r.json()).catch(()=>({})),
    ]);

    return [
      { id:"caduti",       key:"dbCaduti",       value: ww1Stats.caduti||0,              sub:"6 fonti nazionali · 1GM" },
      { id:"decorati",     key:"dbDecorati",     value: ww1Stats.decorati||0,            sub:"ISTORECO + Nastro Azzurro · 1GM" },
      { id:"menzioni",     key:"dbMenzioni",     value: ww1Stats.menzioni||0,            sub:"fondi archivistici SME" },
      { id:"documenti",    key:"dbDocumenti",    value: (ww1Stats.fondi||0),               sub:"fondi archivistici censiti" },
      { id:"fonti",        key:"dbFonti",        value: ww1Stats.fonti_indice||0,        sub:"schede di collocazione esterne" },
      { id:"entita",       key:"dbEntita",       value: ww1Stats.entita||0,              sub:"persone · luoghi · eventi · unità" },
      { id:"collegamenti", key:"dbCollegamenti", value: ww1Stats.collegamenti||0,        sub:"star schema cross-dataset" },
      { id:"eventi",       key:"dbEventi",       value: (eventsR.eventi||[]).length,     sub:"ricostruzioni multi-prospettiva" },
      { id:"providers",    key:"dbProviders",    value: sourceStatsR.providers||0,       sub:"archivi nazionali e internazionali" },
    ];
  } catch(e) {
    console.warn('loadLiveStats 1GM error:', e);
    return DB_STATS;
  }
}

// ── Ricerca live: interroga il backend 1GM e converte in formato SUBJECTS ─────
export async function searchLive(query) {
  if (!query || query.trim().length < 2) return { subjects: {}, events: {} };
  try {
    const res = await fetch(`/api/search/ww1?q=${encodeURIComponent(query.trim())}&limit=20`).then(r=>r.json());
    const subjects = {};
    const decorati = res.decorati || [];
    const caduti   = res.caduti   || [];
    const menzioni = res.menzioni || [];

    for (const d of decorati.slice(0, 8)) {
      const id = `dec_${d.id || d.cognome}`;
      subjects[id] = {
        id, type: 'persona',
        name: `${d.cognome || ''} ${d.nome || ''}`.trim(),
        subtitle: `Decorato al Valor Militare${d.decorazione ? ' — ' + d.decorazione : ''}`,
        tags: ['Decorato', d.guerra || '1GM', d.source || 'ISTORECO'],
        status: 'partial', confidence: 0.7,
        timeline: [], perspectives: [], sources: [], gaps: [],
        _cognome: d.cognome || '', _nome: d.nome || '',
      };
    }

    for (const c of caduti.slice(0, 8)) {
      const cnome = `${c.cognome || c.nom || c.nome || ''} ${c.nome || ''}`.trim();
      const id = `cad_${cnome.replace(/\s+/g, '_').toLowerCase()}_${c._source_table || ''}`;
      subjects[id] = {
        id, type: 'persona',
        name: cnome || 'Caduto',
        subtitle: `Caduto${c._source_label ? ' — ' + c._source_label : ''}${c.luogo_morte ? ', ' + c.luogo_morte : ''}`,
        tags: ['Caduto', '1GM', c._source_label || ''],
        status: 'verified', confidence: 0.9,
        timeline: [], perspectives: [], sources: [], gaps: [],
        _cognome: c.cognome || c.nom || '', _nome: c.nome || '',
      };
    }

    for (const m of menzioni.slice(0, 5)) {
      const id = `men_${m.id}`;
      subjects[id] = {
        id, type: 'persona',
        name: `${m.cognome || ''} ${m.nome || ''}`.trim() || 'Menzione',
        subtitle: `Menzione in fondo SME${m.reparto ? ' — ' + m.reparto : ''}`,
        tags: ['Menzione', '1GM', m.titolo || ''],
        status: 'partial', confidence: 0.6,
        timeline: [], perspectives: [], sources: [], gaps: [],
        _cognome: m.cognome || '', _nome: m.nome || '',
      };
    }

    return { subjects, events: {} };
  } catch (e) {
    console.warn('searchLive 1GM error:', e);
    return { subjects: {}, events: {} };
  }
}

// ── Sovrascrive stringhe per contesto 1GM ─────────────────────────────────────
const _ww1Subtitle = {
  it: "Voci dal Fronte è un archivio federato per la ricerca storica su soldati, dispersi, caduti e reduci della Prima Guerra Mondiale",
  en: "Voci dal Fronte is a federated archive for historical research on soldiers, missing, fallen and veterans of the First World War",
  de: "Voci dal Fronte ist ein föderiertes Archiv für die historische Forschung über Soldaten, Vermisste, Gefallene und Veteranen des Ersten Weltkriegs",
  fr: "Voci dal Fronte est une archive fédérée pour la recherche historique sur les soldats, disparus, tombés et anciens combattants de la Première Guerre mondiale",
};
const _ww1Title2 = {
  it: "Tutte le Voci, un'Unica Storia",
  en: "All Voices, One Story",
  de: "Alle Stimmen, eine Geschichte",
  fr: "Toutes les Voix, une Seule Histoire",
};
const _ww1Strings = {};
for (const lang of Object.keys(_BASE_STRINGS)) {
  _ww1Strings[lang] = { ..._BASE_STRINGS[lang] };
  if (_ww1Subtitle[lang]) _ww1Strings[lang].heroSubtitle = _ww1Subtitle[lang];
  if (_ww1Title2[lang]) _ww1Strings[lang].heroTitle2 = _ww1Title2[lang];
}
export const STRINGS = _ww1Strings;

// ── Re-esporta funzioni utili ─────────────────────────────────────────────────
export { PROVIDERS, buildArchiveUrl, loadSoldierDossier };

// ── Carica stato admin (riusa il backend generale) ────────────────────────────
export async function loadAdminStatus() {
  try {
    const [status, srcStats] = await Promise.all([
      fetch('/api/status').then(r => r.json()).catch(() => ({})),
      fetch('/api/source/stats').then(r => r.json()).catch(() => ({})),
    ]);
    return { status, srcStats };
  } catch (e) { return {}; }
}

export async function loadLiveCredits() {
  try {
    return await fetch('/api/credits').then(r => r.json());
  } catch (e) { return {}; }
}
