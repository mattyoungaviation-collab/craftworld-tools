import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { parse } from 'csv-parse/sync';
import { factoryRowSchema } from '../schema/factoryRow.js';

const ROOT = path.resolve(process.cwd(), '../..');
const RAW_PATH = path.join(ROOT, 'packages/data/raw/factories.csv');
const OUTPUT_DIR = path.join(ROOT, 'packages/shared/src/generated');

const normalizeToken = (raw: string | null | undefined) => {
  const token = (raw ?? '').trim().toUpperCase();
  if (!token) return '';
  if (token === 'WORMS') return 'WORM';
  return token;
};

const sha256 = (value: string) => crypto.createHash('sha256').update(value).digest('hex');

const run = async () => {
  const csvText = await fs.readFile(RAW_PATH, 'utf-8');
  const rows = parse(csvText, {
    columns: true,
    skip_empty_lines: true,
    trim: true
  });

  const config = rows.map((row: Record<string, string>) => {
    const parsed = factoryRowSchema.parse(row);
    const input1Token = normalizeToken(parsed.input_token_1 ?? '');
    const input2Token = normalizeToken(parsed.input_token_2 ?? '');

    const inputs = [
      input1Token
        ? { token: input1Token, amount: Number(parsed.input_amount_1 ?? 0) }
        : null,
      input2Token
        ? { token: input2Token, amount: Number(parsed.input_amount_2 ?? 0) }
        : null
    ].filter(Boolean);

    return {
      token: normalizeToken(parsed.token),
      level: parsed.level,
      durationMin: parsed.duration_min,
      outputToken: normalizeToken(parsed.output_token ?? parsed.token),
      outputAmount: parsed.output_amount,
      inputs,
      upgrade: parsed.upgrade_token
        ? {
            token: normalizeToken(parsed.upgrade_token),
            amount: Number(parsed.upgrade_amount ?? 0)
          }
        : null
    };
  });

  const tokens = new Set<string>();
  for (const entry of config) {
    tokens.add(entry.token);
    tokens.add(entry.outputToken);
    for (const input of entry.inputs) {
      tokens.add(input.token);
    }
    if (entry.upgrade) tokens.add(entry.upgrade.token);
  }

  const defs = {
    items: Array.from(tokens)
      .filter(Boolean)
      .sort()
      .map((token) => ({ token, name: token }))
  };

  const craftIndex: Record<string, { inputs: { token: string; amount: number }[]; level: number }> = {};
  for (const entry of config) {
    if (!craftIndex[entry.outputToken] || entry.level < craftIndex[entry.outputToken].level) {
      craftIndex[entry.outputToken] = {
        inputs: entry.inputs as { token: string; amount: number }[],
        level: entry.level
      };
    }
  }
  const craftIndexClean: Record<string, { inputs: { token: string; amount: number }[] }> = {};
  for (const [key, value] of Object.entries(craftIndex)) {
    craftIndexClean[key] = { inputs: value.inputs };
  }

  await fs.mkdir(OUTPUT_DIR, { recursive: true });

  const configJson = JSON.stringify({ factories: config }, null, 2);
  const defsJson = JSON.stringify(defs, null, 2);
  const craftIndexJson = JSON.stringify(craftIndexClean, null, 2);

  await Promise.all([
    fs.writeFile(path.join(OUTPUT_DIR, 'config.json'), configJson),
    fs.writeFile(path.join(OUTPUT_DIR, 'defs.json'), defsJson),
    fs.writeFile(path.join(OUTPUT_DIR, 'craft_index.json'), craftIndexJson)
  ]);

  const meta = {
    fetchedAt: new Date().toISOString(),
    version: 'local',
    checksum: {
      config: sha256(configJson),
      defs: sha256(defsJson),
      craftIndex: sha256(craftIndexJson)
    }
  };

  await fs.writeFile(path.join(OUTPUT_DIR, 'meta.json'), JSON.stringify(meta, null, 2));
};

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
