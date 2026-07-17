// ════════════════════════════════════════════════════════════════════════════
// voci-data-1gm.js — Dati e funzioni per il frontend dedicato alla 1ª GM
// Re-esporta da ../voci-data.js filtrando solo soggetti/eventi della Prima GM
// ════════════════════════════════════════════════════════════════════════════
import {
  STRINGS as _BASE_STRINGS, SUBJECTS as ALL_SUBJECTS, EVENTS as ALL_EVENTS,
  PROVIDERS, EXPLORE_TABLES as ALL_EXPLORE,
  buildArchiveUrl, loadSoldierDossier,
} from '../voci-data.js';

// ── Filtra solo soggetti 1GM ──────────────────────────────────────────────────
const _ww1SubjectIds = ['baracca', 'toti', 'rossi_ministero'];
export const SUBJECTS = Object.fromEntries(
  Object.entries(ALL_SUBJECTS).filter(([k]) => _ww1SubjectIds.includes(k))
);

// ── Filtra solo eventi 1GM (fallback statico, sostituito da loadEvents1gm) ────
const _ww1EventIds = ['caporetto', 'vittorio_veneto', 'undicesima_isonzo'];
export let EVENTS = Object.fromEntries(
  Object.entries(ALL_EVENTS).filter(([k]) => _ww1EventIds.includes(k))
);

// ── Carica eventi canonici 1GM+WW2 dal backend (eventi_1gm.db) ────────────────
export async function loadEvents1gm() {
  try {
    const res = await fetch('/api/events/1gm').then(r => r.json());
    const eventi = res.eventi || [];
    const dynamicEvents = {};
    for (const ev of eventi) {
      const id = ev.nome.toLowerCase()
        .replace(/[àá]/g, 'a').replace(/[èé]/g, 'e').replace(/[ìí]/g, 'i').replace(/[òó]/g, 'o').replace(/[ùú]/g, 'u')
        .replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
      dynamicEvents[id] = {
        id,
        type: 'evento',
        name: ev.nome,
        subtitle: `${ev.data_inizio || '?'} – ${ev.data_fine || '?'}, ${ev.luogo || ''}`,
        tags: ev.aliases?.slice(0, 3) || [],
        status: 'verified',
        confidence: 0.95,
        timeline: [],
        perspectives: [],
        sources: [],
        gaps: [],
        _event_db_id: ev.id,
        _stats: {
          caduti: ev.caduti || 0,
          decorati: ev.decorati || 0,
          documenti: ev.documenti || 0,
          fonti: ev.fonti || 0,
          internati: ev.internati || 0,
          cwgc: ev.cwgc || 0,
        },
        _descrizione: ev.descrizione || '',
        _keywords: ev.keywords || [],
        _aliases: ev.aliases || [],
      };
    }
    // Merge: keep static events for perspectives/timeline, add dynamic ones
    EVENTS = { ...dynamicEvents, ...EVENTS };
    return EVENTS;
  } catch(e) {
    console.warn('loadEvents1gm error:', e);
    return EVENTS;
  }
}

// ── Carica dossier completo per un evento (da event_query_engine) ─────────────
export async function loadEventDossier(eventName) {
  try {
    const encoded = encodeURIComponent(eventName.replace(/\s+/g, '+'));
    const [dossierR, cadutiR, decoratiR] = await Promise.all([
      fetch(`/api/events/1gm/${encoded}`).then(r => r.json()).catch(() => ({})),
      fetch(`/api/events/1gm/${encoded}/caduti?limit=50`).then(r => r.json()).catch(() => ({caduti:[],total:0})),
      fetch(`/api/events/1gm/${encoded}/decorati?limit=50`).then(r => r.json()).catch(() => ({decorati:[],total:0})),
    ]);

    const result = {
      event: dossierR.event || {},
      caduti: cadutiR.caduti || [],
      caduti_total: cadutiR.total || 0,
      decorati: decoratiR.decorati || [],
      decorati_total: decoratiR.total || 0,
      documenti: dossierR.documenti?.items || [],
      fonti: dossierR.fonti?.items || [],
      internati: dossierR.internati?.items || [],
      ok: dossierR.ok !== false,
    };
    return result;
  } catch(e) {
    console.warn('loadEventDossier error:', e);
    return { ok: false, error: e.message };
  }
}

// ── Esplora: tabelle 1GM caricate dinamicamente dal backend ───────────────────
export const EXPLORE_TABLES = {
  caduti:    { labelKey:"dbCaduti",    cols:[], rows:[] },
  decorati:  { labelKey:"dbDecorati",  cols:[], rows:[] },
  documenti: { labelKey:"dbDocumenti", cols:[], rows:[] },
  fonti:     { labelKey:"dbFonti",     cols:[], rows:[] },
};

// ── Carica tabelle esplorabili dal backend (solo 1GM) ─────────────────────────
export async function loadExploreTables() {
  try {
    const [cadutiR, decoratiR, fondiR, fontiR] = await Promise.all([
      fetch('/api/caduti?limit=50').then(r=>r.json()).catch(()=>({rows:[]})),
      fetch('/api/decorati?limit=50').then(r=>r.json()).catch(()=>({rows:[]})),
      fetch('/api/fondi?limit=50').then(r=>r.json()).catch(()=>({rows:[]})),
      fetch('/api/source/stats').then(r=>r.json()).catch(()=>({})),
    ]);

    // Caduti
    if (cadutiR.rows && cadutiR.rows.length) {
      const cols = ["Cognome","Nome","Luogo morte","Anno morte","Fonte"];
      const rows = cadutiR.rows.slice(0,50).map(r => [
        r.cognome || r.nominativo || '',
        r.nome || '',
        r.luogo_morte || '',
        r.anno_morte || r.data_morte || '',
        r._source_label || 'Albo d\'Oro',
      ]);
      EXPLORE_TABLES.caduti = { labelKey:"dbCaduti", cols, rows };
    }

    // Decorati (filtra solo 1GM)
    if (decoratiR.rows && decoratiR.rows.length) {
      const ww1 = decoratiR.rows.filter(r => {
        const g = (r.guerra || '').toUpperCase();
        return g.includes('GRANDE') || g.includes('1915') || g.includes('1916') || g.includes('1917') || g.includes('1918');
      });
      const cols = ["Cognome","Nome","Decorazione","Guerra","Luogo morte"];
      const rows = ww1.slice(0,50).map(r => [
        r.cognome || '',
        r.nome || '',
        r.decorazione || '',
        r.guerra || '1GM',
        r.luogo_morte || '',
      ]);
      EXPLORE_TABLES.decorati = { labelKey:"dbDecorati", cols, rows };
    }

    // Fondi archivistici
    if (fondiR.rows && fondiR.rows.length) {
      const cols = ["Codice fondo","Titolo"];
      const rows = fondiR.rows.slice(0,50).map(r => [
        r.codice_fondo || '',
        (r.titolo || '').substring(0,80),
      ]);
      EXPLORE_TABLES.documenti = { labelKey:"dbDocumenti", cols, rows };
    }

    return EXPLORE_TABLES;
  } catch(e) {
    console.warn('loadExploreTables 1GM error:', e);
    return EXPLORE_TABLES;
  }
}

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
      fetch('/api/events/1gm').then(r=>r.json()).catch(()=>({eventi:[]})),
      fetch('/api/source/stats').then(r=>r.json()).catch(()=>({})),
    ]);

    // Load dynamic events in background
    loadEvents1gm();

    const eventi1gm = eventsR.eventi || [];
    return [
      { id:"caduti",       key:"dbCaduti",       value: ww1Stats.caduti||0,              sub:"6 fonti nazionali · 1GM" },
      { id:"decorati",     key:"dbDecorati",     value: ww1Stats.decorati||0,            sub:"ISTORECO + Nastro Azzurro · 1GM" },
      { id:"menzioni",     key:"dbMenzioni",     value: ww1Stats.menzioni||0,            sub:"fondi archivistici SME" },
      { id:"documenti",    key:"dbDocumenti",    value: (ww1Stats.fondi||0),              sub:"fondi archivistici censiti" },
      { id:"fonti",        key:"dbFonti",        value: ww1Stats.fonti_indice||0,        sub:"schede di collocazione esterne" },
      { id:"entita",       key:"dbEntita",       value: ww1Stats.entita||0,              sub:"persone · luoghi · eventi · unità" },
      { id:"collegamenti", key:"dbCollegamenti", value: ww1Stats.collegamenti||0,        sub:"star schema cross-dataset" },
      { id:"eventi",       key:"dbEventi",       value: eventi1gm.length,                sub:"eventi canonici 1GM+WW2 (eventi_1gm.db)" },
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
const _ww1Strings = {};
for (const lang of Object.keys(_BASE_STRINGS)) {
  _ww1Strings[lang] = { ..._BASE_STRINGS[lang] };
  if (_ww1Subtitle[lang]) _ww1Strings[lang].heroSubtitle = _ww1Subtitle[lang];
}
export const STRINGS = _ww1Strings;

// ── Re-esporta funzioni utili ─────────────────────────────────────────────────
export { PROVIDERS, buildArchiveUrl, loadSoldierDossier, loadEvents1gm, loadEventDossier };

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
