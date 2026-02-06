import Papa from 'papaparse';
import type { FactoryCsvMap, FactoryCsvRow, FactoryResult, PriceBook } from './types';

export const CSV_FACTORY_DISPLAY_ORDER_BASE = [
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

export interface MyFactory {
  token: string;
  level: number;
  duration_hours: number;
  output_per_batch: number;
  inputs_per_batch: Array<[string, number]>;
}

export const MY_FACTORIES: MyFactory[] = [
  { token: 'MUD', level: 40, duration_hours: 1.4167, output_per_batch: 11300, inputs_per_batch: [['EARTH', 32300]] },
  { token: 'CLAY', level: 24, duration_hours: 1.219, output_per_batch: 1510, inputs_per_batch: [['MUD', 15100]] },
  { token: 'SAND', level: 27, duration_hours: 1.75, output_per_batch: 2560, inputs_per_batch: [['STONE', 38400]] },
  { token: 'COPPER', level: 28, duration_hours: 1.25, output_per_batch: 640, inputs_per_batch: [['EARTH', 32700]] },
  { token: 'SEAWATER', level: 25, duration_hours: 1.867, output_per_batch: 605, inputs_per_batch: [['WATER', 33200]] },
  { token: 'ALGAE', level: 13, duration_hours: 0.625, output_per_batch: 120, inputs_per_batch: [['SEAWATER', 4820]] },
  { token: 'CERAMICS', level: 11, duration_hours: 1.117, output_per_batch: 15, inputs_per_batch: [['CLAY', 1500]] },
  { token: 'OXYGEN', level: 17, duration_hours: 0.667, output_per_batch: 40, inputs_per_batch: [['ALGAE', 2400]] },
  { token: 'STONE', level: 39, duration_hours: 0.9, output_per_batch: 10700, inputs_per_batch: [['EARTH', 53500]] },
  { token: 'HEAT', level: 22, duration_hours: 0.5, output_per_batch: 157, inputs_per_batch: [['FIRE', 7850]] },
  { token: 'LAVA', level: 21, duration_hours: 1.35, output_per_batch: 210, inputs_per_batch: [['STONE', 2100], ['HEAT', 480]] },
  { token: 'GAS', level: 11, duration_hours: 1.117, output_per_batch: 15, inputs_per_batch: [['OXYGEN', 1450]] },
  { token: 'CEMENT', level: 21, duration_hours: 1.183, output_per_batch: 180, inputs_per_batch: [['STONE', 3320]] },
  { token: 'GLASS', level: 21, duration_hours: 1.0, output_per_batch: 190, inputs_per_batch: [['SAND', 3800]] },
  { token: 'STEAM', level: 13, duration_hours: 0.6, output_per_batch: 120, inputs_per_batch: [['WATER', 3610], ['HEAT', 415]] },
  { token: 'STEEL', level: 19, duration_hours: 1.833, output_per_batch: 190, inputs_per_batch: [['COPPER', 3770], ['HEAT', 800]] },
  { token: 'FUEL', level: 16, duration_hours: 1.65, output_per_batch: 132, inputs_per_batch: [['HEAT', 910], ['OIL', 1320]] },
  { token: 'ACID', level: 7, duration_hours: 0.6, output_per_batch: 5, inputs_per_batch: [['GAS', 580], ['SULFUR', 150]] },
  { token: 'SULFUR', level: 17, duration_hours: 1.0, output_per_batch: 40, inputs_per_batch: [['GAS', 840]] },
  { token: 'ENERGY', level: 8, duration_hours: 0.6, output_per_batch: 6, inputs_per_batch: [['FUEL', 372], ['STEAM', 252]] },
  { token: 'SCREWS', level: 15, duration_hours: 0.867, output_per_batch: 60, inputs_per_batch: [['STEEL', 1060]] },
  { token: 'OIL', level: 14, duration_hours: 1.5, output_per_batch: 52, inputs_per_batch: [['SEAWATER', 1730]] },
  { token: 'PLASTICS', level: 20, duration_hours: 1.1, output_per_batch: 175, inputs_per_batch: [['ACID', 315], ['OIL', 1370]] },
  { token: 'FIBERGLASS', level: 16, duration_hours: 0.867, output_per_batch: 60, inputs_per_batch: [['GLASS', 1120]] },
  { token: 'HYDROGEN', level: 7, duration_hours: 0.55, output_per_batch: 5, inputs_per_batch: [['STEAM', 180], ['ENERGY', 30]] },
  { token: 'DYNAMITE', level: 6, duration_hours: 0.6, output_per_batch: 4, inputs_per_batch: [['ACID', 88], ['SULFUR', 290], ['ENERGY', 44]] },
  { token: 'TAPE', level: 24, duration_hours: 0.475, output_per_batch: 12600, inputs_per_batch: [['PLASTICS', 12700]] },
  { token: 'PLUNGER', level: 19, duration_hours: 0.375, output_per_batch: 163, inputs_per_batch: [['TAPE', 8150]] },
  { token: 'SPOON', level: 23, duration_hours: 0.5, output_per_batch: 1150, inputs_per_batch: [['TAPE', 13800]] },
  { token: 'TOYHAMMER', level: 17, duration_hours: 1.117, output_per_batch: 331, inputs_per_batch: [['SPOON', 3980]] },
  { token: 'TARGET', level: 18, duration_hours: 1.15, output_per_batch: 159, inputs_per_batch: [['PLUNGER', 954]] },
  { token: 'NINJASTAR', level: 9, duration_hours: 0.5, output_per_batch: 12, inputs_per_batch: [['SPOON', 1380], ['TARGET', 96]] },
  { token: 'SWORD', level: 6, duration_hours: 0.49, output_per_batch: 5, inputs_per_batch: [['TARGET', 130], ['TOYHAMMER', 80]] },
  { token: 'MYSTICWEAPON', level: 3, duration_hours: 1.25, output_per_batch: 3, inputs_per_batch: [['SWORD', 12], ['NINJASTAR', 9]] },
];

export function profitPerHour(factory: MyFactory, prices: PriceBook, speedFactor = 1.0, workers = 0) {
  const workersClamped = Math.max(0, Math.min(workers, 4));
  const multiplier = Math.max(speedFactor, 0.01) * (1.0 + 0.5 * workersClamped);
  const effDurationHours = multiplier > 0 ? factory.duration_hours / multiplier : factory.duration_hours;
  if (effDurationHours <= 0) return 0.0;

  const craftsPerHour = 1.0 / effDurationHours;
  const outPerHour = factory.output_per_batch * craftsPerHour;
  const costIn = factory.inputs_per_batch.reduce((sum, [tok, amt]) => {
    const amtPerHour = amt * craftsPerHour;
    return sum + amtPerHour * (prices[tok] || 0.0);
  }, 0.0);
  const valOut = outPerHour * (prices[factory.token] || 0.0);
  return valOut - costIn;
}

function normalizeToken(symbol: string) {
  const token = (symbol || '').trim().toUpperCase();
  return token === 'WORMS' ? 'WORM' : token;
}

export function loadFactoriesFromCsv(csvText: string): FactoryCsvMap {
  const parsed = Papa.parse(csvText, { header: true, skipEmptyLines: true });
  const factories: FactoryCsvMap = {};
  if (!parsed.data || !Array.isArray(parsed.data)) return factories;

  for (const row of parsed.data as Record<string, string>[]) {
    if (!row) continue;
    const tokenRaw = normalizeToken(row.token || '');
    if (!tokenRaw) continue;

    const levelRaw = row.level;
    const level = levelRaw ? Math.floor(Number(levelRaw)) : NaN;
    if (!Number.isFinite(level)) continue;

    const durationMin = Number(String(row.duration_min || 0).replace(/,/g, '')) || 0;
    const outTokenRaw = normalizeToken(row.output_token || tokenRaw);
    const outputToken = outTokenRaw || tokenRaw;
    const outputAmount = Number(String(row.output_amount || 0).replace(/,/g, '')) || 0;

    const inputs: Record<string, number> = {};
    for (const idx of [1, 2]) {
      const tokenKey = `input_token_${idx}`;
      const amountKey = `input_amount_${idx}`;
      const token = normalizeToken(row[tokenKey] || '');
      if (!token) continue;
      const amountRaw = row[amountKey];
      if (amountRaw === undefined || amountRaw === '') continue;
      const qty = Number(String(amountRaw).replace(/,/g, '')) || 0;
      inputs[token] = (inputs[token] || 0) + qty;
    }

    const upgradeTokenRaw = normalizeToken(row.upgrade_token || '');
    const upgradeToken = upgradeTokenRaw || null;
    const upgradeAmountRaw = row.upgrade_amount;
    const upgradeAmount = upgradeAmountRaw !== undefined && upgradeAmountRaw !== ''
      ? Number(String(upgradeAmountRaw).replace(/,/g, ''))
      : null;

    const entry: FactoryCsvRow = {
      output_token: outputToken,
      output_amount: outputAmount,
      duration_min: durationMin,
      inputs,
      upgrade_token: upgradeToken,
      upgrade_amount: Number.isFinite(upgradeAmount || 0) ? upgradeAmount : null,
    };

    if (!factories[tokenRaw]) factories[tokenRaw] = {};
    factories[tokenRaw][level] = entry;
  }

  return factories;
}

export function buildFactoryDisplayOrder(factories: FactoryCsvMap) {
  const order = CSV_FACTORY_DISPLAY_ORDER_BASE.filter((tok) => tok in factories);
  for (const tok of Object.keys(factories).sort()) {
    if (!order.includes(tok)) order.push(tok);
  }
  return order;
}

export function computeFactoryResultCsv(
  factories: FactoryCsvMap,
  pricesCoin: PriceBook,
  token: string,
  level: number,
  targetLevel: number | null,
  count: number,
  yieldPct: number,
  speedFactor: number,
  workers: number,
  inputPricesCoin?: PriceBook | null,
): FactoryResult {
  if (!factories[token]) {
    throw new Error(`No CSV data for factory token ${token}.`);
  }
  if (!factories[token][level]) {
    throw new Error(`No CSV data for ${token} level ${level}.`);
  }

  const levelsDict = factories[token];
  const data = levelsDict[level];
  const outToken = data.output_token;
  const outAmount = data.output_amount;
  const durationMin = data.duration_min;
  const baseInputs = data.inputs || {};

  const yieldFactor = Math.max(yieldPct, 0.0001) / 100.0;
  const inputsAdj: Record<string, number> = {};
  for (const [tok, qty] of Object.entries(baseInputs)) {
    inputsAdj[tok] = qty / yieldFactor;
  }

  const multiUpgradeTokens: Record<string, number> = {};
  if (targetLevel && targetLevel > level) {
    for (let step = level + 1; step <= targetLevel; step += 1) {
      const stepRow = levelsDict[step];
      if (!stepRow) continue;
      const stepTok = stepRow.upgrade_token;
      const stepAmt = stepRow.upgrade_amount || 0;
      if (stepTok && stepAmt > 0) {
        multiUpgradeTokens[stepTok] = (multiUpgradeTokens[stepTok] || 0) + stepAmt;
      }
    }
  }

  const nextRow = levelsDict[level + 1];
  const upToken = nextRow ? nextRow.upgrade_token : data.upgrade_token;
  const upAmount = nextRow ? nextRow.upgrade_amount : data.upgrade_amount;

  const workersClamped = Math.max(0, Math.min(workers, 4));
  const workerFactor = 1.0 + 0.5 * workersClamped;
  const combinedSpeed = Math.max(speedFactor, 0.01) * workerFactor;
  const effectiveDuration = combinedSpeed > 0 ? durationMin / combinedSpeed : durationMin;
  const craftsPerHour = effectiveDuration > 0 ? 60.0 / effectiveDuration : 0.0;

  const priceOut = (tok: string) => Number(pricesCoin[tok] || 0);
  const priceIn = (tok: string) =>
    Number((inputPricesCoin || pricesCoin)[tok] || pricesCoin[tok] || 0);

  const inputsValueCoin: Record<string, number> = {};
  for (const [tok, qty] of Object.entries(inputsAdj)) {
    inputsValueCoin[tok] = qty * priceIn(tok);
  }
  const costCoinPerCraft = Object.values(inputsValueCoin).reduce((sum, val) => sum + val, 0);
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
  if (targetLevel && targetLevel > level && Object.keys(multiUpgradeTokens).length) {
    for (const [tok, amt] of Object.entries(multiUpgradeTokens)) {
      const coinPerFactory = amt * priceIn(tok);
      const coinAll = coinPerFactory * count;
      upgradeChain.push({
        token: tok,
        amount_per_factory: amt,
        coin_per_factory: coinPerFactory,
        coin_total: coinAll,
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
  factories: FactoryCsvMap,
  pricesCoin: PriceBook,
  speedFactor: number,
  workers: number,
  yieldPct: number,
  topN = 15,
) {
  const results: Array<{
    token: string;
    level: number;
    profit_coin_per_hour: number;
    profit_coin_per_craft: number;
  }> = [];
  const yieldFactor = Math.max(yieldPct, 0.0001) / 100.0;
  const workersClamped = Math.max(0, Math.min(workers, 4));
  const workerFactor = 1.0 + 0.5 * workersClamped;
  const combinedSpeed = Math.max(speedFactor, 0.01) * workerFactor;

  const price = (tok: string) => Number(pricesCoin[tok] || 0);

  for (const [facName, levels] of Object.entries(factories)) {
    const levelKeys = Object.keys(levels).map((lvl) => Number(lvl));
    if (!levelKeys.length) continue;
    const maxLevel = Math.max(...levelKeys);
    const data = levels[maxLevel];
    const outToken = data.output_token;
    const outAmount = data.output_amount;
    const durationMin = data.duration_min;
    const baseInputs = data.inputs || {};

    const effDur = combinedSpeed > 0 ? durationMin / combinedSpeed : durationMin;
    const craftsPerHour = effDur > 0 ? 60.0 / effDur : 0.0;

    const inputsAdj: Record<string, number> = {};
    for (const [tok, qty] of Object.entries(baseInputs)) {
      inputsAdj[tok] = qty / yieldFactor;
    }
    const costCoin = Object.entries(inputsAdj).reduce((sum, [tok, qty]) => {
      return sum + qty * price(tok);
    }, 0);
    const valueCoin = outAmount * price(outToken);
    const profitCoinPerCraft = valueCoin - costCoin;
    const profitCoinPerHour = profitCoinPerCraft * craftsPerHour;

    results.push({
      token: facName,
      level: maxLevel,
      profit_coin_per_hour: profitCoinPerHour,
      profit_coin_per_craft: profitCoinPerCraft,
    });
  }

  results.sort((a, b) => b.profit_coin_per_hour - a.profit_coin_per_hour);
  return {
    results: results.slice(0, topN),
    combined_speed: combinedSpeed,
    worker_factor: workerFactor,
  };
}
