// Voci dal Fronte — sample data + i18n strings for the frontend prototype.
// Historical record content stays in Italian (original archival language);
// only interface chrome is translated across it/en/de/fr.

export const STRINGS = {
it: {
  navHome:"Home", navSearch:"Ricerca", navExplore:"Esplora database", navEvents:"Eventi storici", navAdmin:"Amministrazione",
  brandTag:"Archivio storico multi-fonte — guerre mondiali del '900",
  heroKicker:"Ricerca federata su archivi locali e internazionali",
  heroTitle1:"Voci dal Fronte", heroTitle2:"",
  heroSubtitle:"Tutte le Voci, in un Unica Storia",
  searchPlaceholder:"Cerca un nome, un reparto, un luogo o una data — es. Rossi Mario, Bergamo 1943",
  searchButton:"Cerca", searchHint:"La ricerca interroga prima i dati locali, poi — se necessario — i provider federati e l'intelligenza artificiale.",
  examplesLabel:"Prova con:",
  dbInternati:"Soldati IMI", dbCaduti:"Caduti", dbDecorati:"Decorati", dbEntita:"Entità", dbCollegamenti:"Archi del grafo",
  dbDocumenti:"Documenti d'archivio", dbFonti:"Fonti indicizzate", dbEventi:"Eventi curati", dbProviders:"Archivi federati",
  eventsSectionTitle:"Eventi in evidenza", eventsSectionSub:"Ricostruzioni con fonti italiane, dell'Asse e alleate a confronto",
  seeAll:"Vedi tutti",
  resultsFor:"Risultati per", tabOverview:"Panoramica", tabCrossdb:"Collegamenti", tabSources:"Fonti", tabEvents:"Eventi correlati",
  tabGaps:"Lacune", tabPerspectives:"Punti di vista",
  noResults:"Nessuna corrispondenza esatta nei dati locali.", 
  federationNote:"In un sistema collegato, a questo punto la ricerca interrogherebbe in parallelo i 16 archivi federati e, in mancanza di riscontri verificati, l'intelligenza artificiale cloud.",
  personsSection:"Soggetti", eventsSection:"Eventi storici",
  statusLocal:"Locale", statusOnline:"Online", statusRequest:"Da richiedere", statusError:"Non accessibile",
  statusUnverified:"Non verificato", statusVerified:"Verificato", statusPartial:"Parzialmente verificato",
  btnOpenFile:"Apri file", btnOpenOriginal:"Apri originale", btnRequestAccess:"Richiedi accesso", btnGenerateDossier:"Apri dossier",
  btnBack:"Indietro", btnClose:"Chiudi", btnExploreDb:"Esplora", btnGenerateBio:"Genera dossier verificato",
  dossierConfidence:"Livello di verifica", dossierTimelineTitle:"Cronologia", dossierPerspectivesTitle:"Punti di vista a confronto",
  dossierSourcesTitle:"Fonti collegate", dossierGapsTitle:"Campi mancanti", 
  dossierUnverifiedNote:"Fonti individuate ma non ancora recuperate — non usate nel testo del dossier:",
  dossierAiNote:"Sintesi generata da AI cloud sulla base delle sole fonti verificate elencate sopra.",
  gapMissingField:"Campo mancante", gapSuggestedProvider:"Provider suggerito", gapPriorityHigh:"Priorità alta",
  gapPriorityMedium:"Priorità media", gapPriorityLow:"Priorità bassa",
  exploreFilterPlaceholder:"Filtra per cognome, luogo, reparto…", exploreRows:"record", explorePrev:"Precedente", exploreNext:"Successivo",
  explorePage:"Pagina", perspectiveIntlNote:"Dati incrociati con archivi internazionali",
  lightboxTitle:"Anteprima documento", lightboxPlaceholderNote:"Anteprima dimostrativa — nel sistema collegato qui appare la scansione originale.",
  lightboxOpenExternal:"Apri sul sito dell'archivio",
  footerAbout:"Voci dal Fronte è un archivio federato per la ricerca storica su soldati, dispersi, caduti e reduci delle due guerre mondiali.",
  footerNote:"I dati storici sono presentati nella lingua originale della fonte.", footerAdminLink:"Area operatori",
  adminTitle:"Area operatori", adminSubtitle:"Import, estrazione ed enrichment — riservata a chi cura l'archivio.",
  adminBackPublic:"Torna al sito pubblico", adminImportTitle:"Import documenti", adminExtractionTitle:"Avanzamento estrazioni",
  adminProvidersTitle:"Stato federazione provider", adminCreditsTitle:"Crediti AI cloud",
  adminDemoNote:"Pannello dimostrativo — le azioni non sono connesse a un backend in questo prototipo.",
  povItaly:"Fonti italiane", povAxis:"Fonti dell'Asse", povAllied:"Fonti alleate", povIntl:"Archivi internazionali",
  loading:"Caricamento…", langLabel:"Lingua", demoBadge:"Dato dimostrativo", of:"di",
  btnGenerateReport:"Genera Report", reportExplanation:"Analizza tutte le fonti verificate dell'evento ed estrae solo i fatti comuni a tutte le fonti, creando una ricostruzione oggettiva.",
  reportLoading:"Generazione in corso…", reportTitle:"Report AI — Fatti accertati da fonti convergenti",
  reportAiBadge:"Report AI", sourcesLabel:"fonti",
  eventsBasedOnSearches:"Eventi in evidenza selezionati in base alle tue ricerche recenti.",
},
en: {
  navHome:"Home", navSearch:"Search", navExplore:"Explore databases", navEvents:"Historical events", navAdmin:"Administration",
  brandTag:"A federated archive for 20th-century world war research",
  heroKicker:"Federated search across local and international archives",
  heroTitle1:"Voci dal Fronte", heroTitle2:"",
  heroSubtitle:"All Voices, One Story",
  searchPlaceholder:"Search a name, unit, place or date — e.g. Rossi Mario, Bergamo 1943",
  searchButton:"Search", searchHint:"Search checks local records first, then — if needed — federated providers and AI.",
  examplesLabel:"Try:",
  dbInternati:"IMI soldiers", dbCaduti:"Casualties", dbDecorati:"Decorated", dbEntita:"Entities", dbCollegamenti:"Graph edges",
  dbDocumenti:"Archival documents", dbFonti:"Indexed sources", dbEventi:"Curated events", dbProviders:"Federated archives",
  eventsSectionTitle:"Featured events", eventsSectionSub:"Reconstructions comparing Italian, Axis and Allied sources",
  seeAll:"See all",
  resultsFor:"Results for", tabOverview:"Overview", tabCrossdb:"Cross-links", tabSources:"Sources", tabEvents:"Related events",
  tabGaps:"Gaps", tabPerspectives:"Perspectives",
  noResults:"No exact match in local data.",
  federationNote:"In a connected system, the search would now query the 16 federated archives in parallel and, absent verified matches, cloud AI.",
  personsSection:"Subjects", eventsSection:"Historical events",
  statusLocal:"Local", statusOnline:"Online", statusRequest:"On request", statusError:"Not accessible",
  statusUnverified:"Unverified", statusVerified:"Verified", statusPartial:"Partially verified",
  btnOpenFile:"Open file", btnOpenOriginal:"Open original", btnRequestAccess:"Request access", btnGenerateDossier:"Open dossier",
  btnBack:"Back", btnClose:"Close", btnExploreDb:"Explore", btnGenerateBio:"Generate verified dossier",
  dossierConfidence:"Verification level", dossierTimelineTitle:"Timeline", dossierPerspectivesTitle:"Perspectives compared",
  dossierSourcesTitle:"Linked sources", dossierGapsTitle:"Missing fields",
  dossierUnverifiedNote:"Sources located but not yet retrieved — not used in the dossier text:",
  dossierAiNote:"AI-generated synthesis based only on the verified sources listed above.",
  gapMissingField:"Missing field", gapSuggestedProvider:"Suggested provider", gapPriorityHigh:"High priority",
  gapPriorityMedium:"Medium priority", gapPriorityLow:"Low priority",
  exploreFilterPlaceholder:"Filter by surname, place, unit…", exploreRows:"records", explorePrev:"Previous", exploreNext:"Next",
  explorePage:"Page", perspectiveIntlNote:"Cross-checked with international archives",
  lightboxTitle:"Document preview", lightboxPlaceholderNote:"Demo preview — the connected system would show the original scan here.",
  lightboxOpenExternal:"Open on archive site",
  footerAbout:"Voci dal Fronte is a federated archive for historical research on soldiers, missing, fallen and returned servicemen of the two world wars.",
  footerNote:"Historical data is shown in the source's original language.", footerAdminLink:"Staff area",
  adminTitle:"Staff area", adminSubtitle:"Import, extraction and enrichment — for archive curators.",
  adminBackPublic:"Back to public site", adminImportTitle:"Document import", adminExtractionTitle:"Extraction progress",
  adminProvidersTitle:"Provider federation status", adminCreditsTitle:"Cloud AI credits",
  adminDemoNote:"Demo panel — actions are not wired to a backend in this prototype.",
  povItaly:"Italian sources", povAxis:"Axis sources", povAllied:"Allied sources", povIntl:"International archives",
  loading:"Loading…", langLabel:"Language", demoBadge:"Sample data", of:"of",
  btnGenerateReport:"Generate Report", reportExplanation:"Analyzes all verified sources for this event and extracts only facts common to all sources, producing an objective reconstruction.",
  reportLoading:"Generating…", reportTitle:"AI Report — Facts verified by converging sources",
  reportAiBadge:"AI Report", sourcesLabel:"sources",
  eventsBasedOnSearches:"Featured events selected based on your recent searches.",
},
de: {
  navHome:"Start", navSearch:"Suche", navExplore:"Datenbanken durchsuchen", navEvents:"Historische Ereignisse", navAdmin:"Verwaltung",
  brandTag:"Föderiertes Archiv zur Erforschung der Weltkriege des 20. Jahrhunderts",
  heroKicker:"Föderierte Suche über lokale und internationale Archive",
  heroTitle1:"Voci dal Fronte", heroTitle2:"",
  heroSubtitle:"Alle Stimmen, eine Geschichte",
  searchPlaceholder:"Name, Einheit, Ort oder Datum suchen — z. B. Rossi Mario, Bergamo 1943",
  searchButton:"Suchen", searchHint:"Die Suche prüft zuerst lokale Daten, dann bei Bedarf föderierte Anbieter und KI.",
  examplesLabel:"Beispiele:",
  dbInternati:"IMI-Soldaten", dbCaduti:"Gefallene", dbDecorati:"Ausgezeichnete", dbEntita:"Entitäten", dbCollegamenti:"Graph-Kanten",
  dbDocumenti:"Archivdokumente", dbFonti:"Indexierte Quellen", dbEventi:"Kuratierte Ereignisse", dbProviders:"Föderierte Archive",
  eventsSectionTitle:"Ausgewählte Ereignisse", eventsSectionSub:"Rekonstruktionen im Vergleich italienischer, Achsen- und alliierter Quellen",
  seeAll:"Alle anzeigen",
  resultsFor:"Ergebnisse für", tabOverview:"Übersicht", tabCrossdb:"Querverweise", tabSources:"Quellen", tabEvents:"Verwandte Ereignisse",
  tabGaps:"Lücken", tabPerspectives:"Perspektiven",
  noResults:"Keine exakte Übereinstimmung in lokalen Daten.",
  federationNote:"In einem verbundenen System würde die Suche nun parallel die 16 föderierten Archive und – ohne verifizierte Treffer – Cloud-KI abfragen.",
  personsSection:"Personen", eventsSection:"Historische Ereignisse",
  statusLocal:"Lokal", statusOnline:"Online", statusRequest:"Auf Anfrage", statusError:"Nicht zugänglich",
  statusUnverified:"Nicht verifiziert", statusVerified:"Verifiziert", statusPartial:"Teilweise verifiziert",
  btnOpenFile:"Datei öffnen", btnOpenOriginal:"Original öffnen", btnRequestAccess:"Zugang anfragen", btnGenerateDossier:"Dossier öffnen",
  btnBack:"Zurück", btnClose:"Schließen", btnExploreDb:"Durchsuchen", btnGenerateBio:"Verifiziertes Dossier erstellen",
  dossierConfidence:"Verifizierungsgrad", dossierTimelineTitle:"Zeitleiste", dossierPerspectivesTitle:"Perspektiven im Vergleich",
  dossierSourcesTitle:"Verknüpfte Quellen", dossierGapsTitle:"Fehlende Felder",
  dossierUnverifiedNote:"Gefundene, aber noch nicht abgerufene Quellen — nicht im Dossiertext verwendet:",
  dossierAiNote:"KI-Synthese ausschließlich auf Basis der oben genannten verifizierten Quellen.",
  gapMissingField:"Fehlendes Feld", gapSuggestedProvider:"Empfohlener Anbieter", gapPriorityHigh:"Hohe Priorität",
  gapPriorityMedium:"Mittlere Priorität", gapPriorityLow:"Niedrige Priorität",
  exploreFilterPlaceholder:"Nach Nachname, Ort, Einheit filtern…", exploreRows:"Datensätze", explorePrev:"Zurück", exploreNext:"Weiter",
  explorePage:"Seite", perspectiveIntlNote:"Abgeglichen mit internationalen Archiven",
  lightboxTitle:"Dokumentvorschau", lightboxPlaceholderNote:"Demo-Vorschau — im verbundenen System erscheint hier die Originalscanaufnahme.",
  lightboxOpenExternal:"Auf der Archivseite öffnen",
  footerAbout:"Voci dal Fronte ist ein föderiertes Archiv zur historischen Erforschung von Soldaten, Vermissten, Gefallenen und Heimkehrern der beiden Weltkriege.",
  footerNote:"Historische Daten werden in der Originalsprache der Quelle angezeigt.", footerAdminLink:"Mitarbeiterbereich",
  adminTitle:"Mitarbeiterbereich", adminSubtitle:"Import, Extraktion und Anreicherung — für Archivkuratoren.",
  adminBackPublic:"Zur öffentlichen Seite", adminImportTitle:"Dokumentenimport", adminExtractionTitle:"Extraktionsfortschritt",
  adminProvidersTitle:"Status der Anbieterföderation", adminCreditsTitle:"Cloud-KI-Guthaben",
  adminDemoNote:"Demo-Panel — Aktionen sind in diesem Prototyp nicht mit einem Backend verbunden.",
  povItaly:"Italienische Quellen", povAxis:"Quellen der Achsenmächte", povAllied:"Alliierte Quellen", povIntl:"Internationale Archive",
  loading:"Wird geladen…", langLabel:"Sprache", demoBadge:"Beispieldaten", of:"von",
  btnGenerateReport:"Bericht erstellen", reportExplanation:"Analysiert alle verifizierten Quellen dieses Ereignisses und extrahiert nur Fakten, die allen Quellen gemeinsam sind, um eine objektive Rekonstruktion zu erstellen.",
  reportLoading:"Wird erstellt…", reportTitle:"KI-Bericht — Durch Quellenkonvergenz verifizierte Fakten",
  reportAiBadge:"KI-Bericht", sourcesLabel:"Quellen",
  eventsBasedOnSearches:"Hervorgehobene Ereignisse basierend auf Ihren letzten Suchen.",
},
fr: {
  navHome:"Accueil", navSearch:"Recherche", navExplore:"Explorer les bases", navEvents:"Événements historiques", navAdmin:"Administration",
  brandTag:"Archive fédérée pour la recherche sur les guerres mondiales du XXe siècle",
  heroKicker:"Recherche fédérée sur archives locales et internationales",
  heroTitle1:"Voci dal Fronte", heroTitle2:"",
  heroSubtitle:"Toutes les voix, une histoire",
  searchPlaceholder:"Cherchez un nom, une unité, un lieu ou une date — ex. Rossi Mario, Bergame 1943",
  searchButton:"Rechercher", searchHint:"La recherche interroge d'abord les données locales, puis, si besoin, les archives fédérées et l'IA.",
  examplesLabel:"Essayez :",
  dbInternati:"Soldats IMI", dbCaduti:"Victimes", dbDecorati:"Décorés", dbEntita:"Entités", dbCollegamenti:"Liens du graphe",
  dbDocumenti:"Documents d'archives", dbFonti:"Sources indexées", dbEventi:"Événements sélectionnés", dbProviders:"Archives fédérées",
  eventsSectionTitle:"Événements en vedette", eventsSectionSub:"Reconstitutions croisant sources italiennes, de l'Axe et alliées",
  seeAll:"Tout voir",
  resultsFor:"Résultats pour", tabOverview:"Aperçu", tabCrossdb:"Liens croisés", tabSources:"Sources", tabEvents:"Événements liés",
  tabGaps:"Lacunes", tabPerspectives:"Points de vue",
  noResults:"Aucune correspondance exacte dans les données locales.",
  federationNote:"Dans un système connecté, la recherche interrogerait alors en parallèle les 16 archives fédérées puis, sans résultat vérifié, l'IA cloud.",
  personsSection:"Sujets", eventsSection:"Événements historiques",
  statusLocal:"Local", statusOnline:"En ligne", statusRequest:"Sur demande", statusError:"Non accessible",
  statusUnverified:"Non vérifié", statusVerified:"Vérifié", statusPartial:"Partiellement vérifié",
  btnOpenFile:"Ouvrir le fichier", btnOpenOriginal:"Ouvrir l'original", btnRequestAccess:"Demander l'accès", btnGenerateDossier:"Ouvrir le dossier",
  btnBack:"Retour", btnClose:"Fermer", btnExploreDb:"Explorer", btnGenerateBio:"Générer le dossier vérifié",
  dossierConfidence:"Niveau de vérification", dossierTimelineTitle:"Chronologie", dossierPerspectivesTitle:"Points de vue comparés",
  dossierSourcesTitle:"Sources liées", dossierGapsTitle:"Champs manquants",
  dossierUnverifiedNote:"Sources repérées mais non encore récupérées — non utilisées dans le texte du dossier :",
  dossierAiNote:"Synthèse générée par IA à partir uniquement des sources vérifiées listées ci-dessus.",
  gapMissingField:"Champ manquant", gapSuggestedProvider:"Fournisseur suggéré", gapPriorityHigh:"Priorité haute",
  gapPriorityMedium:"Priorité moyenne", gapPriorityLow:"Priorité basse",
  exploreFilterPlaceholder:"Filtrer par nom, lieu, unité…", exploreRows:"fiches", explorePrev:"Précédent", exploreNext:"Suivant",
  explorePage:"Page", perspectiveIntlNote:"Recoupé avec des archives internationales",
  lightboxTitle:"Aperçu du document", lightboxPlaceholderNote:"Aperçu de démonstration — le système connecté afficherait ici la numérisation originale.",
  lightboxOpenExternal:"Ouvrir sur le site de l'archive",
  footerAbout:"Voci dal Fronte est une archive fédérée pour la recherche historique sur les soldats, disparus, victimes et rapatriés des deux guerres mondiales.",
  footerNote:"Les données historiques sont présentées dans la langue d'origine de la source.", footerAdminLink:"Espace opérateurs",
  adminTitle:"Espace opérateurs", adminSubtitle:"Import, extraction et enrichissement — réservé aux conservateurs de l'archive.",
  adminBackPublic:"Retour au site public", adminImportTitle:"Import de documents", adminExtractionTitle:"Avancement des extractions",
  adminProvidersTitle:"État de la fédération des fournisseurs", adminCreditsTitle:"Crédits IA cloud",
  adminDemoNote:"Panneau de démonstration — les actions ne sont pas connectées à un backend dans ce prototype.",
  povItaly:"Sources italiennes", povAxis:"Sources de l'Axe", povAllied:"Sources alliées", povIntl:"Archives internationales",
  loading:"Chargement…", langLabel:"Langue", demoBadge:"Donnée de démonstration", of:"sur",
  btnGenerateReport:"Générer le rapport", reportExplanation:"Analyse toutes les sources vérifiées de l'événement et extrait uniquement les faits communs à toutes les sources, produisant une reconstitution objective.",
  reportLoading:"Génération en cours…", reportTitle:"Rapport IA — Faits vérifiés par convergence des sources",
  reportAiBadge:"Rapport IA", sourcesLabel:"sources",
  eventsBasedOnSearches:"Événements en vedette sélectionnés selon vos recherches récentes.",
},
};

// DB_STATS: valori di default mostrati durante il caricamento, poi sostituiti dal backend
export const DB_STATS = [
  { id:"internati",    key:"dbInternati",    value:0,   sub:"IMI · Archivio di Stato Bolzano" },
  { id:"caduti",       key:"dbCaduti",       value:0,   sub:"6 fonti nazionali" },
  { id:"decorati",     key:"dbDecorati",     value:0,   sub:"ISTORECO + Nastro Azzurro" },
  { id:"entita",       key:"dbEntita",       value:0,   sub:"persone · luoghi · eventi · unità" },
  { id:"collegamenti", key:"dbCollegamenti", value:0,   sub:"star schema cross-dataset" },
  { id:"documenti",    key:"dbDocumenti",    value:0,   sub:"scansioni originali OCR" },
  { id:"fonti",        key:"dbFonti",        value:0,   sub:"schede di collocazione esterne" },
  { id:"eventi",       key:"dbEventi",       value:0,   sub:"ricostruzioni multi-prospettiva" },
  { id:"providers",    key:"dbProviders",    value:0,   sub:"archivi nazionali e internazionali" },
];

// ── Carica statistiche reali dal backend ──────────────────────────────────────
export async function loadLiveStats() {
  try {
    const [statusR, decoratiR, entitaR, fondiR, naraR, eventsR, sourceStatsR, alboR, cwgcR, ministR, sardiR, bolgnaR, nastrR, franciaR] = await Promise.all([
      fetch('/api/status').then(r=>r.json()).catch(()=>({})),
      fetch('/api/decorati').then(r=>r.json()).catch(()=>({})),
      fetch('/api/entita').then(r=>r.json()).catch(()=>({})),
      fetch('/api/fondi').then(r=>r.json()).catch(()=>({})),
      fetch('/api/nara').then(r=>r.json()).catch(()=>({})),
      fetch('/api/events').then(r=>r.json()).catch(()=>({})),
      fetch('/api/source/stats').then(r=>r.json()).catch(()=>({})),
      fetch('/api/albooro').then(r=>r.json()).catch(()=>({})),
      fetch('/api/cwgc').then(r=>r.json()).catch(()=>({})),
      fetch('/api/ministero').then(r=>r.json()).catch(()=>({})),
      fetch('/api/sardi').then(r=>r.json()).catch(()=>({})),
      fetch('/api/bologna').then(r=>r.json()).catch(()=>({})),
      fetch('/api/nastroazzurro').then(r=>r.json()).catch(()=>({})),
      fetch('/api/francia_ww1').then(r=>r.json()).catch(()=>({})),
    ]);

    const caduti = (alboR.count||0)+(cwgcR.count||0)+(ministR.count||0)+(sardiR.count||0)+(bolgnaR.count||0)+(franciaR.count||0);
    const decorati = (decoratiR.count||0)+(nastrR.count||0);

    return [
      { id:"internati",    key:"dbInternati",    value: statusR.total_internati||0,        sub:"IMI · Archivio di Stato Bolzano" },
      { id:"caduti",       key:"dbCaduti",       value: caduti,                            sub:"6 fonti nazionali" },
      { id:"decorati",     key:"dbDecorati",     value: decorati,                          sub:"ISTORECO + Nastro Azzurro" },
      { id:"entita",       key:"dbEntita",       value: entitaR.count_entita||0,           sub:"persone · luoghi · eventi · unità" },
      { id:"collegamenti", key:"dbCollegamenti", value: entitaR.count_collegamenti||0,     sub:"star schema cross-dataset" },
      { id:"documenti",    key:"dbDocumenti",    value: (naraR.count||0)+(fondiR.count_fondi||0), sub:"scansioni originali OCR" },
      { id:"fonti",        key:"dbFonti",        value: sourceStatsR.total_sources||0,     sub:"schede di collocazione esterne" },
      { id:"eventi",       key:"dbEventi",       value: (eventsR.eventi||[]).length,       sub:"ricostruzioni multi-prospettiva" },
      { id:"providers",    key:"dbProviders",    value: sourceStatsR.providers||0,         sub:"archivi nazionali e internazionali" },
    ];
  } catch(e) {
    console.warn('loadLiveStats error:', e);
    return DB_STATS;
  }
}

// ── Mappa archivio → URL di ricerca nominale (costruito con cognome+nome) ────
// Restituisce null se l'archivio non ha ricerca online nominale diretta.
export function buildArchiveUrl(archivio, cognome, nome) {
  // Costruisce URL di ricerca nominale SOLO se l'archivio indicizzato
  // contiene effettivamente schede di quel tipo di soggetto.
  // Restituisce null se l'archivio non è navigabile per nome o se
  // il soggetto non può comparirvi (es. TNA per soldati italiani IMI).
  const c = encodeURIComponent((cognome||'').trim());
  const n = encodeURIComponent((nome||'').trim());
  const arch = (archivio||'').toLowerCase();

  // Arolsen Archives / ITS — contiene schede di tutti i nazionali internati
  if (arch.includes('arolsen') || arch.includes('its'))
    return `https://collections.arolsen-archives.org/en/search/?query=${c}+${n}`;

  // Onorcaduti (Ministero Difesa IT) — caduti e dispersi italiani
  if (arch.includes('onorcaduti') || (arch.includes('difesa') && !arch.includes('ufficio storico')))
    return `https://www.difesa.it/Il_Ministero/CadutiInGuerra/Pages/RicercaCaduti.aspx?cognome=${c}&nome=${n}`;

  // Albo d'Oro / cadutigrandeguerra — caduti italiani 1GM/2GM
  if (arch.includes("albo d'oro") || arch.includes('cadutigrandeguerra'))
    return `https://www.cadutigrandeguerra.it/ricerca/?cognome=${c}&nome=${n}`;

  // Nastro Azzurro / decorati al Valor Militare
  if (arch.includes('nastro azzurro') || arch.includes('valor militare') || arch.includes('istitutonastroazzurro'))
    return `https://decoratialvalormilitare.istitutonastroazzurro.org/?s=${c}+${n}`;

  // CWGC — caduti del Commonwealth (non italiani IMI → non usare per soggetti IMI,
  // ma utile per eventi come Tobruk dove ci sono caduti alleati)
  if (arch.includes('cwgc'))
    return `https://www.cwgc.org/find-records/find-war-dead/?familyName=${c}&firstName=${n}`;

  // Australian War Memorial — personale australiano
  if (arch.includes('australian war memorial') || arch.includes('awm'))
    return `https://www.awm.gov.au/collection/people/?query=${c}+${n}`;

  // Bundesarchiv invenio — documenti tedeschi (Scheda cattura, KTB, ecc.)
  if (arch.includes('bundesarchiv'))
    return `https://invenio.bundesarchiv.de/invenio/?q=${c}+${n}`;

  // Europeana — aggregatore europeo
  if (arch.includes('europeana'))
    return `https://www.europeana.eu/en/search?query=${c}+${n}`;

  // Mémoire des Hommes (SHD Francia) — personale francese/coloniale
  if (arch.includes('mémoire') || arch.includes('shd'))
    return `https://www.memoiredeshommes.sga.defense.gouv.fr/fr/article.php?larub=24&titre=recherche-par-nom&q=${c}`;

  // NOTA: TNA (The National Archives, Kew) NON è incluso:
  // WO 361 e simili contengono missing personnel britannici, non italiani.
  // I link TNA vengono aggiunti solo come URL fissi di catalogo sulle fonti che li richiedono.

  // NOTA: NARA, USSME, Archivi di Stato, Arolsen richiesta → gestiti come locale/richiesta,
  // non come link di ricerca nominale (accesso non diretto o soggetti non indicizzati per nome).

  return null;
}

// ── Ricerca live: interroga il backend e converte in formato SUBJECTS ────────
export async function searchLive(query) {
  if (!query || query.trim().length < 2) return { subjects: {}, events: {}, confirmations: [], validations: [] };
  try {
    const res = await fetch(`/api/search-validated?q=${encodeURIComponent(query.trim())}&limit=20`).then(r=>r.json());
    const subjects = {};
    const eventsOut = {};
    const data = res.results || res;
    const internati = data.internati || [];
    const menzioni  = data.menzioni  || [];
    const decorati  = data.decorati  || [];
    const caduti    = data.caduti    || [];
    const confirmations = res.confirmations || [];
    const validations = res.validations || [];

    for (const ev of (data.events || [])) {
      const id = ev.id || ev.nome.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
      eventsOut[id] = {
        id, type: 'evento', name: ev.nome,
        subtitle: ev.descrizione || '',
        tags: (ev.keywords || []).slice(0, 3),
        status: 'verified', confidence: 0.95,
        timeline: [], perspectives: [], sources: [], gaps: [],
        _stats: { caduti: 0, decorati: 0, documenti: 0, fonti: 0, internati: 0 },
      };
    }

    for (const s of internati) {
      const id = `imi_${s.id}`;
      const tags = ['IMI · 2GM'];
      if (s.luogo_nascita) tags.push(s.luogo_nascita);
      if (s.sorte) tags.push(`Sorte: ${s.sorte}`);
      subjects[id] = {
        id, type:'persona',
        name: `${s.cognome||''} ${s.nome||''}`.trim() || `Soldato #${s.id}`,
        subtitle: `Internato Militare Italiano${s.luogo_internamento ? ' — '+s.luogo_internamento : ''}`,
        tags, status: s.needs_review ? 'partial' : 'verified', confidence: s.needs_review ? 0.6 : 0.85,
        timeline: [], perspectives: [], sources: [], gaps: [],
        _soldierId: s.id, _cognome: s.cognome||'', _nome: s.nome||'',
      };
    }

    for (const d of decorati.slice(0,5)) {
      const id = `dec_${d.id||d.cognome}`;
      subjects[id] = {
        id, type:'persona',
        name: `${d.cognome||''} ${d.nome||''}`.trim(),
        subtitle: `Decorato al Valor Militare${d.decorazione ? ' — '+d.decorazione : ''}`,
        tags: ['Decorato', d.guerra||'2GM', d.source||'ISTORECO'],
        status:'partial', confidence:0.7,
        timeline:[], perspectives:[], sources:[], gaps:[],
        _cognome: d.cognome||'', _nome: d.nome||'',
      };
    }

    for (const c of caduti.slice(0,5)) {
      const cnome = `${c.cognome||c.nom||''} ${c.nome||''}`.trim();
      const id = `cad_${cnome.replace(/\s+/g,'_').toLowerCase()}`;
      subjects[id] = {
        id, type:'persona',
        name: cnome || 'Caduto',
        subtitle: `Caduto${c._source_label ? ' — '+c._source_label : ''}${c.luogo_morte ? ', '+c.luogo_morte : ''}`,
        tags: ['Caduto', c._source_label||''],
        status:'verified', confidence:0.9,
        timeline:[], perspectives:[], sources:[], gaps:[],
        _cognome: c.cognome||c.nom||'', _nome: c.nome||'',
      };
    }

    return { subjects, events: eventsOut, confirmations, validations, searchStatus: res.status || 'local_only', externalSources: res.external_sources || [] };
  } catch(e) {
    console.warn('searchLive error:', e);
    return { subjects:{}, events:{}, confirmations: [], validations: [] };
  }
}

// ── Carica dossier completo per un soldato IMI dal backend ───────────────────
// Chiama in parallelo:
//   /fonti   → fonti dal DB locale (già indicizzate)
//   /links   → ricerca federata REALE su tutti i provider (verifica esistenza)
//   /opengraph → card anagrafica
// Solo i link effettivamente trovati vengono mostrati nel dossier.
export async function loadSoldierDossier(soldierId) {
  try {
    const [fontiRes, linksRes, ogRes] = await Promise.all([
      fetch(`/api/internati/${soldierId}/fonti`).then(r=>r.json()).catch(()=>({})),
      fetch(`/api/internati/${soldierId}/links`).then(r=>r.json()).catch(()=>({links:[]})),
      fetch(`/api/internati/${soldierId}/opengraph`).then(r=>r.json()).catch(()=>({})),
    ]);

    const card     = ogRes.card || {};
    const cognome  = fontiRes.cognome || linksRes.cognome || '';
    const nome     = fontiRes.nome    || linksRes.nome    || '';

    // ── Fonti verificate (da ricerca federata reale) ──────────────────────────
    // Solo record effettivamente trovati sui provider — nessun URL generato a vuoto
    const verifiedLinks = (linksRes.links || []).filter(lk => lk.url);
    const seenUrls = new Set();
    const sources = [];

    for (const lk of verifiedLinks) {
      if (seenUrls.has(lk.url)) continue;
      seenUrls.add(lk.url);
      sources.push({
        id: `lnk_${sources.length}`,
        title: lk.titolo || lk.archivio,
        archive: lk.archivio,
        access: lk.access_type || 'online',
        kind: lk.source_type || 'metadato',
        url: lk.url,
        _provider: lk.provider,
        _score: lk.score,
      });
    }

    // ── Fonti DB locale (accesso richiesta/locale) — aggiunte solo se non già coperte ──
    for (const [arch, items] of Object.entries(fontiRes.by_archive||{})) {
      for (const f of items) {
        const access = f.access_type || 'richiesta';
        if (access === 'online') continue; // già coperto dalla ricerca federata o non trovato
        const urlDiretto = f.url || null;
        sources.push({
          id: String(f.id||`db_${sources.length}`),
          title: (f.titolo||f.segnatura||arch).substring(0,80),
          archive: arch,
          access,
          kind: 'metadato',
          url: urlDiretto,
        });
      }
    }

    // ── Prospettive dinamiche generate dai link verificati ────────────────────
    // Raggruppa per pov: italiano (it), tedesco/cattura (de), alleato (allied)
    const itSources  = sources.filter(s => {
      const a = (s.archive||'').toLowerCase();
      return a.includes('difesa') || a.includes('onorcaduti') || a.includes('nastro') ||
             a.includes('ussme') || a.includes('stato') || a.includes('antenati') ||
             a.includes('cadutigrandeguerra') || a.includes('internetculturale');
    });
    const deSources  = sources.filter(s => {
      const a = (s.archive||'').toLowerCase();
      return a.includes('bundesarchiv') || a.includes('arolsen') || a.includes('oesta') ||
             a.includes('deutsche') || a.includes('ddb');
    });
    const allSources = sources.filter(s => {
      const a = (s.archive||'').toLowerCase();
      return a.includes('cwgc') || a.includes('tna') || a.includes('nara') ||
             a.includes('awm') || a.includes('europeana') || a.includes('gallica') ||
             a.includes('mémoire') || a.includes('trove');
    });

    const perspectives = [];
    if (itSources.length)
      perspectives.push({ pov:'it',     summary:`${itSources.length} fonte/i italiana/e trovata/e per ${cognome} ${nome}.`,  sourceIds: itSources.map(s=>s.id) });
    if (deSources.length)
      perspectives.push({ pov:'de',     summary:`${deSources.length} documento/i tedesco/i o ITS trovato/i per ${cognome} ${nome}.`, sourceIds: deSources.map(s=>s.id) });
    if (allSources.length)
      perspectives.push({ pov:'allied', summary:`${allSources.length} fonte/i alleata/e trovata/e per ${cognome} ${nome}.`, sourceIds: allSources.map(s=>s.id) });

    // ── Timeline ──────────────────────────────────────────────────────────────
    const timeline = [];
    if (card.nascita)      timeline.push({ date:'—', label:`Nascita: ${card.nascita}`,            pov:'it',     sourceId:'' });
    if (card.cattura)      timeline.push({ date:'—', label:`Cattura: ${card.cattura}`,            pov:'de',     sourceId:'' });
    if (card.internamento) timeline.push({ date:'—', label:`Internamento: ${card.internamento}`,  pov:'de',     sourceId:'' });
    if (card.sorte)        timeline.push({ date:'—', label:`Sorte: ${card.sorte}`,                pov:'it',     sourceId:'' });

    return { timeline, sources, perspectives, _cognome: cognome, _nome: nome };
  } catch(e) {
    console.warn('loadSoldierDossier error:', e);
    return { timeline:[], sources:[], perspectives:[] };
  }
}

// ── Carica dossier evento dal backend (eventi curati + 1GM) ──────────────────
export async function loadEventDossier(eventName) {
  try {
    const encoded = encodeURIComponent(eventName.replace(/\s+/g, '+'));
    const [dossierR, cadutiR, decoratiR, internatiR] = await Promise.all([
      fetch(`/api/events/1gm/${encoded}`).then(r => r.json()).catch(() => ({})),
      fetch(`/api/events/1gm/${encoded}/caduti?limit=50`).then(r => r.json()).catch(() => ({caduti:[],total:0})),
      fetch(`/api/events/1gm/${encoded}/decorati?limit=50`).then(r => r.json()).catch(() => ({decorati:[],total:0})),
      fetch(`/api/events/${encoded}/internati?limit=50`).then(r => r.json()).catch(() => ({internati:[],total:0})),
    ]);
    return {
      event: dossierR.event || {},
      caduti: cadutiR.caduti || [],
      caduti_total: cadutiR.total || 0,
      decorati: decoratiR.decorati || [],
      decorati_total: decoratiR.total || 0,
      documenti: dossierR.documenti?.items || [],
      fonti: dossierR.fonti?.items || [],
      internati: internatiR.internati || dossierR.internati?.items || [],
      internati_total: internatiR.total || 0,
      ok: dossierR.ok !== false,
    };
  } catch(e) {
    console.warn('loadEventDossier error:', e);
    return { ok: false, caduti: [], decorati: [], documenti: [], fonti: [], internati: [] };
  }
}

// ── Carica eventi canonici 1GM+WW2 dal backend ───────────────────────────────
export async function loadEvents1gm() {
  try {
    const r = await fetch('/api/events/1gm').then(r => r.json());
    const eventi = r.eventi || [];
    const events = {};
    for (const ev of eventi) {
      const id = ev.nome.toLowerCase()
        .replace(/[àá]/g, 'a').replace(/[èé]/g, 'e').replace(/[ìí]/g, 'i').replace(/[òó]/g, 'o').replace(/[ùú]/g, 'u')
        .replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
      events[id] = {
        id, type: 'evento', name: ev.nome,
        subtitle: `${ev.data_inizio || '?'} – ${ev.data_fine || '?'}, ${ev.luogo || ''}`,
        tags: ev.aliases?.slice(0, 3) || [],
        status: 'verified', confidence: 0.95,
        timeline: [], perspectives: [], sources: [], gaps: [],
        _stats: { caduti: ev.caduti||0, decorati: ev.decorati||0, documenti: ev.documenti||0, fonti: ev.fonti||0, internati: ev.internati||0 },
      };
    }
    return events;
  } catch(e) {
    console.warn('loadEvents1gm error', e);
    return {};
  }
}

// ── Carica crediti AI dal backend ────────────────────────────────────────────
export async function loadLiveCredits() {
  try {
    return await fetch('/api/credits').then(r=>r.json());
  } catch(e) { return {}; }
}

// ── Carica stato estrazioni per pannello admin ───────────────────────────────
export async function loadAdminStatus() {
  try {
    const [status, fondi, decorati, entita, srcStats] = await Promise.all([
      fetch('/api/status').then(r=>r.json()).catch(()=>({})),
      fetch('/api/fondi').then(r=>r.json()).catch(()=>({})),
      fetch('/api/decorati').then(r=>r.json()).catch(()=>({})),
      fetch('/api/entita').then(r=>r.json()).catch(()=>({})),
      fetch('/api/source/stats').then(r=>r.json()).catch(()=>({})),
    ]);
    return { status, fondi, decorati, entita, srcStats };
  } catch(e) { return {}; }
}

export const PROVIDERS = [
  { name:"Arolsen Archives (ITS)", country:"DE" }, { name:"Bundesarchiv", country:"DE" },
  { name:"Archivportal-D (DDB)", country:"DE" }, { name:"The National Archives (TNA)", country:"UK" },
  { name:"Europeana", country:"EU" }, { name:"Gallica / BnF", country:"FR" },
  { name:"SHD — Mémoire des Hommes", country:"FR" }, { name:"Internet Archive", country:"US" },
  { name:"Google Books", country:"US" }, { name:"HathiTrust", country:"US" },
  { name:"ABMC", country:"US" }, { name:"Australian War Memorial", country:"AU" },
  { name:"Library and Archives Canada", country:"CA" }, { name:"Internet Culturale (OPAC SBN)", country:"IT" },
  { name:"USSME", country:"IT" }, { name:"Archivi di Stato", country:"IT" },
];

// access: locale (file cached) · online (fetchable) · richiesta (login/permission) · errore
export const SUBJECTS = {
  gaiaschi: {
    id:"gaiaschi", type:"persona", name:"Luigi Gaiaschi", _cognome:"Gaiaschi", _nome:"Luigi",
    subtitle:"Soldato, Internato Militare Italiano (IMI) — 2ª Guerra Mondiale",
    tags:["IMI · 2GM","Nibbiano (Piacenza)","Sorte: rimpatriato"], status:"partial", confidence:0.72,
    timeline:[
      { date:"1912-01-09", label:"Nascita a Nibbiano (Piacenza)", pov:"it", sourceId:"g1" },
      { date:"1943-09-12", label:"Catturato in Grecia dopo l'armistizio dell'8 settembre 1943", pov:"it", sourceId:"g1" },
    ],
    perspectives:[
      { pov:"it", summary:"Registro IMI: nato a Nibbiano (Piacenza) il 9 gennaio 1912, catturato in Grecia il 12 settembre 1943. Divergenza tra fonti italiane (Belgrado) e fonti dell'Asse (Grecia) sul luogo di cattura — confermata Grecia.", sourceIds:["g1"] },
    ],
    sources:[
      { id:"g1", title:"Registro IMI — GAIASCHI Luigi (id 22808)", archive:"Database locale IMI", access:"locale", kind:"metadato" },
    ],
    gaps:[
      { field:"campo di internamento specifico", provider:"Arolsen Archives", priority:"medium" },
      { field:"data e luogo di rimpatrio", provider:"Archivio di Stato Bolzano", priority:"medium" },
      { field:"unità militare di appartenenza", provider:"USSME", priority:"low" },
    ],
  },
  rossi_imi:{
    id:"rossi_imi", type:"persona", name:"Mario Rossi", _cognome:"Rossi", _nome:"Mario",
    subtitle:"Internato Militare Italiano — omonimo (1) — 2ª Guerra Mondiale",
    tags:["IMI · 2GM","Bergamo","Sorte: disperso"], status:"unverified", confidence:0.31,
    timeline:[
      { date:"1920-06-02", label:"Nascita a Bergamo", pov:"it", sourceId:"r1" },
      { date:"1943-09-15", label:"Catturato in Grecia dopo l'armistizio", pov:"de", sourceId:"r1" },
      { date:"1944", label:"Ultima menzione nei registri di internamento — nessun dato successivo", pov:"de", sourceId:"r1" },
    ],
    perspectives:[
      { pov:"it", summary:"Unico riscontro nel registro IMI; nessuna fonte di rimpatrio o decesso associata.", sourceIds:["r1"] },
    ],
    sources:[
      { id:"r1", title:"Registro IMI, vol. R, p. 88", archive:"Archivio di Stato di Bolzano", access:"locale", kind:"immagine" },
      { id:"r2", title:"Ricerca federata — nessun riscontro univoco (omonimia)", archive:"Arolsen Archives", access:"richiesta", kind:"metadato" },
    ],
    gaps:[
      { field:"sorte finale", provider:"CWGC", priority:"high" },
      { field:"reparto di appartenenza", provider:"USSME", priority:"medium" },
    ],
  },
  rossi_ministero:{
    id:"rossi_ministero", type:"persona", name:"Mario Rossi", _cognome:"Rossi", _nome:"Mario",
    subtitle:"Caduto, Ministero della Difesa — omonimo (2) — 1ª Guerra Mondiale",
    tags:["1GM","Isonzo 1917","Caduto"], status:"verified", confidence:0.86,
    timeline:[
      { date:"1893-11-09", label:"Nascita, luogo non specificato", pov:"it", sourceId:"m1" },
      { date:"1917-08-24", label:"Caduto sul fronte dell'Isonzo", pov:"it", sourceId:"m1" },
      { date:"1917", label:"Iscritto all'Albo d'Oro dei Caduti", pov:"it", sourceId:"m2" },
    ],
    perspectives:[
      { pov:"it", summary:"Doppio riscontro tra Banca Dati Caduti Onorcaduti e Albo d'Oro, coerenti su data e luogo di morte.", sourceIds:["m1","m2"] },
    ],
    sources:[
      { id:"m1", title:"Banca Dati Caduti Onorcaduti — ricerca nominativa", archive:"Ministero della Difesa", access:"online", kind:"metadato" },
      { id:"m2", title:"Albo d'Oro dei Caduti — ricerca nominativa", archive:"cadutigrandeguerra.it", access:"online", kind:"metadato" },
    ],
    gaps:[],
  },
  bianchi:{
    id:"bianchi", type:"persona", name:"Ernesto Bianchi", _cognome:"Bianchi", _nome:"Ernesto",
    subtitle:"Decorato al Valor Militare — 2ª Guerra Mondiale",
    tags:["Nastro Azzurro","Decorazione"], status:"partial", confidence:0.6,
    timeline:[
      { date:"1943-12-01", label:"Azione decorata, teatro balcanico", pov:"it", sourceId:"b1" },
      { date:"1944", label:"Decreto di concessione della decorazione", pov:"it", sourceId:"b1" },
    ],
    perspectives:[ { pov:"it", summary:"Motivazione del decreto conservata nel database Nastro Azzurro; nessun riscontro estero associato.", sourceIds:["b1"] } ],
    sources:[ { id:"b1", title:"Ricerca decorati al Valor Militare", archive:"Nastro Azzurro / Ministero Difesa", access:"online", kind:"metadato" } ],
    gaps:[ { field:"unità di appartenenza", provider:"USSME", priority:"low" } ],
  },
  baracca:{
    id:"baracca", type:"persona", name:"Francesco Baracca", _cognome:"Baracca", _nome:"Francesco",
    subtitle:"Asso dell'aviazione italiana — 1ª Guerra Mondiale",
    tags:["1GM","Aviazione","Medaglia d'Oro"], status:"verified", confidence:0.92,
    timeline:[
      { date:"1888-05-09", label:"Nascita a Lugo di Romagna (Ravenna)", pov:"it", sourceId:"ba1" },
      { date:"1915-05-31", label:"Prima vittoria aerea sulle Alpi", pov:"it", sourceId:"ba2" },
      { date:"1917-11-01", label:"Comando della 91ª Squadriglia aeroportata", pov:"it", sourceId:"ba2" },
      { date:"1918-06-19", label:"Abbattimento del 34º e ultimo aereo nemico", pov:"it", sourceId:"ba2" },
      { date:"1918-06-19", label:"Caduta a Montello (Treviso)", pov:"it", sourceId:"ba3" },
    ],
    perspectives:[
      { pov:"it", summary:"Medaglia d'Oro al Valor Militare, 34 vittorie aeree confermate; simbolo dell'aviazione italiana della Grande Guerra.", sourceIds:["ba1","ba2","ba3"] },
      { pov:"allied", summary:"Decorazioni francesi e britanniche confermano il ruolo di Baracca tra gli assi alleati.", sourceIds:["ba4"] },
    ],
    sources:[
      { id:"ba1", title:"Scheda biografica Francesco Baracca", archive:"Ministero della Difesa — Medaglia d'Oro al Valor Militare", access:"online", kind:"metadato" },
      { id:"ba2", title:"Francesco Baracca — l'asso dell'aviazione italiana", archive:"Istituto Storico della Grande Guerra di Gorizia", access:"online", kind:"metadato" },
      { id:"ba3", title:"Memoriale e museo Francesco Baracca", archive:"Comune di Lugo di Romagna", access:"online", kind:"metadato" },
      { id:"ba4", title:"Foreign decorations — Captain Baracca", archive:"The National Archives (TNA)", access:"richiesta", kind:"metadato" },
    ],
    gaps:[
      { field:"verbali di volo originali", provider:"Archivio dell'Aeronautica Militare", priority:"medium" },
    ],
  },
  toti:{
    id:"toti", type:"persona", name:"Enrico Toti", _cognome:"Toti", _nome:"Enrico",
    subtitle:"Patriota, ciclista ed eroe della 1ª Guerra Mondiale",
    tags:["1GM","Medaglia d'Oro","Roma"], status:"verified", confidence:0.90,
    timeline:[
      { date:"1882-08-20", label:"Nascita a Roma", pov:"it", sourceId:"t1" },
      { date:"1911", label:"Incidente in bicicletta: amputazione di entrambe le gambe", pov:"it", sourceId:"t1" },
      { date:"1915-05-23", label:"Volontariato in trincea nonostante le menomazioni", pov:"it", sourceId:"t2" },
      { date:"1916-08-06", label:"Caduta a Monfalcone (Gorizia) durante l'offensiva del Carso", pov:"it", sourceId:"t2" },
      { date:"1916", label:"Medaglia d'Oro al Valor Militare alla memoria", pov:"it", sourceId:"t3" },
    ],
    perspectives:[
      { pov:"it", summary:"Medaglia d'Oro alla memoria per aver lanciato bombe a mano contro il nemico nonostante le gravi menomazioni.", sourceIds:["t1","t2","t3"] },
    ],
    sources:[
      { id:"t1", title:"Enrico Toti — scheda eroe", archive:"ANPI", access:"online", kind:"metadato" },
      { id:"t2", title:"Enrico Toti", archive:"Istituto per la Storia del Risorgimento italiano", access:"online", kind:"metadato" },
      { id:"t3", title:"Medaglia d'Oro al Valor Militare Enrico Toti", archive:"Ministero della Difesa", access:"online", kind:"metadato" },
    ],
    gaps:[
      { field:"lettere dal fronte", provider:"Archivio di Stato di Roma", priority:"low" },
    ],
  },
};

export const EVENTS = {
  caporetto:{
    id:"caporetto", type:"evento", name:"Battaglia di Caporetto", subtitle:"24 ottobre – 12 novembre 1917, Isonzo",
    tags:["1GM","Isonzo","Disastro"], status:"verified", confidence:0.95,
    timeline:[
      { date:"1917-10-24", label:"Offensiva austro-tedesca con gas e infiltrazioni", pov:"de", sourceId:"cap1" },
      { date:"1917-10-27", label:"Cedimento del fronte italiano; ritirata verso il Piave", pov:"it", sourceId:"cap2" },
      { date:"1917-11-12", label:"Fine dell'offensiva lungo il Piave", pov:"de", sourceId:"cap3" },
    ],
    perspectives:[
      { pov:"it", summary:"La disfatta di Caporetto provocò circa 600.000 perdite e il trasferimento del Comando supremo a Diaz.", sourceIds:["cap2","cap4"] },
      { pov:"de", summary:"L'offensiva di Caporetto (12ª battaglia dell'Isonzo) fu progettata con tattiche di infiltrazione e gas.", sourceIds:["cap1","cap3"] },
      { pov:"allied", summary:"Britannici e francesi inviarono rinforzi per sostenere la linea del Piave.", sourceIds:["cap5"] },
    ],
    sources:[
      { id:"cap1", title:"Der Weltkrieg 1914–1918 — Band 13", archive:"Bundesarchiv", access:"richiesta", kind:"metadato" },
      { id:"cap2", title:"Caporetto 1917", archive:"Istituto Storico della Grande Guerra di Gorizia", access:"online", kind:"metadato" },
      { id:"cap3", title:"L'ultima offensiva austro-tedesca sul Piave", archive:"Österreichisches Staatsarchiv", access:"richiesta", kind:"metadato" },
      { id:"cap4", title:"Ordine del giorno Cadorna n. 11100", archive:"Ufficio Storico SME", access:"locale", kind:"immagine" },
      { id:"cap5", title:"Allied support to Italian front 1917", archive:"The National Archives (TNA)", access:"richiesta", kind:"metadato" },
    ], gaps:[],
  },
  vittorio_veneto:{
    id:"vittorio_veneto", type:"evento", name:"Battaglia di Vittorio Veneto", subtitle:"24 ottobre – 4 novembre 1918, Veneto",
    tags:["1GM","Vittoria","Armistizio"], status:"verified", confidence:0.95,
    timeline:[
      { date:"1918-10-24", label:"Offensiva finale dell'esercito italiano sul Piave e nel Grappa", pov:"it", sourceId:"vv1" },
      { date:"1918-10-30", label:"Rottura del fronte austriaco a Vittorio Veneto", pov:"it", sourceId:"vv2" },
      { date:"1918-11-03", label:"Armistizio di Villa Giusti", pov:"it", sourceId:"vv3" },
    ],
    perspectives:[
      { pov:"it", summary:"L'offensiva di Vittorio Veneto determinò il crollo dell'Impero austro-ungarico e l'armistizio del 3 novembre.", sourceIds:["vv1","vv2","vv3"] },
      { pov:"de", summary:"I registri austro-ungarici documentano l'evolversi delle trattative d'armistizio.", sourceIds:["vv4"] },
      { pov:"allied", summary:"Gli Alleati riconobbero la vittoria italiana come decisiva per la fine del conflitto sul fronte sud.", sourceIds:["vv5"] },
    ],
    sources:[
      { id:"vv1", title:"L'offensiva di Vittorio Veneto", archive:"Ufficio Storico SME", access:"locale", kind:"immagine" },
      { id:"vv2", title:"Battaglia di Vittorio Veneto — 24 ottobre-4 novembre 1918", archive:"Istituto Storico della Grande Guerra di Gorizia", access:"online", kind:"metadato" },
      { id:"vv3", title:"Armistizio di Villa Giusti", archive:"Ministero della Difesa", access:"online", kind:"metadato" },
      { id:"vv4", title:"Armistice negotiations, 1918", archive:"Österreichisches Staatsarchiv", access:"richiesta", kind:"metadato" },
      { id:"vv5", title:"Italian offensive October 1918", archive:"The National Archives (TNA)", access:"richiesta", kind:"metadato" },
    ], gaps:[],
  },
  undicesima_isonzo:{
    id:"undicesima_isonzo", type:"evento", name:"Undicesima battaglia dell'Isonzo", subtitle:"18 agosto – 15 settembre 1917, Bainsizza",
    tags:["1GM","Isonzo","Offensiva"], status:"verified", confidence:0.90,
    timeline:[
      { date:"1917-08-18", label:"Offensiva italiana sul Bainsizza e monte San Gabriele", pov:"it", sourceId:"i1" },
      { date:"1917-09-04", label:"Conquista della Bainsizza", pov:"it", sourceId:"i2" },
      { date:"1917-09-15", label:"Sospensione dell'offensiva per esaurimento munizioni e truppe", pov:"it", sourceId:"i3" },
    ],
    perspectives:[
      { pov:"it", summary:"L'undicesima battaglia ottenne il successo tattico della Bainsizza, ma non conseguì una vittoria strategica.", sourceIds:["i1","i2","i3"] },
      { pov:"de", summary:"Fonti austro-ungariche registrano la ritirata ordinata su linee più arretrate.", sourceIds:["i4"] },
    ],
    sources:[
      { id:"i1", title:"Bainsizza e San Gabriele, 1917", archive:"Ufficio Storico SME", access:"locale", kind:"immagine" },
      { id:"i2", title:"La battaglia della Bainsizza", archive:"Istituto Storico della Grande Guerra di Gorizia", access:"online", kind:"metadato" },
      { id:"i3", title:"Undicesima battaglia dell'Isonzo", archive:"ANPI", access:"online", kind:"metadato" },
      { id:"i4", title:"Frontberichte Isonzo 1917", archive:"Österreichisches Kriegsarchiv", access:"richiesta", kind:"metadato" },
    ], gaps:[],
  },
  cefalonia:{
    id:"cefalonia", type:"evento", name:"Cefalonia — Divisione Acqui", subtitle:"Settembre 1943, isola di Cefalonia (Grecia)",
    tags:["1943","Grecia","Eccidio"], status:"verified", confidence:0.88,
    timeline:[
      { date:"1943-09-08", label:"Annuncio dell'armistizio; la Divisione Acqui rifiuta la resa alle truppe tedesche", pov:"it", sourceId:"c1" },
      { date:"1943-09-15", label:"Combattimenti tra reparti italiani e tedeschi sull'isola", pov:"de", sourceId:"c2" },
      { date:"1943-09-24", label:"Esecuzioni sommarie di militari italiani catturati", pov:"de", sourceId:"c2" },
      { date:"1945", label:"Prime indagini alleate sulle stragi", pov:"allied", sourceId:"c3" },
    ],
    perspectives:[
      { pov:"it",     summary:"Fonti USSME e ANPI ricostruiscono la decisione di resistenza e l'elenco delle vittime italiane.",                            sourceIds:["c1"] },
      { pov:"de",     summary:"I documenti Bundesarchiv riportano gli ordini operativi tedeschi e i rapporti delle unità coinvolte.",                          sourceIds:["c2"] },
      { pov:"allied", summary:"Le indagini TNA/NARA del dopoguerra raccolgono testimonianze usate nei processi per crimini di guerra.",                        sourceIds:["c3","c4"] },
    ],
    sources:[
      { id:"c1", title:"Relazione ufficiale, fondo USSME", archive:"Ufficio Storico SME", access:"locale", kind:"immagine" },
      { id:"c2", title:"Kriegstagebuch 1. Gebirgs-Division, sett. 1943", archive:"Bundesarchiv Militärarchiv", access:"online", kind:"metadato", url:"https://invenio.bundesarchiv.de/invenio/direktlink/a8d18c73-a22c-47d4-b37d-68a1f66e0e7c/" },
      { id:"c3", title:"WO 235 — War crimes trial records (catalogo serie)", archive:"TNA Discovery", access:"online", kind:"metadato", url:"https://discovery.nationalarchives.gov.uk/details/r/C13445" },
      { id:"c4", title:"Ricerca caduti per cognome", archive:"CWGC Debt of Honour", access:"online", kind:"metadato" },
    ], gaps:[],
  },
  mauthausen:{
    id:"mauthausen", type:"evento", name:"Mauthausen / Gusen — deportati italiani", subtitle:"1943–1945, Austria",
    tags:["Deportazione","Austria"], status:"partial", confidence:0.7,
    timeline:[
      { date:"1943", label:"Primi trasporti di internati militari italiani verso il sistema concentrazionario", pov:"de", sourceId:"mh1" },
      { date:"1945-05-05", label:"Liberazione del campo da parte delle truppe alleate", pov:"allied", sourceId:"mh2" },
    ],
    perspectives:[
      { pov:"de",     summary:"I registri di immatricolazione Arolsen tracciano gli arrivi e i trasferimenti interni al sistema.",          sourceIds:["mh1"] },
      { pov:"allied", summary:"I rapporti di liberazione documentano le condizioni dei sopravvissuti al momento della liberazione.",     sourceIds:["mh2"] },
    ],
    sources:[
      { id:"mh1", title:"Arolsen Archives — ricerca online internati", archive:"Arolsen Archives", access:"online", kind:"metadato" },
      { id:"mh2", title:"NARA — 11th Armored Division, After Action Reports (Record Group 407)", archive:"NARA Catalog", access:"online", kind:"metadato", url:"https://catalog.archives.gov/id/305342" },
    ], gaps:[ { field:"elenco completo deportati italiani", provider:"Arolsen Archives", priority:"high" } ],
  },
  tobruk:{
    id:"tobruk", type:"evento", name:"Tobruk — prigionieri italiani", subtitle:"1941–1942, Africa Settentrionale",
    tags:["Africa Settentrionale","Prigionia"], status:"partial", confidence:0.55,
    timeline:[
      { date:"1941-01-22", label:"Caduta di Tobruk, cattura di reparti italiani", pov:"allied", sourceId:"t1" },
      { date:"1942", label:"Trasferimento dei prigionieri nei campi del Commonwealth", pov:"allied", sourceId:"t2" },
    ],
    perspectives:[ { pov:"allied", summary:"I registri britannici e del Commonwealth documentano cattura e instradamento verso i campi di prigionia.", sourceIds:["t1","t2"] } ],
    sources:[
      { id:"t1", title:"AWM54 — Operations reports, 6th Division (catalogo)", archive:"Australian War Memorial", access:"online", kind:"metadato", url:"https://www.awm.gov.au/collection/C1417366" },
      { id:"t2", title:"TNA — Prisoners of War Lists, WO 392 (catalogo serie)", archive:"TNA Discovery", access:"online", kind:"metadato", url:"https://discovery.nationalarchives.gov.uk/details/r/C14596" },
    ], gaps:[ { field:"elenco nominativo completo", provider:"TNA", priority:"medium" } ],
  },
  armir:{
    id:"armir", type:"evento", name:"ARMIR — Campagna di Russia", subtitle:"1942–1943, fronte orientale",
    tags:["Russia","Ritirata 1943"], status:"partial", confidence:0.6,
    timeline:[
      { date:"1942-08", label:"Schieramento dell'8ª Armata italiana sul Don", pov:"it", sourceId:"a1" },
      { date:"1943-01", label:"Ritirata durante l'offensiva sovietica", pov:"it", sourceId:"a1" },
    ],
    perspectives:[ { pov:"it", summary:"I fondi USSME ricostruiscono lo schieramento e la ritirata invernale dell'8ª Armata.", sourceIds:["a1"] } ],
    sources:[ { id:"a1", title:"Diario storico, 8ª Armata", archive:"Ufficio Storico SME", access:"locale", kind:"immagine" } ],
    gaps:[ { field:"riscontro prigionia sovietica", provider:"Archivi russi (non federato)", priority:"high" } ],
  },
  achse:{
    id:"achse", type:"evento", name:"Operazione Achse", subtitle:"Settembre 1943, disarmo delle forze italiane",
    tags:["1943","Disarmo"], status:"partial", confidence:0.65,
    timeline:[
      { date:"1943-09-09", label:"Avvio dell'operazione di disarmo delle forze armate italiane", pov:"de", sourceId:"ac1" },
    ],
    perspectives:[ { pov:"de", summary:"Gli ordini Wehrmacht in Bundesarchiv definiscono le modalità di disarmo per teatro operativo.", sourceIds:["ac1"] } ],
    sources:[ { id:"ac1", title:"Bundesarchiv invenio — ricerca Fall Achse / OKW settembre 1943", archive:"Bundesarchiv Militärarchiv", access:"online", kind:"metadato", url:"https://invenio.bundesarchiv.de/invenio/" } ],
    gaps:[],
  },
};

export const EXPLORE_TABLES = {
  internati: { labelKey:"dbInternati", cols:["Cognome","Nome","Nascita","Luogo nascita","Internamento","Sorte"],
    rows:[
      ["Gaiaschi","Luigi","14/03/1917","Bergamo","Norimberga (Kdo. 1054)","Rimpatriato"],
      ["Rossi","Mario","02/06/1920","Bergamo","—","Disperso"],
      ["Colombo","Aldo","09/11/1918","Milano","Stalag VII A","Rimpatriato"],
      ["Ferrari","Bruno","22/05/1921","Torino","Arbeitskommando 771","Deceduto"],
      ["Marino","Salvatore","03/01/1919","Palermo","—","Rimpatriato"],
    ]},
  caduti: { labelKey:"dbCaduti", cols:["Cognome","Nome","Guerra","Luogo morte","Data morte","Fonte"],
    rows:[
      ["Rossi","Mario","1ª GM","Isonzo","24/08/1917","Onorcaduti"],
      ["Greco","Antonio","1ª GM","Carso","1916","Albo d'Oro"],
      ["Villa","Pietro","2ª GM","Cefalonia","24/09/1943","CWGC"],
      ["Moretti","Carlo","1ª GM","Piave","1918","Caduti Bologna"],
    ]},
  decorati: { labelKey:"dbDecorati", cols:["Cognome","Nome","Decorazione","Teatro","Anno"],
    rows:[
      ["Bianchi","Ernesto","Medaglia di Bronzo","Balcani","1944"],
      ["Serra","Giovanni","Croce di Guerra","Africa Sett.","1942"],
    ]},
  entita: { labelKey:"dbEntita", cols:["Tipo","Valore","Collegamenti","Tabelle"],
    rows:[
      ["persona","Gaiaschi Luigi","6","internati, archivio_fonti, fonti_indice"],
      ["luogo","Cefalonia","214","caduti_cwgc, fondi_archivistici, entita"],
      ["unita","Divisione Acqui","58","fondi_archivistici, menzioni"],
    ]},
  documenti: { labelKey:"dbDocumenti", cols:["Archivio","Fondo","Tipo documento","Data","Stato OCR"],
    rows:[
      ["AUSSME","T315","Tätigkeitsbericht","1944-05","done"],
      ["NARA","T315","Lagebericht","1943-11","done"],
      ["Bundesarchiv","RH 24","Befehl","1943-09","partial"],
    ]},
  fonti: { labelKey:"dbFonti", cols:["Archivio","Titolo","Accesso","Confidenza"],
    rows:[
      ["Arolsen Archives","Scheda ITS trasferimento","richiesta","0.6"],
      ["TNA Discovery","WO 361 rapporti liberazione","online","0.8"],
      ["Bundesarchiv","Ordini operativi 1. Gebirgs-Division","online","0.9"],
    ]},
};
