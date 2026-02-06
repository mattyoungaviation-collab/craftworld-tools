import { describe, expect, it } from 'vitest';
import {
  computeFactoryResultCsv,
  buildChainReport,
  getEffectiveRecipe,
  buildRecipeIndex,
} from '../index';
import type { FactoryCsvMap } from '../types';

const SAMPLE_FACTORIES: FactoryCsvMap = {
  MUD: {
    1: {
      output_token: 'MUD',
      output_amount: 10,
      duration_min: 10,
      inputs: { EARTH: 20 },
    },
  },
  CLAY: {
    1: {
      output_token: 'CLAY',
      output_amount: 5,
      duration_min: 5,
      inputs: { MUD: 10 },
    },
  },
};

const PRICES = { EARTH: 1, MUD: 3, CLAY: 8, COIN: 1 };

describe('computeFactoryResultCsv', () => {
  it('calculates profitability per craft and hour', () => {
    const result = computeFactoryResultCsv(
      SAMPLE_FACTORIES,
      PRICES,
      'MUD',
      1,
      null,
      1,
      100,
      1,
      0,
    );

    expect(result.cost_coin_per_craft).toBeCloseTo(20, 5);
    expect(result.value_coin_per_craft).toBeCloseTo(30, 5);
    expect(result.profit_coin_per_craft).toBeCloseTo(10, 5);
    expect(result.crafts_per_hour).toBeCloseTo(6, 5);
    expect(result.profit_coin_per_hour).toBeCloseTo(60, 5);
  });
});

describe('buildChainReport', () => {
  it('builds a chain report with expected profit', () => {
    const report = buildChainReport(
      SAMPLE_FACTORIES,
      'EARTH ➜ CLAY',
      ['EARTH', 'MUD', 'CLAY'],
      PRICES,
      { masteryLevelsBySymbol: {}, workshopLevelsByFactoryOrTier: {}, globalSpeedMultiplier: 1.0 },
      10,
    );

    expect(report.error).toBeNull();
    expect(report.total_profit).toBeCloseTo(20, 5);
    expect(report.stages.length).toBe(2);
  });
});

describe('getEffectiveRecipe', () => {
  it('applies mastery and workshop modifiers', () => {
    const { index } = buildRecipeIndex(SAMPLE_FACTORIES);
    const base = index.MUD;
    const effective = getEffectiveRecipe(base, {
      masteryLevelsBySymbol: { MUD: 10 },
      workshopLevelsByFactoryOrTier: { MUD: 1 },
      globalSpeedMultiplier: 1.0,
    });

    expect(effective.inputs[0].qty).toBeLessThan(base.inputs[0].qty);
    expect(effective.craftSeconds).toBeLessThan(base.craftSeconds);
  });
});
