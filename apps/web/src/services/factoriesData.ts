import factoriesCsv from '@data/factories/Game Data - Factories - rev. v_01 +events.csv?raw';
import { buildFactoryDisplayOrder, loadFactoriesFromCsv } from '@shared/factories';

export const FACTORIES = loadFactoriesFromCsv(factoriesCsv);
export const FACTORY_ORDER = buildFactoryDisplayOrder(FACTORIES);
