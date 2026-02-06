import type { PriceMap, ChainReport } from './types';
import { MASTERY_BONUSES, WORKSHOP_MODIFIERS } from './factories';

export const BASE_SYMBOLS = new Set(['EARTH', 'WATER', 'FIRE', 'COIN']);

export const CRAFTING_CHAINS: Record<string, string[]> = {
  'EARTH ➜ SCREWS': ['EARTH', 'MUD', 'CLAY', 'SAND', 'COPPER', 'STEEL', 'SCREWS'],
  'WATER ➜ OIL': ['WATER', 'SEAWATER', 'ALGAE', 'OXYGEN', 'GAS', 'FUEL', 'OIL'],
  'FIRE ➜ LAVA': ['FIRE', 'HEAT', 'LAVA'],
};

export const CANONICAL_GRAPH: Record<string, string[]> = {
  MUD: ['EARTH'],
  CLAY: ['MUD'],
  SAND: ['CLAY'],
  COPPER: ['SAND'],
  STEEL: ['COPPER'],
  SCREWS: ['STEEL'],
  SEAWATER: ['WATER'],
  ALGAE: ['SEAWATER'],
  OXYGEN: ['ALGAE'],
  GAS: ['OXYGEN'],
  FUEL: ['GAS'],
  OIL: ['FUEL'],
  HEAT: ['FIRE'],
  LAVA: ['HEAT'],
  CERAMICS: ['CLAY', 'SEAWATER'],
  STONE: ['COPPER', 'ALGAE'],
  CEMENT: ['CERAMICS', 'STONE'],
  ACID: ['SCREWS', 'FUEL'],
  PLASTICS: ['CEMENT', 'ACID'],
  GLASS: ['SAND', 'HEAT'],
  SULFUR: ['GLASS', 'LAVA'],
  FIBERGLASS: ['GLASS', 'SULFUR'],
  DYNAMITE: ['PLASTICS', 'FIBERGLASS'],
  STEAM: ['OXYGEN', 'LAVA'],
  ENERGY: ['OIL', 'HEAT'],
  HYDROGEN: ['STEAM', 'ENERGY'],
};

export type RecipeInput = { symbol: string; qty: number };
export type Recipe = {
  outputSymbol: string;
  outputQty: number;
  inputs: RecipeInput[];
  craftSeconds: number;
  powerCost: number;
  level: number;
};

export type Modifiers = {
  masteryLevelsBySymbol: Record<string, number>;
  workshopLevelsByFactoryOrTier: Record<string, number>;
  globalSpeedMultiplier: number;
};

export const DEFAULT_MODIFIERS: Modifiers = {
  masteryLevelsBySymbol: {},
  workshopLevelsByFactoryOrTier: {},
  globalSpeedMultiplier: 1.0,
};

export function safeFloat(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function buildRecipeIndex(factories: Record<string, Record<number, { output_token: string; output_amount: number; duration_min: number; inputs: Record<string, number>; required_power?: number }>>): {
  index: Record<string, Recipe>;
  warnings: string[];
} {
  const warnings: string[] = [];
  const index: Record<string, Recipe> = {};

  for (const [token, levels] of Object.entries(factories)) {
    const levelKeys = Object.keys(levels).map((key) => Number(key));
    if (!levelKeys.length) continue;
    const lvl = Math.min(...levelKeys);
    const row = levels[lvl];
    const inputs = Object.entries(row.inputs || {}).map(([sym, qty]) => ({ symbol: sym.toUpperCase(), qty: safeFloat(qty, 0) }));
    const requiredPower = safeFloat((row as { required_power?: number }).required_power, 0);
    const recipe: Recipe = {
      outputSymbol: (row.output_token || token).toUpperCase(),
      outputQty: Math.max(safeFloat(row.output_amount, 1), 1e-9),
      inputs,
      craftSeconds: Math.max(safeFloat(row.duration_min, 0) * 60, 0),
      powerCost: requiredPower > 0 ? requiredPower : Math.max(inputs.reduce((acc, item) => acc + item.qty, 0), 1),
      level: lvl,
    };
    index[recipe.outputSymbol] = recipe;
  }

  for (const symbol of Object.keys(CANONICAL_GRAPH)) {
    if (!index[symbol]) warnings.push(`Missing recipe for canonical symbol ${symbol}`);
  }

  return { index, warnings };
}

export function getEffectiveRecipe(baseRecipe: Recipe, modifiers: Modifiers): Recipe {
  const masteryLevel = Math.max(0, Math.min(10, Number(modifiers.masteryLevelsBySymbol[baseRecipe.outputSymbol] || 0)));
  const masteryBonus = Number(MASTERY_BONUSES[masteryLevel] || 1.0);
  const workshopLevel = Math.max(0, Math.min(10, Number(modifiers.workshopLevelsByFactoryOrTier[baseRecipe.outputSymbol] || 0)));
  const wsTable = WORKSHOP_MODIFIERS[baseRecipe.outputSymbol] || [0];
  const wsPct = workshopLevel < wsTable.length ? Number(wsTable[workshopLevel] || 0) : 0;

  const speedMultiplier = Math.max(1e-9, Number(modifiers.globalSpeedMultiplier || 1) * (1 + wsPct / 100));
  const effInputs = baseRecipe.inputs.map((input) => ({ ...input, qty: input.qty / Math.max(masteryBonus, 1e-9) }));

  return {
    outputSymbol: baseRecipe.outputSymbol,
    outputQty: baseRecipe.outputQty,
    inputs: effInputs,
    craftSeconds: baseRecipe.craftSeconds / speedMultiplier,
    powerCost: baseRecipe.powerCost,
    level: baseRecipe.level,
  };
}

function formatHms(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function planCraft(
  factories: Record<string, Record<number, { output_token: string; output_amount: number; duration_min: number; inputs: Record<string, number>; required_power?: number }>>,
  targetSymbol: string,
  targetAmount: number,
  prices: PriceMap,
  mode: 'market' | 'craft',
  modifiers: Modifiers = DEFAULT_MODIFIERS,
  baseCostModel: PriceMap = {},
  availableBases: string[] = ['EARTH', 'WATER', 'FIRE'],
  powerNow?: number,
  refillSeconds?: number,
): Record<string, unknown> {
  const { index, warnings } = buildRecipeIndex(factories);
  const baseCost = { EARTH: 0, WATER: prices.WATER || 0, FIRE: prices.FIRE || 0, ...baseCostModel };
  const availableBaseSet = new Set(availableBases.map((b) => b.toUpperCase()));

  const stepsCount: Record<string, number> = {};
  const externalNeeds: Record<string, number> = {};
  const missingPrices = new Set<string>();
  const missingRecipes = new Set<string>();

  const unitCoinCost = (symbol: string): number => {
    const s = symbol.toUpperCase();
    const price = prices[s];
    if (mode === 'market') {
      if (price === undefined) {
        missingPrices.add(s);
        return 0;
      }
      return Number(price);
    }

    if (BASE_SYMBOLS.has(s)) {
      if (availableBaseSet.has(s)) return Number(baseCost[s] ?? prices[s] ?? 0);
      if (price === undefined) {
        missingPrices.add(s);
        return 0;
      }
      return Number(price);
    }

    const recipe = index[s];
    if (!recipe) {
      missingRecipes.add(s);
      if (price === undefined) {
        missingPrices.add(s);
        return 0;
      }
      return Number(price);
    }

    const eff = getEffectiveRecipe(recipe, modifiers);
    const totalInCost = eff.inputs.reduce((acc, input) => acc + input.qty * unitCoinCost(input.symbol), 0);
    return totalInCost / Math.max(eff.outputQty, 1e-9);
  };

  const expand = (symbol: string, qty: number): void => {
    const s = symbol.toUpperCase();
    if (qty <= 0) return;

    if (mode === 'market') {
      externalNeeds[s] = (externalNeeds[s] || 0) + qty;
      if (!prices[s]) missingPrices.add(s);
      return;
    }

    if (BASE_SYMBOLS.has(s)) {
      externalNeeds[s] = (externalNeeds[s] || 0) + qty;
      if (!prices[s] && !baseCost[s]) missingPrices.add(s);
      return;
    }

    const recipe = index[s];
    if (!recipe) {
      missingRecipes.add(s);
      externalNeeds[s] = (externalNeeds[s] || 0) + qty;
      if (!prices[s]) missingPrices.add(s);
      return;
    }

    const eff = getEffectiveRecipe(recipe, modifiers);
    const crafts = Math.ceil(qty / Math.max(eff.outputQty, 1e-9));
    stepsCount[s] = (stepsCount[s] || 0) + crafts;
    for (const input of eff.inputs) {
      expand(input.symbol, input.qty * crafts);
    }
  };

  expand(targetSymbol, Number(targetAmount));

  const steps: Record<string, unknown>[] = [];
  let totalPower = 0;
  let totalSeconds = 0;
  let totalCoinCost = 0;

  for (const [symbol, crafts] of Object.entries(stepsCount).sort()) {
    const recipe = index[symbol];
    const eff = getEffectiveRecipe(recipe, modifiers);
    const inputCost = eff.inputs.reduce((acc, input) => acc + input.qty * unitCoinCost(input.symbol) * crafts, 0);
    const outputQty = eff.outputQty * crafts;
    const outputValue = outputQty * Number(prices[symbol] || 0);
    totalPower += eff.powerCost * crafts;
    totalSeconds += eff.craftSeconds * crafts;
    totalCoinCost += inputCost;
    steps.push({
      outputSymbol: symbol,
      times: crafts,
      inputs: eff.inputs.map((input) => ({ symbol: input.symbol, qty: input.qty * crafts })),
      powerCost: eff.powerCost * crafts,
      timeCost: eff.craftSeconds * crafts,
      coinCost: inputCost,
      coinValue: outputValue,
    });
  }

  let externalCost = 0;
  for (const [sym, qty] of Object.entries(externalNeeds)) {
    externalCost += qty * unitCoinCost(sym);
  }

  const targetPrice = Number(prices[targetSymbol.toUpperCase()] || 0);
  const coinValue = targetPrice * Number(targetAmount);
  const grossProfit = coinValue - (totalCoinCost + externalCost);
  const profitPerPower = grossProfit / Math.max(totalPower, 1e-9);
  const profitPerHour = grossProfit / Math.max(totalSeconds / 3600, 1e-9);
  const roi = grossProfit / Math.max(totalCoinCost + externalCost, 1e-9);

  let deficit = 0;
  let canAffordNow = true;
  let eta = '00:00:00';
  if (powerNow !== undefined) {
    deficit = Math.max(0, totalPower - Number(powerNow));
    canAffordNow = deficit <= 0;
    eta = canAffordNow ? '00:00:00' : formatHms(Number(refillSeconds || 0));
  }

  return {
    targetSymbol: targetSymbol.toUpperCase(),
    targetAmount: Number(targetAmount),
    steps,
    totals: {
      power: totalPower,
      seconds: totalSeconds,
      coinCost: totalCoinCost + externalCost,
      coinValue,
      grossProfit,
      profitPerPower,
      profitPerHour,
      ROI: roi,
    },
    missing: {
      prices: Array.from(missingPrices).sort(),
      recipes: Array.from(new Set([...warnings, ...missingRecipes])).sort(),
      modifiers: [],
    },
    constraints: {
      powerNow,
      canAffordNow,
      powerDeficit: deficit,
      etaToAffordHMS: eta,
    },
    externalNeeds,
  };
}

export function rankOpportunities(
  factories: Record<string, Record<number, { output_token: string; output_amount: number; duration_min: number; inputs: Record<string, number>; required_power?: number }>>,
  prices: PriceMap,
  mode: 'market' | 'craft',
  objective: 'profit_per_power' | 'profit_per_hour' | 'total_profit',
  powerBudget?: number,
  timeBudgetSeconds?: number,
  targetAmount = 1,
  modifiers: Modifiers = DEFAULT_MODIFIERS,
  baseCostModel: PriceMap = {},
  availableBases: string[] = ['EARTH', 'WATER', 'FIRE'],
): Record<string, unknown>[] {
  const { index } = buildRecipeIndex(factories);
  const candidates = Array.from(new Set(Object.keys(CANONICAL_GRAPH).filter((key) => key in index)));
  const plans = [] as Record<string, unknown>[];

  for (const symbol of candidates.sort()) {
    const plan = planCraft(factories, symbol, targetAmount, prices, mode, modifiers, baseCostModel, availableBases, powerBudget, 0);
    const totals = (plan as { totals: { power: number; seconds: number; grossProfit: number; profitPerPower: number; profitPerHour: number } }).totals;
    const missing = plan.missing as { prices?: string[]; recipes?: string[] };
    if ((missing?.prices?.length || 0) > 0 || (missing?.recipes?.length || 0) > 0) continue;
    if (Number(prices[symbol] || 0) <= 0) continue;
    if (powerBudget !== undefined && totals.power > powerBudget) continue;
    if (timeBudgetSeconds !== undefined && totals.seconds > timeBudgetSeconds) continue;
    plans.push(plan);
  }

  const sortKey = {
    profit_per_power: (p: Record<string, unknown>) => (p.totals as { profitPerPower: number }).profitPerPower,
    profit_per_hour: (p: Record<string, unknown>) => (p.totals as { profitPerHour: number }).profitPerHour,
    total_profit: (p: Record<string, unknown>) => (p.totals as { grossProfit: number }).grossProfit,
  }[objective] ?? ((p: Record<string, unknown>) => (p.totals as { profitPerPower: number }).profitPerPower);

  return plans.sort((a, b) => sortKey(b) - sortKey(a));
}

export function buildChainReport(
  factories: Record<string, Record<number, { output_token: string; output_amount: number; duration_min: number; inputs: Record<string, number>; required_power?: number }>>,
  chainName: string,
  chainSymbols: string[],
  prices: PriceMap,
  modifiers: Modifiers = DEFAULT_MODIFIERS,
  startAmount = 1.0,
  inputPrices: PriceMap = prices,
  outputPrices: PriceMap = prices,
): ChainReport {
  const { index } = buildRecipeIndex(factories);
  if (chainSymbols.length < 2) {
    return { name: chainName, stages: [], total_input_cost: 0, total_output_value: 0, total_profit: 0, total_roi: 0, total_power: 0, total_seconds: 0, error: 'Chain must contain at least two symbols.' };
  }

  let currentSymbol = chainSymbols[0].toUpperCase();
  let currentAmount = Math.max(Number(startAmount), 1e-9);
  let currentBookCost = currentAmount * Number(inputPrices[currentSymbol] ?? prices[currentSymbol] ?? 0);

  const stages = [] as ChainReport['stages'];
  let totalSeconds = 0;
  let totalPower = 0;

  for (const nextSymbolRaw of chainSymbols.slice(1)) {
    const nextSymbol = nextSymbolRaw.toUpperCase();
    const recipe = index[nextSymbol];
    if (!recipe) {
      return { name: chainName, stages, total_input_cost: 0, total_output_value: 0, total_profit: 0, total_roi: 0, total_power: 0, total_seconds: 0, error: `Missing recipe for ${nextSymbol}.` };
    }

    const eff = getEffectiveRecipe(recipe, modifiers);
    const prevInput = eff.inputs.find((input) => input.symbol === currentSymbol);
    if (!prevInput || prevInput.qty <= 0) {
      return { name: chainName, stages, total_input_cost: 0, total_output_value: 0, total_profit: 0, total_roi: 0, total_power: 0, total_seconds: 0, error: `${nextSymbol} does not directly consume ${currentSymbol}.` };
    }

    const crafts = currentAmount / prevInput.qty;
    const outputAmount = crafts * eff.outputQty;

    let otherInputsCost = 0;
    for (const input of eff.inputs) {
      if (input.symbol === currentSymbol) continue;
      otherInputsCost += input.qty * crafts * Number(inputPrices[input.symbol] ?? prices[input.symbol] ?? 0);
    }

    const inputPrice = Number(inputPrices[currentSymbol] ?? prices[currentSymbol] ?? 0);
    const stageInputCost = currentAmount * inputPrice + otherInputsCost;
    const outputPrice = Number(outputPrices[nextSymbol] ?? prices[nextSymbol] ?? 0);
    const stageOutputValue = outputAmount * outputPrice;
    const stageProfit = stageOutputValue - stageInputCost;
    const stageRoi = stageProfit / Math.max(stageInputCost, 1e-9);

    totalSeconds += eff.craftSeconds * crafts;
    totalPower += eff.powerCost * crafts;

    stages.push({
      inputSymbol: currentSymbol,
      inputAmount: currentAmount,
      outputSymbol: nextSymbol,
      outputAmount,
      inputCost: stageInputCost,
      outputValue: stageOutputValue,
      profit: stageProfit,
      roi: stageRoi,
      powerCost: eff.powerCost * crafts,
      craftSeconds: eff.craftSeconds * crafts,
    });

    currentSymbol = nextSymbol;
    currentAmount = outputAmount;
    currentBookCost = stageInputCost;
  }

  const totalInputCost = currentBookCost;
  const totalOutputValue = currentAmount * Number(outputPrices[currentSymbol] ?? prices[currentSymbol] ?? 0);
  const totalProfit = totalOutputValue - totalInputCost;
  const totalRoi = totalProfit / Math.max(totalInputCost, 1e-9);

  return {
    name: chainName,
    stages,
    total_input_cost: totalInputCost,
    total_output_value: totalOutputValue,
    total_profit: totalProfit,
    total_roi: totalRoi,
    total_power: totalPower,
    total_seconds: totalSeconds,
  };
}
