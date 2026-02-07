import config from '@craftworld/shared/src/generated/config.json' with { type: 'json' };
import defs from '@craftworld/shared/src/generated/defs.json' with { type: 'json' };
import meta from '@craftworld/shared/src/generated/meta.json' with { type: 'json' };

export const getConfigPayload = () => ({
  ...config,
  meta: meta.checksum?.config ? { ...meta, checksum: { ...meta.checksum, config: meta.checksum.config } } : meta
});

export const getDefsPayload = () => ({
  ...defs,
  meta: meta.checksum?.defs ? { ...meta, checksum: { ...meta.checksum, defs: meta.checksum.defs } } : meta
});
