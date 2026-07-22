/**
 * Mappatura category -> postazione (station).
 *
 * Scelta di progetto: la station NON è un campo del prodotto ma viene DERIVATA
 * dalla `category` esistente (decisione del titolare). Alla creazione di una riga
 * ordine la station viene però DENORMALIZZATA su OrderItem.station, così le
 * statistiche storiche restano stabili anche se domani cambiamo questa tabella.
 */

export type Station = 'BAR' | 'TAVOLA_CALDA';

/**
 * Category che vanno al BAR. Tutto ciò che non è qui né in cucina cade nel
 * fallback (`DEFAULT_STATION`). Le category `ingrediente` non generano righe
 * ordine (sono solo di magazzino) quindi non serve mapparle.
 */
const BAR_CATEGORIES = new Set<string>([
  'aperitivo',
  'bevanda',
  'analcolico',
  'cocktail',
  'birra',
  'vino',
  'caffe',
  'caffetteria',
  'liquore',
  'distillato',
]);

const TAVOLA_CALDA_CATEGORIES = new Set<string>([
  'pizza',
  'primo',
  'secondo',
  'contorno',
  'panino',
  'piadina',
  'toast',
  'insalata',
  'dolce',
  'piatto',
  'tavola_calda',
  'griglia',
  'frittura',
]);

/** Postazione usata quando la category non è classificata. */
export const DEFAULT_STATION: Station = 'BAR';

/** Normalizza una category (case/spazi) per il confronto. */
function norm(category: string | null | undefined): string {
  return (category ?? '').trim().toLowerCase();
}

/** Restituisce la postazione per una category. */
export function stationForCategory(category: string | null | undefined): Station {
  const c = norm(category);
  if (TAVOLA_CALDA_CATEGORIES.has(c)) return 'TAVOLA_CALDA';
  if (BAR_CATEGORIES.has(c)) return 'BAR';
  return DEFAULT_STATION;
}

/** True se la category è esplicitamente classificata (utile per validare l'anagrafica). */
export function isCategoryClassified(category: string | null | undefined): boolean {
  const c = norm(category);
  return BAR_CATEGORIES.has(c) || TAVOLA_CALDA_CATEGORIES.has(c);
}

export const ALL_STATIONS: Station[] = ['BAR', 'TAVOLA_CALDA'];

export const STATION_LABEL: Record<Station, string> = {
  BAR: 'Bar',
  TAVOLA_CALDA: 'Tavola calda',
};
