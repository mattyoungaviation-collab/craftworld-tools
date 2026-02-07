import config from './generated/config.json' assert { type: 'json' };
import { BASE_SYMBOLS, CANONICAL_GRAPH, MASTERY_BONUSES, WORKSHOP_MODIFIERS } from './constants.js';
import type { CraftPlan, Modifiers, Recipe, RecipeInput } from './types.js';

const DEFAULT_MODIFIERS: Modifiers = {
  masteryLevelsBySymbol: {},
  workshopLevelsByFactoryOrTier: {},
  globalSpeedMultiplier: 1.0
};

const safeFloat = (value: unknown, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

export const buildRecipeIndex = () => {
  const index = new Map<string, Recipe>();
  const warnings: string[] = [];

  for (const row of config.factories) {
    if (!row) continue;
    const outputSymbol = row.outputToken.toUpperCase();
    const inputs: RecipeInput[] = (row.inputs ?? []).map((input) => ({
      symbol: input.token.toUpperCase(),
      qty: safeFloat(input.amount, 0)
    }));

    const recipe: Recipe = {
      outputSymbol,
      outputQty: Math.max(safeFloat(row.outputAmount, 1), 1e-9),
      inputs,
      craftSeconds: Math.max(safeFloat(row.durationMin, 0) * 60, 0),
      powerCost: Math.max(inputs.reduce((sum, item) => sum + item.qty, 0), 1),
      level: safeFloat(row.level, 0)
    };

    const existing = index.get(outputSymbol);
    if (!existing || recipe.level < existing.level) {
      index.set(outputSymbol, recipe);
    }
  }

  for (const symbol of Object.keys(CANONICAL_GRAPH)) {
    if (!index.has(symbol)) warnings.push(`Missing recipe for canonical symbol ${symbol}`);
  }

  return { index, warnings };
};

export const getEffectiveRecipe = (baseRecipe: Recipe, modifiers: Modifiers) => {
  const masteryLevel = Math.max(0, Math.min(10, modifiers.masteryLevelsBySymbol[baseRecipe.outputSymbol] || 0));
  const masteryBonus = MASTERY_BONUSES[masteryLevel] ?? 1.0;

  const workshopLevel = Math.max(
    0,
    Math.min(10, modifiers.workshopLevelsByFactoryOrTier[baseRecipe.outputSymbol] || 0)
  );
  const wsTable = WORKSHOP_MODIFIERS[baseRecipe.outputSymbol] ?? [0];
  const wsPct = wsTable[workshopLevel] ?? 0;

  const speedMultiplier = Math.max(1e-9, (modifiers.globalSpeedMultiplier || 1.0) * (1 + wsPct / 100));
  const effInputs = baseRecipe.inputs.map((input) => ({
    symbol: input.symbol,
    qty: input.qty / Math.max(masteryBonus, 1e-9)
  }));

  return {
    ...baseRecipe,
    inputs: effInputs,
    craftSeconds: baseRecipe.craftSeconds / speedMultiplier
  };
};

const formatHms = (totalSeconds: number) => {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

export const planCraft = (
  targetSymbol: string,
  targetAmount: number,
  prices: Record<string, number>,
  mode: 'craft' | 'market',
  modifiers: Modifiers = DEFAULT_MODIFIERS,
  baseCostModel: Record<string, number> = {},
  availableBases: string[] = ['EARTH', 'WATER', 'FIRE'],
  powerNow?: number,
  refillSeconds?: number
): CraftPlan => {
  const { index, warnings } = buildRecipeIndex();
  const baseModel = {
    EARTH: 0.0,
    WATER: prices.WATER ?? 0.0,
    FIRE: prices.FIRE ?? 0.0,
    ...baseCostModel
  };
  const availableBaseSet = new Set(availableBases.map((base) => base.toUpperCase()));

  const stepsCount = new Map<string, number>();
  const externalNeeds: Record<string, number> = {};
  const missingPrices = new Set<string>();
  const missingRecipes = new Set<string>();

  const unitCoinCost = (symbol: string): number => {
    const sym = symbol.toUpperCase();
    const price = prices[sym];
    if (mode === 'market') {
      if (price === undefined) missingPrices.add(sym);
      return price ?? 0;
    }

    if (BASE_SYMBOLS.has(sym)) {
      if (availableBaseSet.has(sym)) return baseModel[sym] ?? prices[sym] ?? 0;
      if (price === undefined && baseModel[sym] === undefined) missingPrices.add(sym);
      return price ?? baseModel[sym] ?? 0;
    }

    const recipe = index.get(sym);
    if (!recipe) {
      missingRecipes.add(sym);
      if (price === undefined) missingPrices.add(sym);
      return price ?? 0;
    }

    const eff = getEffectiveRecipe(recipe, modifiers);
    const totalInCost = eff.inputs.reduce((sum, input) => sum + input.qty * unitCoinCost(input.symbol), 0);
    return totalInCost / Math.max(eff.outputQty, 1e-9);
  };

  const expand = (symbol: string, qty: number) => {
    const sym = symbol.toUpperCase();
    if (qty <= 0) return;

    if (mode === 'market') {
      externalNeeds[sym] = (externalNeeds[sym] || 0) + qty;
      if (prices[sym] === undefined) missingPrices.add(sym);
      return;
    }

    if (BASE_SYMBOLS.has(sym)) {
      externalNeeds[sym] = (externalNeeds[sym] || 0) + qty;
      if (!availableBaseSet.has(sym) && prices[sym] === undefined && baseModel[sym] === undefined) {
        missingPrices.add(sym);
      }
      return;
    }

    const recipe = index.get(sym);
    if (!recipe) {
      missingRecipes.add(sym);
      externalNeeds[sym] = (externalNeeds[sym] || 0) + qty;
      if (prices[sym] === undefined) missingPrices.add(sym);
      return;
    }

    const eff = getEffectiveRecipe(recipe, modifiers);
    const crafts = Math.ceil(qty / Math.max(eff.outputQty, 1e-9));
    stepsCount.set(sym, (stepsCount.get(sym) || 0) + crafts);
    for (const input of eff.inputs) {
      expand(input.symbol, input.qty * crafts);
    }
  };

  expand(targetSymbol, targetAmount);

  const steps: CraftPlan['steps'] = [];
  let totalPower = 0;
  let totalSeconds = 0;
  let totalCoinCost = 0;

  for (const symbol of Array.from(stepsCount.keys()).sort()) {
    const crafts = stepsCount.get(symbol) ?? 0;
    const recipe = index.get(symbol);
    if (!recipe) continue;
    const eff = getEffectiveRecipe(recipe, modifiers);
    const inputCost = eff.inputs.reduce(
      (sum, input) => sum + input.qty * unitCoinCost(input.symbol) * crafts,
      0
    );
    const outputQty = eff.outputQty * crafts;
    const outputValue = outputQty * (prices[symbol] ?? 0);
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
      coinValue: outputValue
    });
  }

  let extCost = 0;
  for (const [sym, qty] of Object.entries(externalNeeds)) {
    extCost += qty * unitCoinCost(sym);
  }

  const targetPrice = prices[targetSymbol.toUpperCase()] ?? 0;
  const coinValue = targetPrice * targetAmount;
  const grossProfit = coinValue - (totalCoinCost + extCost);
  const profitPerPower = grossProfit / Math.max(totalPower, 1e-9);
  const profitPerHour = grossProfit / Math.max(totalSeconds / 3600, 1e-9);
  const roi = grossProfit / Math.max(totalCoinCost + extCost, 1e-9);

  let deficit = 0;
  let canAffordNow = true;
  let eta = '00:00:00';
  if (powerNow !== undefined) {
    deficit = Math.max(0, totalPower - powerNow);
    canAffordNow = deficit <= 0;
    eta = canAffordNow ? '00:00:00' : formatHms(refillSeconds ?? 0);
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
      ROI: roi
    },
    missing: {
      prices: Array.from(missingPrices).sort(),
      recipes: Array.from(new Set([...warnings, ...missingRecipes])).sort(),
      modifiers: []
    },
    constraints: {
      powerNow,
      canAffordNow,
      powerDeficit: deficit,
      etaToAffordHMS: eta
    },
    externalNeeds
  };
};

export const rankOpportunities = (
  prices: Record<string, number>,
  mode: 'craft' | 'market',
  objective: 'profit_per_power' | 'profit_per_hour' | 'total_profit',
  powerBudget?: number,
  timeBudgetSeconds?: number,
  targetAmount = 1,
  modifiers: Modifiers = DEFAULT_MODIFIERS,
  baseCostModel?: Record<string, number>,
  availableBases?: string[]
) => {
  const { index } = buildRecipeIndex();
  const candidates = Object.keys(CANONICAL_GRAPH).filter((symbol) => index.has(symbol));

  const plans = candidates
    .map((symbol) =>
      planCraft(symbol, targetAmount, prices, mode, modifiers, baseCostModel, availableBases, powerBudget, 0)
    )
    .filter((plan) => {
      const missing = plan.missing;
      if (missing.prices.length || missing.recipes.length) return false;
      if ((prices[plan.targetSymbol] ?? 0) <= 0) return false;
      if (powerBudget !== undefined && plan.totals.power > powerBudget) return false;
      if (timeBudgetSeconds !== undefined && plan.totals.seconds > timeBudgetSeconds) return false;
      return true;
    });

  const sortKey = {
    profit_per_power: (plan: CraftPlan) => plan.totals.profitPerPower,
    profit_per_hour: (plan: CraftPlan) => plan.totals.profitPerHour,
    total_profit: (plan: CraftPlan) => plan.totals.grossProfit
  }[objective];

  return plans.sort((a, b) => sortKey(b) - sortKey(a));
};

export const buildChainReport = (
  name: string,
  chainSymbols: string[],
  prices: Record<string, number>,
  modifiers: Modifiers = DEFAULT_MODIFIERS,
  startAmount = 1,
  inputPrices: Record<string, number> = prices,
  outputPrices: Record<string, number> = prices
) => {
  const { index } = buildRecipeIndex();

  if (chainSymbols.length < 2) {
    return { name, stages: [], error: 'Chain must contain at least two symbols.' };
  }

  let currentSymbol = chainSymbols[0].toUpperCase();
  let currentAmount = Math.max(startAmount, 1e-9);
  let currentBookCost = currentAmount * (inputPrices[currentSymbol] ?? prices[currentSymbol] ?? 0);

  const stages: Array<Record<string, number | string>> = [];
  let totalSeconds = 0;
  let totalPower = 0;

  for (const nextSymbolRaw of chainSymbols.slice(1)) {
    const nextSymbol = nextSymbolRaw.toUpperCase();
    const recipe = index.get(nextSymbol);
    if (!recipe) {
      return { name, stages, error: `Missing recipe for ${nextSymbol}.` };
    }

    const eff = getEffectiveRecipe(recipe, modifiers);
    const prevInput = eff.inputs.find((input) => input.symbol === currentSymbol);
    if (!prevInput || prevInput.qty <= 0) {
      return { name, stages, error: `${nextSymbol} does not directly consume ${currentSymbol}.` };
    }

    const crafts = currentAmount / prevInput.qty;
    const outputAmount = crafts * eff.outputQty;

    let otherInputsCost = 0;
    for (const input of eff.inputs) {
      if (input.symbol === currentSymbol) continue;
      otherInputsCost += input.qty * crafts * (inputPrices[input.symbol] ?? prices[input.symbol] ?? 0);
    }

    const inputPrice = inputPrices[currentSymbol] ?? prices[currentSymbol] ?? 0;
    const stageInputCost = currentAmount * inputPrice + otherInputsCost;
    const outputPrice = outputPrices[nextSymbol] ?? prices[nextSymbol] ?? 0;
    const outputValue = outputAmount * outputPrice;

    totalSeconds += eff.craftSeconds * crafts;
    totalPower += eff.powerCost * crafts;

    stages.push({
      inputSymbol: currentSymbol,
      outputSymbol: nextSymbol,
      inputAmount: currentAmount,
      outputAmount,
      craftCount: crafts,
      inputCost: stageInputCost,
      outputValue,
      cumulativeCost: currentBookCost + stageInputCost,
      cumulativeValue: outputValue,
      craftSeconds: eff.craftSeconds * crafts,
      powerCost: eff.powerCost * crafts
    });

    currentSymbol = nextSymbol;
    currentAmount = outputAmount;
    currentBookCost += stageInputCost;
  }

  return {
    name,
    stages,
    totals: {
      seconds: totalSeconds,
      power: totalPower
    }
  };
};
