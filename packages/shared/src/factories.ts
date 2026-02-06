import Papa from 'papaparse';
import type { FactoryLevelRow, FactoriesFromCsv, PriceMap } from './types';

export const CSV_TOKEN_ALIAS: Record<string, string> = {
  WORMS: 'WORM',
};

export const MASTERY_BONUSES: Record<number, number> = {
  0: 1.0,
  1: 1.0204,
  2: 1.0286,
  3: 1.0329,
  4: 1.0372,
  5: 1.0415,
  6: 1.0437,
  7: 1.0459,
  8: 1.0481,
  9: 1.0503,
  10: 1.0525,
};

export const WORKSHOP_MODIFIERS: Record<string, number[]> = {
  MUD: [0, 11.11, 23.46, 35.14, 47.06, 58.73, 69.49, 78.57, 85.19, 92.31, 100],
  CLAY: [0, 11.11, 23.46, 35.14, 47.06, 58.73, 69.49, 78.57, 85.19, 92.31, 100],
  SAND: [0, 11.11, 23.46, 35.14, 47.06, 58.73, 69.49, 78.57, 85.19, 92.31, 100],
  COPPER: [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
  SEAWATER: [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
  HEAT: [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
  ALGAE: [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
  LAVA: [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
  CERAMICS: [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
  STEEL: [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
  OXYGEN: [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
  GLASS: [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
  STEAM: [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
  GAS: [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
  STONE: [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
  SCREWS: [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
  FUEL: [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
  CEMENT: [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
  OIL: [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
  SULFUR: [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
  ACID: [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
  FIBERGLASS: [0, 7.53, 14.94, 21.95, 28.21, 33.33, 36.99, 40.85, 44.93, 49.25, 53.85],
  PLASTICS: [0, 7.53, 14.94, 21.95, 28.21, 33.33, 36.99, 40.85, 44.93, 49.25, 53.85],
  ENERGY: [0, 7.53, 14.94, 21.95, 28.21, 33.33, 36.99, 40.85, 44.93, 49.25, 53.85],
  HYDROGEN: [0, 7.53, 14.94, 21.95, 28.21, 33.33, 36.99, 40.85, 44.93, 49.25, 53.85],
  DYNAMITE: [0, 7.53, 14.94, 21.95, 28.21, 33.33, 36.99, 40.85, 44.93, 49.25, 53.85],
};

export const FACTORY_DISPLAY_ORDER_BASE = [
  'MUD',
  'CLAY',
  'SAND',
  'COPPER',
  'SEAWATER',
  'HEAT',
  'ALGAE',
  'LAVA',
  'CERAMICS',
  'STEEL',
  'OXYGEN',
  'GLASS',
  'GAS',
  'STONE',
  'STEAM',
  'SCREWS',
  'FUEL',
  'CEMENT',
  'OIL',
  'ACID',
  'SULFUR',
  'PLASTICS',
  'FIBERGLASS',
  'ENERGY',
  'HYDROGEN',
  'DYNAMITE',
];

export function normalizeToken(raw: string): string {
  const token = String(raw || '').trim().toUpperCase();
  if (!token) return '';
  return CSV_TOKEN_ALIAS[token] ?? token;
}

export function parseFactoriesFromCsv(csvText: string): FactoriesFromCsv {
  const factories: FactoriesFromCsv = {};
  const parsed = Papa.parse<Record<string, string>>(csvText, {
    header: true,
    skipEmptyLines: true,
  });

  for (const row of parsed.data) {
    if (!row) continue;
    const token = normalizeToken(row.token || '');
    if (!token) continue;
    const levelValue = Number.parseFloat(String(row.level ?? ''));
    if (!Number.isFinite(levelValue)) continue;
    const level = Math.trunc(levelValue);

    const durationMin = Number.parseFloat(String(row.duration_min ?? '')) || 0;
    const outputToken = normalizeToken(row.output_token || token) || token;
    const outputAmount = Number.parseFloat(String(row.output_amount ?? '0').replace(/,/g, '')) || 0;

    const inputs: Record<string, number> = {};
    for (const idx of [1, 2]) {
      const tokenKey = `input_token_${idx}`;
      const amountKey = `input_amount_${idx}`;
      const inputToken = normalizeToken((row as Record<string, string>)[tokenKey] || '');
      if (!inputToken) continue;
      const rawQty = (row as Record<string, string>)[amountKey];
      if (rawQty === undefined || rawQty === null || rawQty === '') continue;
      const qty = Number.parseFloat(String(rawQty).replace(/,/g, '')) || 0;
      inputs[inputToken] = (inputs[inputToken] || 0) + qty;
    }

    const upgradeToken = normalizeToken(row.upgrade_token || '') || null;
    const upgradeAmountRaw = row.upgrade_amount;
    const upgradeAmount = upgradeAmountRaw ? Number.parseFloat(String(upgradeAmountRaw).replace(/,/g, '')) : null;

    factories[token] = factories[token] || {};
    factories[token][level] = {
      output_token: outputToken,
      output_amount: outputAmount,
      duration_min: durationMin,
      inputs,
      upgrade_token: upgradeToken,
      upgrade_amount: Number.isFinite(Number(upgradeAmount)) ? upgradeAmount : null,
    } satisfies FactoryLevelRow;
  }

  return factories;
}

export function getFactoryDisplayOrder(factories: FactoriesFromCsv): string[] {
  const order: string[] = FACTORY_DISPLAY_ORDER_BASE.filter((token) => token in factories);
  for (const token of Object.keys(factories).sort()) {
    if (!order.includes(token)) order.push(token);
  }
  return order;
}

export function getFactoryDisplayIndex(factories: FactoriesFromCsv): Record<string, number> {
  const order = getFactoryDisplayOrder(factories);
  return order.reduce((acc, token, idx) => {
    acc[token] = idx;
    return acc;
  }, {} as Record<string, number>);
}

export type FactoryResult = {
  token: string;
  level: number;
  target_level?: number | null;
  count: number;
  yield_pct: number;
  speed_factor: number;
  workers: number;
  duration_min: number;
  effective_duration: number;
  crafts_per_hour: number;
  out_token: string;
  out_amount: number;
  inputs: Record<string, number>;
  inputs_value_coin: Record<string, number>;
  cost_coin_per_craft: number;
  value_coin_per_craft: number;
  profit_coin_per_craft: number;
  profit_coin_per_hour: number;
  upgrade_single?: {
    token: string;
    amount_per_factory: number;
    coin_per_factory: number;
    coin_total: number;
  } | null;
  upgrade_chain: {
    token: string;
    amount_per_factory: number;
    coin_per_factory: number;
    coin_total: number;
  }[];
};

export function computeFactoryResultCsv(
  factories: FactoriesFromCsv,
  pricesCoin: PriceMap,
  token: string,
  level: number,
  targetLevel: number | null,
  count: number,
  yieldPct: number,
  speedFactor: number,
  workers: number,
  inputPricesCoin?: PriceMap,
): FactoryResult {
  if (!factories[token]) throw new Error(`No CSV data for factory token ${token}.`);
  if (!factories[token][level]) throw new Error(`No CSV data for ${token} level ${level}.`);

  const levels = factories[token];
  const data = levels[level];
  const outToken = data.output_token;
  const outAmount = data.output_amount;
  const durationMin = data.duration_min;
  const baseInputs = data.inputs || {};

  const yieldFactor = Math.max(yieldPct, 0.0001) / 100.0;
  const inputsAdj = Object.fromEntries(Object.entries(baseInputs).map(([t, q]) => [t, q / yieldFactor]));

  const multiUpgradeTokens: Record<string, number> = {};
  if (targetLevel && targetLevel > level) {
    for (let step = level + 1; step <= targetLevel; step += 1) {
      const rowStep = levels[step];
      if (!rowStep) continue;
      const stepTok = rowStep.upgrade_token;
      const stepAmt = rowStep.upgrade_amount || 0;
      if (stepTok && stepAmt > 0) {
        multiUpgradeTokens[stepTok] = (multiUpgradeTokens[stepTok] || 0) + stepAmt;
      }
    }
  }

  const nextRow = levels[level + 1];
  const upToken = nextRow ? nextRow.upgrade_token : data.upgrade_token;
  const upAmount = nextRow ? nextRow.upgrade_amount || 0 : data.upgrade_amount || 0;

  const workersClamped = Math.max(0, Math.min(workers, 4));
  const workerFactor = 1.0 + 0.5 * workersClamped;
  const combinedSpeed = Math.max(speedFactor, 0.01) * workerFactor;
  const effectiveDuration = combinedSpeed > 0 ? durationMin / combinedSpeed : durationMin;
  const craftsPerHour = effectiveDuration > 0 ? 60.0 / effectiveDuration : 0.0;

  const priceOut = (tok: string) => Number(pricesCoin[tok] || 0);
  const priceIn = (tok: string) => Number((inputPricesCoin ?? pricesCoin)[tok] || pricesCoin[tok] || 0);

  const inputsValueCoin = Object.fromEntries(
    Object.entries(inputsAdj).map(([t, q]) => [t, q * priceIn(t)]),
  );
  const costCoinPerCraft = Object.values(inputsValueCoin).reduce((acc, value) => acc + value, 0);
  const valueCoinPerCraft = outAmount * priceOut(outToken);
  const profitCoinPerCraft = valueCoinPerCraft - costCoinPerCraft;
  const profitCoinPerHour = profitCoinPerCraft * craftsPerHour * count;

  let upgradeSingle: FactoryResult['upgrade_single'] = null;
  if (upToken && upAmount && upAmount > 0) {
    const upCoinOne = upAmount * priceIn(upToken);
    const upCoinTotal = upCoinOne * count;
    upgradeSingle = {
      token: upToken,
      amount_per_factory: upAmount,
      coin_per_factory: upCoinOne,
      coin_total: upCoinTotal,
    };
  }

  const upgradeChain: FactoryResult['upgrade_chain'] = [];
  if (targetLevel && targetLevel > level && Object.keys(multiUpgradeTokens).length > 0) {
    for (const [tok, amt] of Object.entries(multiUpgradeTokens)) {
      const coinPerFactory = amt * priceIn(tok);
      upgradeChain.push({
        token: tok,
        amount_per_factory: amt,
        coin_per_factory: coinPerFactory,
        coin_total: coinPerFactory * count,
      });
    }
  }

  return {
    token,
    level,
    target_level: targetLevel,
    count,
    yield_pct: yieldPct,
    speed_factor: speedFactor,
    workers,
    duration_min: durationMin,
    effective_duration: effectiveDuration,
    crafts_per_hour: craftsPerHour,
    out_token: outToken,
    out_amount: outAmount,
    inputs: inputsAdj,
    inputs_value_coin: inputsValueCoin,
    cost_coin_per_craft: costCoinPerCraft,
    value_coin_per_craft: valueCoinPerCraft,
    profit_coin_per_craft: profitCoinPerCraft,
    profit_coin_per_hour: profitCoinPerHour,
    upgrade_single: upgradeSingle,
    upgrade_chain: upgradeChain,
  };
}

export function computeBestSetupsCsv(
  factories: FactoriesFromCsv,
  pricesCoin: PriceMap,
  speedFactor: number,
  workers: number,
  yieldPct: number,
  topN = 15,
): { results: { token: string; level: number; profit_coin_per_hour: number; profit_coin_per_craft: number }[]; combinedSpeed: number; workerFactor: number } {
  const results: { token: string; level: number; profit_coin_per_hour: number; profit_coin_per_craft: number }[] = [];
  const yieldFactor = Math.max(yieldPct, 0.0001) / 100.0;
  const workersClamped = Math.max(0, Math.min(workers, 4));
  const workerFactor = 1.0 + 0.5 * workersClamped;
  const combinedSpeed = Math.max(speedFactor, 0.01) * workerFactor;

  const price = (tok: string) => Number(pricesCoin[tok] || 0);

  for (const [factoryName, levels] of Object.entries(factories)) {
    const levelKeys = Object.keys(levels).map((value) => Number(value));
    if (!levelKeys.length) continue;
    const maxLevel = Math.max(...levelKeys);
    const data = levels[maxLevel];
    const outToken = data.output_token;
    const outAmount = data.output_amount;
    const durationMin = data.duration_min;
    const baseInputs = data.inputs || {};

    const effDuration = combinedSpeed > 0 ? durationMin / combinedSpeed : durationMin;
    const craftsPerHour = effDuration > 0 ? 60.0 / effDuration : 0.0;

    const inputsAdj = Object.fromEntries(Object.entries(baseInputs).map(([t, q]) => [t, q / yieldFactor]));
    const costCoin = Object.entries(inputsAdj).reduce((acc, [t, q]) => acc + q * price(t), 0);
    const valueCoin = outAmount * price(outToken);
    const profitCoinPerCraft = valueCoin - costCoin;
    const profitCoinPerHour = profitCoinPerCraft * craftsPerHour;

    results.push({
      token: factoryName,
      level: maxLevel,
      profit_coin_per_hour: profitCoinPerHour,
      profit_coin_per_craft: profitCoinPerCraft,
    });
  }

  results.sort((a, b) => b.profit_coin_per_hour - a.profit_coin_per_hour);
  return { results: results.slice(0, topN), combinedSpeed, workerFactor };
}
