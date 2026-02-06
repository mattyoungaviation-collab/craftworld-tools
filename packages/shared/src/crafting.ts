import type { CraftPlan, FactoryCsvMap, Modifiers, PriceBook, ChainReport } from './types';
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

export interface RecipeInput {
  symbol: string;
  qty: number;
}

export interface Recipe {
  outputSymbol: string;
  outputQty: number;
  inputs: RecipeInput[];
  craftSeconds: number;
  powerCost: number;
  level: number;
}

export const DEFAULT_MODIFIERS: Modifiers = {
  masteryLevelsBySymbol: {},
  workshopLevelsByFactoryOrTier: {},
  globalSpeedMultiplier: 1.0,
};

const safeFloat = (value: unknown, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

export function buildRecipeIndex(factories: FactoryCsvMap): { index: Record<string, Recipe>; warnings: string[] } {
  const warnings: string[] = [];
  const index: Record<string, Recipe> = {};

  for (const [token, levels] of Object.entries(factories)) {
    const levelKeys = Object.keys(levels).map((lvl) => Number(lvl));
    if (!levelKeys.length) continue;
    const lvl = Math.min(...levelKeys);
    const row = levels[lvl];
    const inputs = Object.entries(row.inputs || {}).map(([sym, qty]) => ({
      symbol: sym.toUpperCase(),
      qty: safeFloat(qty, 0),
    }));
    const requiredPower = safeFloat((row as { required_power?: number }).required_power, 0);
    const recipe: Recipe = {
      outputSymbol: (row.output_token || token).toUpperCase(),
      outputQty: Math.max(safeFloat(row.output_amount, 1.0), 1e-9),
      inputs,
      craftSeconds: Math.max(safeFloat(row.duration_min, 0) * 60, 0),
      powerCost: requiredPower > 0 ? requiredPower : Math.max(inputs.reduce((sum, i) => sum + i.qty, 0), 1),
      level: lvl,
    };
    index[recipe.outputSymbol] = recipe;
  }

  for (const outputSymbol of Object.keys(CANONICAL_GRAPH)) {
    if (!index[outputSymbol]) {
      warnings.push(`Missing recipe for canonical symbol ${outputSymbol}`);
    }
  }

  return { index, warnings };
}

export function getEffectiveRecipe(baseRecipe: Recipe, modifiers: Modifiers): Recipe {
  const masteryLevel = Math.max(0, Math.min(10, Math.trunc(modifiers.masteryLevelsBySymbol[baseRecipe.outputSymbol] || 0)));
  const masteryBonus = MASTERY_BONUSES[masteryLevel] ?? 1.0;

  const workshopLevel = Math.max(0, Math.min(10, Math.trunc(modifiers.workshopLevelsByFactoryOrTier[baseRecipe.outputSymbol] || 0)));
  const wsTable = WORKSHOP_MODIFIERS[baseRecipe.outputSymbol] || [0];
  const wsPct = workshopLevel < wsTable.length ? wsTable[workshopLevel] : 0;

  const speedMultiplier = Math.max(1e-9, Number(modifiers.globalSpeedMultiplier || 1.0) * (1.0 + wsPct / 100.0));
  const effInputs = baseRecipe.inputs.map((input) => ({
    symbol: input.symbol,
    qty: input.qty / Math.max(masteryBonus, 1e-9),
  }));

  return {
    outputSymbol: baseRecipe.outputSymbol,
    outputQty: baseRecipe.outputQty,
    inputs: effInputs,
    craftSeconds: baseRecipe.craftSeconds / speedMultiplier,
    powerCost: baseRecipe.powerCost,
    level: baseRecipe.level,
  };
}

const formatHms = (totalSeconds: number) => {
  const sec = Math.max(0, Math.trunc(totalSeconds));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

export function planCraft(
  factories: FactoryCsvMap,
  targetSymbol: string,
  targetAmount: number,
  prices: PriceBook,
  mode: 'market' | 'craft',
  modifiers: Modifiers = DEFAULT_MODIFIERS,
  baseCostModel?: PriceBook,
  availableBases?: string[],
  powerNow?: number | null,
  refillSeconds?: number | null,
): CraftPlan {
  const { index, warnings } = buildRecipeIndex(factories);
  const normalizedBaseCosts = {
    EARTH: 0.0,
    WATER: prices.WATER || 0.0,
    FIRE: prices.FIRE || 0.0,
    ...(baseCostModel || {}),
  };
  const availableBaseSet = new Set((availableBases || ['EARTH', 'WATER', 'FIRE']).map((b) => b.toUpperCase()));

  const stepsCount: Record<string, number> = {};
  const externalNeeds: Record<string, number> = {};
  const missingPrices = new Set<string>();
  const missingRecipes = new Set<string>();

  const unitCoinCostCache = new Map<string, number>();
  const unitCoinCost = (symbol: string): number => {
    const key = symbol.toUpperCase();
    if (unitCoinCostCache.has(key)) return unitCoinCostCache.get(key)!;

    let value = 0.0;
    const price = prices[key];
    if (mode === 'market') {
      if (price === undefined) missingPrices.add(key);
      value = Number(price || 0.0);
    } else if (BASE_SYMBOLS.has(key)) {
      if (availableBaseSet.has(key)) {
        value = Number(normalizedBaseCosts[key] ?? prices[key] ?? 0.0);
      } else {
        if (price === undefined && normalizedBaseCosts[key] === undefined) missingPrices.add(key);
        value = Number(price ?? normalizedBaseCosts[key] ?? 0.0);
      }
    } else {
      const recipe = index[key];
      if (!recipe) {
        missingRecipes.add(key);
        if (price === undefined) missingPrices.add(key);
        value = Number(price || 0.0);
      } else {
        const eff = getEffectiveRecipe(recipe, modifiers);
        value = eff.inputs.reduce((sum, input) => sum + input.qty * unitCoinCost(input.symbol), 0) / Math.max(eff.outputQty, 1e-9);
      }
    }

    unitCoinCostCache.set(key, value);
    return value;
  };

  const expand = (symbol: string, qty: number) => {
    const key = symbol.toUpperCase();
    if (qty <= 0) return;

    if (mode === 'market') {
      externalNeeds[key] = (externalNeeds[key] || 0) + qty;
      if (!(key in prices)) missingPrices.add(key);
      return;
    }

    if (BASE_SYMBOLS.has(key)) {
      externalNeeds[key] = (externalNeeds[key] || 0) + qty;
      if (!(key in prices) && !(key in normalizedBaseCosts)) missingPrices.add(key);
      return;
    }

    const recipe = index[key];
    if (!recipe) {
      missingRecipes.add(key);
      externalNeeds[key] = (externalNeeds[key] || 0) + qty;
      if (!(key in prices)) missingPrices.add(key);
      return;
    }

    const eff = getEffectiveRecipe(recipe, modifiers);
    const crafts = Math.ceil(qty / Math.max(eff.outputQty, 1e-9));
    stepsCount[key] = (stepsCount[key] || 0) + crafts;
    for (const input of eff.inputs) {
      expand(input.symbol, input.qty * crafts);
    }
  };

  expand(targetSymbol, Number(targetAmount));

  const steps: CraftPlan['steps'] = [];
  let totalPower = 0.0;
  let totalSeconds = 0.0;
  let totalCoinCost = 0.0;

  for (const symbol of Object.keys(stepsCount).sort()) {
    const recipe = index[symbol];
    const eff = getEffectiveRecipe(recipe, modifiers);
    const crafts = stepsCount[symbol];
    const inputCost = eff.inputs.reduce((sum, input) => sum + input.qty * unitCoinCost(input.symbol) * crafts, 0);
    const outputQty = eff.outputQty * crafts;
    const outputValue = outputQty * Number(prices[symbol] || 0.0);
    totalPower += eff.powerCost * crafts;
    totalSeconds += eff.craftSeconds * crafts;
    totalCoinCost += inputCost;

    steps.push({
      outputSymbol: symbol,
      times: crafts,
      inputs: eff.inputs.map((input) => ({
        symbol: input.symbol,
        qty: input.qty * crafts,
      })),
      powerCost: eff.powerCost * crafts,
      timeCost: eff.craftSeconds * crafts,
      coinCost: inputCost,
      coinValue: outputValue,
    });
  }

  let extCost = 0.0;
  for (const [sym, qty] of Object.entries(externalNeeds)) {
    extCost += qty * unitCoinCost(sym);
  }

  const targetPrice = Number(prices[targetSymbol.toUpperCase()] || 0.0);
  const coinValue = targetPrice * Number(targetAmount);
  const grossProfit = coinValue - (totalCoinCost + extCost);
  const profitPerPower = grossProfit / Math.max(totalPower, 1e-9);
  const profitPerHour = grossProfit / Math.max(totalSeconds / 3600.0, 1e-9);
  const roi = grossProfit / Math.max(totalCoinCost + extCost, 1e-9);

  let deficit = 0.0;
  let canAffordNow = true;
  let eta = '00:00:00';
  if (powerNow !== undefined && powerNow !== null) {
    deficit = Math.max(0.0, totalPower - Number(powerNow));
    canAffordNow = deficit <= 0;
    eta = canAffordNow ? '00:00:00' : formatHms(Number(refillSeconds || 0));
  }

  return {
    targetSymbol: targetSymbol.toUpperCase(),
    targetAmount,
    steps,
    totals: {
      power: totalPower,
      seconds: totalSeconds,
      coinCost: totalCoinCost + extCost,
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
  factories: FactoryCsvMap,
  prices: PriceBook,
  mode: 'market' | 'craft',
  objective: 'profit_per_power' | 'profit_per_hour' | 'total_profit',
  powerBudget: number | null,
  timeBudgetSeconds: number | null,
  targetAmount: number,
  modifiers: Modifiers = DEFAULT_MODIFIERS,
  baseCostModel?: PriceBook,
  availableBases?: string[],
) {
  const { index } = buildRecipeIndex(factories);
  const candidates = Object.keys(CANONICAL_GRAPH).filter((sym) => index[sym]).sort();
  const plans = candidates.map((symbol) =>
    planCraft(
      factories,
      symbol,
      targetAmount,
      prices,
      mode,
      modifiers,
      baseCostModel,
      availableBases,
      powerBudget,
      0,
    ),
  );

  const filtered = plans.filter((plan) => {
    const missing = plan.missing;
    if (missing.prices.length || missing.recipes.length) return false;
    if (Number(prices[plan.targetSymbol] || 0) <= 0) return false;
    if (powerBudget !== null && plan.totals.power > powerBudget) return false;
    if (timeBudgetSeconds !== null && plan.totals.seconds > timeBudgetSeconds) return false;
    return true;
  });

  const keyMap: Record<string, (plan: CraftPlan) => number> = {
    profit_per_power: (plan) => plan.totals.profitPerPower,
    profit_per_hour: (plan) => plan.totals.profitPerHour,
    total_profit: (plan) => plan.totals.grossProfit,
  };

  const sortKey = keyMap[objective] || keyMap.profit_per_power;
  return filtered.sort((a, b) => sortKey(b) - sortKey(a));
}

export function buildChainReport(
  factories: FactoryCsvMap,
  chainName: string,
  chainSymbols: string[],
  prices: PriceBook,
  modifiers: Modifiers = DEFAULT_MODIFIERS,
  startAmount = 1.0,
  inputPrices?: PriceBook,
  outputPrices?: PriceBook,
): ChainReport {
  const { index } = buildRecipeIndex(factories);
  const inputBook = inputPrices || prices;
  const outputBook = outputPrices || prices;

  if (chainSymbols.length < 2) {
    return { name: chainName, stages: [], error: 'Chain must contain at least two symbols.' };
  }

  let currentSymbol = chainSymbols[0].toUpperCase();
  let currentAmount = Math.max(Number(startAmount), 1e-9);
  let currentBookCost = currentAmount * Number(inputBook[currentSymbol] ?? prices[currentSymbol] ?? 0);

  const stages: ChainReport['stages'] = [];
  let totalSeconds = 0.0;
  let totalPower = 0.0;

  for (const nextSymbolRaw of chainSymbols.slice(1)) {
    const nextSymbol = nextSymbolRaw.toUpperCase();
    const recipe = index[nextSymbol];
    if (!recipe) {
      return { name: chainName, stages, error: `Missing recipe for ${nextSymbol}.` };
    }

    const eff = getEffectiveRecipe(recipe, modifiers);
    const prevInput = eff.inputs.find((input) => input.symbol === currentSymbol);
    if (!prevInput || prevInput.qty <= 0) {
      return {
        name: chainName,
        stages,
        error: `${nextSymbol} does not directly consume ${currentSymbol}.`,
      };
    }

    const crafts = currentAmount / prevInput.qty;
    const outputAmount = crafts * eff.outputQty;

    let otherInputsCost = 0.0;
    for (const input of eff.inputs) {
      if (input.symbol === currentSymbol) continue;
      otherInputsCost += input.qty * crafts * Number(inputBook[input.symbol] ?? prices[input.symbol] ?? 0);
    }

    const inputPrice = Number(inputBook[currentSymbol] ?? prices[currentSymbol] ?? 0);
    const stageInputCost = currentAmount * inputPrice + otherInputsCost;
    const outputPrice = Number(outputBook[nextSymbol] ?? prices[nextSymbol] ?? 0);
    const outputValue = outputAmount * outputPrice;
    const stageProfit = outputValue - stageInputCost;
    const stageRoi = stageInputCost > 0 ? stageProfit / stageInputCost : 0;

    currentBookCost += otherInputsCost;
    const cumulativeProfit = outputValue - currentBookCost;
    const cumulativeRoi = currentBookCost > 0 ? cumulativeProfit / currentBookCost : 0;

    const stageSeconds = crafts * eff.craftSeconds;
    const stagePower = crafts * eff.powerCost;
    totalSeconds += stageSeconds;
    totalPower += stagePower;

    stages.push({
      from: currentSymbol,
      to: nextSymbol,
      input_amount: currentAmount,
      input_price: inputPrice,
      input_cost: currentAmount * inputPrice,
      other_input_cost: otherInputsCost,
      total_stage_input_cost: stageInputCost,
      output_amount: outputAmount,
      output_price: outputPrice,
      output_value: outputValue,
      stage_profit: stageProfit,
      stage_roi: stageRoi,
      cumulative_cost: currentBookCost,
      cumulative_profit: cumulativeProfit,
      cumulative_roi: cumulativeRoi,
      crafts,
      seconds: stageSeconds,
      power: stagePower,
    });

    currentSymbol = nextSymbol;
    currentAmount = outputAmount;
  }

  const finalValue = currentAmount * Number(outputBook[currentSymbol] ?? prices[currentSymbol] ?? 0);
  const totalProfit = finalValue - currentBookCost;
  const totalRoi = currentBookCost > 0 ? totalProfit / currentBookCost : 0;

  return {
    name: chainName,
    symbols: chainSymbols.map((s) => s.toUpperCase()),
    start_symbol: chainSymbols[0].toUpperCase(),
    start_amount: startAmount,
    end_symbol: currentSymbol,
    end_amount: currentAmount,
    total_cost: currentBookCost,
    total_value: finalValue,
    total_profit: totalProfit,
    total_roi: totalRoi,
    total_seconds: totalSeconds,
    total_power: totalPower,
    stages,
    error: null,
  };
}
