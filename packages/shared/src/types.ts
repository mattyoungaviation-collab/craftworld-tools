export type RecipeInput = {
  symbol: string;
  qty: number;
};

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

export type CraftTotals = {
  power: number;
  seconds: number;
  coinCost: number;
  coinValue: number;
  grossProfit: number;
  profitPerPower: number;
  profitPerHour: number;
  ROI: number;
};

export type CraftPlan = {
  targetSymbol: string;
  targetAmount: number;
  steps: {
    outputSymbol: string;
    times: number;
    inputs: { symbol: string; qty: number }[];
    powerCost: number;
    timeCost: number;
    coinCost: number;
    coinValue: number;
  }[];
  totals: CraftTotals;
  missing: {
    prices: string[];
    recipes: string[];
    modifiers: string[];
  };
  constraints: {
    powerNow?: number;
    canAffordNow: boolean;
    powerDeficit: number;
    etaToAffordHMS: string;
  };
  externalNeeds: Record<string, number>;
};
