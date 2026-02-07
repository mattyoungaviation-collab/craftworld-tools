import { describe, expect, it } from 'vitest';
import { buildChainReport, planCraft } from '../src/logic.js';

const prices = {
  EARTH: 0,
  WATER: 5,
  FIRE: 10,
  MUD: 2,
  CLAY: 4,
  SAND: 6
};

describe('planCraft', () => {
  it('computes profitability for base-driven recipes', () => {
    const mudPlan = planCraft('MUD', 10, prices, 'craft');
    const clayPlan = planCraft('CLAY', 10, prices, 'craft');
    const sandPlan = planCraft('SAND', 10, prices, 'craft');

    expect(mudPlan.totals.coinCost).toBeCloseTo(0);
    expect(mudPlan.totals.grossProfit).toBeCloseTo(20);

    expect(clayPlan.totals.coinCost).toBeCloseTo(0);
    expect(clayPlan.totals.grossProfit).toBeCloseTo(40);

    expect(sandPlan.totals.coinCost).toBeCloseTo(0);
    expect(sandPlan.totals.grossProfit).toBeCloseTo(60);
  });
});

describe('buildChainReport', () => {
  it('walks a simple chain and produces expected output', () => {
    const chain = buildChainReport('EARTH → CLAY', ['EARTH', 'MUD', 'CLAY'], prices, undefined, 9);
    expect(chain.error).toBeUndefined();
    expect(chain.stages[0].outputAmount).toBeCloseTo(3);
    expect(chain.stages[1].outputAmount).toBeCloseTo(0.3);
  });
});
