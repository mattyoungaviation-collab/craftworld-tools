import { describe, expect, it } from 'vitest';
import {
  buildChainReport,
  computeFactoryResultCsv,
  getEffectiveRecipe,
  type Modifiers,
} from '../index';

const sampleFactories = {
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
} as const;

describe('calculate profitability math', () => {
  it('computes profit per craft and hour', () => {
    const result = computeFactoryResultCsv(
      sampleFactories,
      { EARTH: 1, MUD: 2, CLAY: 3 },
      'MUD',
      1,
      null,
      1,
      100,
      1,
      0,
    );
    expect(result.cost_coin_per_craft).toBeCloseTo(20);
    expect(result.value_coin_per_craft).toBeCloseTo(20);
    expect(result.profit_coin_per_craft).toBeCloseTo(0);
  });
});

describe('boost application', () => {
  it('reduces inputs via mastery and speeds up via workshop', () => {
    const baseRecipe = {
      outputSymbol: 'MUD',
      outputQty: 10,
      inputs: [{ symbol: 'EARTH', qty: 20 }],
      craftSeconds: 600,
      powerCost: 5,
      level: 1,
    };
    const modifiers: Modifiers = {
      masteryLevelsBySymbol: { MUD: 10 },
      workshopLevelsByFactoryOrTier: { MUD: 10 },
      globalSpeedMultiplier: 1,
    };
    const effective = getEffectiveRecipe(baseRecipe, modifiers);
    expect(effective.inputs[0].qty).toBeLessThan(baseRecipe.inputs[0].qty);
    expect(effective.craftSeconds).toBeLessThan(baseRecipe.craftSeconds);
  });
});

describe('crafting chains', () => {
  it('builds a chain report with ROI', () => {
    const report = buildChainReport(sampleFactories, 'Test', ['MUD', 'CLAY'], {
      EARTH: 1,
      MUD: 2,
      CLAY: 4,
    });
    expect(report.error).toBeUndefined();
    expect(report.stages.length).toBe(1);
    expect(report.total_roi).toBeDefined();
  });
});
