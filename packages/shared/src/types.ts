export type TokenSymbol = string;

export interface BoostLevels {
  masteryLevel: number;
  workshopLevel: number;
}

export interface WorkshopLevelRow {
  symbol: TokenSymbol;
  level: number;
}

export interface ProficiencyRow {
  symbol: TokenSymbol;
  collectedAmount: number;
  claimedLevel: number;
}

export interface FactoryCsvRow {
  output_token: string;
  output_amount: number;
  duration_min: number;
  inputs: Record<string, number>;
  upgrade_token?: string | null;
  upgrade_amount?: number | null;
}

export type FactoryCsvMap = Record<string, Record<number, FactoryCsvRow>>;

export interface FactoryResult {
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
  upgrade_chain: Array<{
    token: string;
    amount_per_factory: number;
    coin_per_factory: number;
    coin_total: number;
  }>;
}

export interface ChainStage {
  from: string;
  to: string;
  input_amount: number;
  input_price: number;
  input_cost: number;
  other_input_cost: number;
  total_stage_input_cost: number;
  output_amount: number;
  output_price: number;
  output_value: number;
  stage_profit: number;
  stage_roi: number;
  cumulative_cost: number;
  cumulative_profit: number;
  cumulative_roi: number;
  crafts: number;
  seconds: number;
  power: number;
}

export interface ChainReport {
  name: string;
  symbols?: string[];
  start_symbol?: string;
  start_amount?: number;
  end_symbol?: string;
  end_amount?: number;
  total_cost?: number;
  total_value?: number;
  total_profit?: number;
  total_roi?: number;
  total_seconds?: number;
  total_power?: number;
  stages: ChainStage[];
  error: string | null;
}

export interface CraftPlan {
  targetSymbol: string;
  targetAmount: number;
  steps: Array<{
    outputSymbol: string;
    times: number;
    inputs: Array<{ symbol: string; qty: number }>;
    powerCost: number;
    timeCost: number;
    coinCost: number;
    coinValue: number;
  }>;
  totals: {
    power: number;
    seconds: number;
    coinCost: number;
    coinValue: number;
    grossProfit: number;
    profitPerPower: number;
    profitPerHour: number;
    ROI: number;
  };
  missing: {
    prices: string[];
    recipes: string[];
    modifiers: string[];
  };
  constraints: {
    powerNow?: number | null;
    canAffordNow: boolean;
    powerDeficit: number;
    etaToAffordHMS: string;
  };
  externalNeeds: Record<string, number>;
}

export interface Modifiers {
  masteryLevelsBySymbol: Record<string, number>;
  workshopLevelsByFactoryOrTier: Record<string, number>;
  globalSpeedMultiplier: number;
}

export interface PriceBook {
  [symbol: string]: number;
}

export interface BuySellMap {
  [symbol: string]: { [rec: string]: number };
}
