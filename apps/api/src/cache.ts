import fs from 'node:fs/promises';
import path from 'node:path';

const DEFAULT_DATA_DIR = '/var/data';

export const getDataDir = () => process.env.DATA_DIR || DEFAULT_DATA_DIR;

export const readSnapshot = async (key: string) => {
  const filePath = path.join(getDataDir(), 'cache', `${key}.json`);
  try {
    const data = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(data) as unknown;
  } catch (error) {
    return null;
  }
};

export const writeSnapshot = async (key: string, payload: unknown) => {
  const filePath = path.join(getDataDir(), 'cache', `${key}.json`);
  try {
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    await fs.writeFile(filePath, JSON.stringify(payload, null, 2));
  } catch (error) {
    // Ignore disk write errors to keep runtime resilient
  }
};
