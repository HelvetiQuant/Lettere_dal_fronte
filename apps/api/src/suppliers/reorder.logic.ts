/**
 * Logica di riordino "a livello target" (par level) — pura, testabile senza DB.
 *
 * Quando la giacenza scende sotto la soglia (`reorderLevel`), si propone di
 * riportarla al livello target (`parLevel`, o `reorderLevel` se non impostato).
 * Il fabbisogno è in unità BASE del prodotto; l'acquisto avviene in CONFEZIONI
 * (una confezione = `packSize` unità base), quindi si arrotonda per eccesso.
 */

export interface ReorderInput {
  quantity: number; // giacenza attuale (unità base)
  reorderLevel: number; // soglia che fa scattare il riordino
  parLevel: number; // livello target (0 = usa reorderLevel)
  packSize: number; // unità base per confezione (>=1)
}

export interface ReorderSuggestion {
  needed: boolean;
  targetLevel: number; // unità base
  deficitBase: number; // unità base mancanti al target
  packSize: number;
  packs: number; // confezioni da ordinare (arrotondate per eccesso)
  orderedBase: number; // unità base effettivamente ordinate (packs * packSize)
}

export function computeReorder(input: ReorderInput): ReorderSuggestion {
  const packSize = Math.max(1, Math.trunc(input.packSize || 1));
  const target = input.parLevel > 0 ? input.parLevel : input.reorderLevel;

  // Scatta solo se c'è una soglia e la giacenza è a/sotto soglia.
  const triggered = input.reorderLevel > 0 && input.quantity <= input.reorderLevel;
  const deficit = Math.max(0, target - input.quantity);

  if (!triggered || deficit <= 0) {
    return { needed: false, targetLevel: target, deficitBase: 0, packSize, packs: 0, orderedBase: 0 };
  }

  const packs = Math.ceil(deficit / packSize);
  return {
    needed: true,
    targetLevel: target,
    deficitBase: deficit,
    packSize,
    packs,
    orderedBase: packs * packSize,
  };
}
