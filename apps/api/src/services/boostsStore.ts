type BoostLevels = Record<string, { mastery_level: number; workshop_level: number }>;

const store: BoostLevels = {};

export function getBoostLevels(): BoostLevels {
  return { ...store };
}

export function setBoostLevels(levels: BoostLevels): void {
  for (const [token, values] of Object.entries(levels)) {
    store[token] = {
      mastery_level: Number(values.mastery_level || 0),
      workshop_level: Number(values.workshop_level || 0),
    };
  }
}

export function updateMasteryLevels(levels: Record<string, number>): number {
  let updated = 0;
  for (const [token, level] of Object.entries(levels)) {
    const symbol = token.toUpperCase();
    const mastery = Math.max(0, Math.min(10, Number(level || 0)));
    const existing = store[symbol] || { mastery_level: 0, workshop_level: 0 };
    store[symbol] = { ...existing, mastery_level: mastery };
    updated += 1;
  }
  return updated;
}

export function updateWorkshopLevels(levels: Record<string, number>): number {
  let updated = 0;
  for (const [token, level] of Object.entries(levels)) {
    const symbol = token.toUpperCase();
    const workshop = Math.max(0, Math.min(10, Number(level || 0)));
    const existing = store[symbol] || { mastery_level: 0, workshop_level: 0 };
    store[symbol] = { ...existing, workshop_level: workshop };
    updated += 1;
  }
  return updated;
}
