import config from '@craftworld/shared/src/generated/config.json' assert { type: 'json' };
import defs from '@craftworld/shared/src/generated/defs.json' assert { type: 'json' };
import meta from '@craftworld/shared/src/generated/meta.json' assert { type: 'json' };

export const getConfigPayload = () => ({
  ...config,
  meta: meta.checksum?.config ? { ...meta, checksum: { ...meta.checksum, config: meta.checksum.config } } : meta
});

export const getDefsPayload = () => ({
  ...defs,
  meta: meta.checksum?.defs ? { ...meta, checksum: { ...meta.checksum, defs: meta.checksum.defs } } : meta
});
