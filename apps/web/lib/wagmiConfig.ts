import { http, createConfig } from 'wagmi';
import { injected } from '@wagmi/connectors/injected'
import { walletConnect } from '@wagmi/connectors/walletConnect'
import { defineChain } from 'viem';

const ronin = defineChain({
  id: 2020,
  name: 'Ronin',
  nativeCurrency: { name: 'Ronin', symbol: 'RON', decimals: 18 },
  rpcUrls: {
    default: { http: ['https://api.roninchain.com/rpc'] }
  },
  blockExplorers: {
    default: { name: 'Ronin Explorer', url: 'https://app.roninchain.com' }
  }
});

const projectId = process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID ?? '';

const connectors = [
  injected({ shimDisconnect: true }),
  ...(projectId
    ? [
        walletConnect({
          projectId,
          showQrModal: true,
          metadata: {
            name: 'CraftWorld Companion',
            description: 'CraftWorld Companion wallet login',
            url: 'https://craft-world.gg',
            icons: ['https://craft-world.gg/favicon.ico']
          }
        })
      ]
    : [])
];

export const wagmiConfig = createConfig({
  chains: [ronin],
  connectors,
  transports: {
    [ronin.id]: http(ronin.rpcUrls.default.http[0])
  },
  ssr: true
});

export const isWalletConnectConfigured = Boolean(projectId);
