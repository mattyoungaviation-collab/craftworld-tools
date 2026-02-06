export type FactoryInputs = Record<string, number>;

export type FactoryLevelRow = {
  output_token: string;
  output_amount: number;
  duration_min: number;
  inputs: FactoryInputs;
  upgrade_token?: string | null;
  upgrade_amount?: number | null;
};

export type FactoriesFromCsv = Record<string, Record<number, FactoryLevelRow>>;

export type PriceMap = Record<string, number>;

export type BoostLevels = Record<string, { mastery_level: number; workshop_level: number }>;

export type ChainReportStage = {
  inputSymbol: string;
  inputAmount: number;
  outputSymbol: string;
  outputAmount: number;
  inputCost: number;
  outputValue: number;
  profit: number;
  roi: number;
  powerCost: number;
  craftSeconds: number;
};

export type ChainReport = {
  name: string;
  stages: ChainReportStage[];
  total_input_cost: number;
  total_output_value: number;
  total_profit: number;
  total_roi: number;
  total_power: number;
  total_seconds: number;
  error?: string;
};
