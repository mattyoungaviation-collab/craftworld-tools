import { BrowserProvider, getAddress } from 'ethers';

type Eip1193Provider = {
  request: (args: { method: string; params?: unknown[] | Record<string, unknown> }) => Promise<unknown>;
  on?: (event: string, callback: (...args: unknown[]) => void) => void;
  removeListener?: (event: string, callback: (...args: unknown[]) => void) => void;
  disconnect?: () => Promise<void> | void;
};

export type ConnectedWallet = {
  provider: Eip1193Provider;
  address: string;
  type: 'injected' | 'walletconnect';
};

const getInjectedProvider = (): Eip1193Provider | null => {
  if (typeof window === 'undefined') return null;
  const anyWindow = window as typeof window & {
    ronin?: Eip1193Provider & { provider?: Eip1193Provider };
    ethereum?: Eip1193Provider & { providers?: Eip1193Provider[] };
  };
  if (anyWindow.ronin?.provider) return anyWindow.ronin.provider;
  if (anyWindow.ronin) return anyWindow.ronin;
  if (anyWindow.ethereum?.providers?.length) {
    const roninProvider = anyWindow.ethereum.providers.find((provider) => (provider as { isRonin?: boolean }).isRonin);
    if (roninProvider) return roninProvider;
    const metamaskProvider = anyWindow.ethereum.providers.find(
      (provider) => (provider as { isMetaMask?: boolean }).isMetaMask
    );
    if (metamaskProvider) return metamaskProvider;
    return anyWindow.ethereum.providers[0];
  }
  if (anyWindow.ethereum) return anyWindow.ethereum;
  return null;
};

export const connectInjectedWallet = async (): Promise<ConnectedWallet | null> => {
  const provider = getInjectedProvider();
  if (!provider) return null;
  const browserProvider = new BrowserProvider(provider as never);
  const accounts = (await browserProvider.send('eth_requestAccounts', [])) as string[];
  const address = getAddress(accounts[0]);
  return { provider, address, type: 'injected' };
};

export const connectWalletConnect = async (): Promise<ConnectedWallet> => {
  const projectId = process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID;
  if (!projectId) {
    throw new Error('WalletConnect project id missing.');
  }
  const { EthereumProvider } = await import('@walletconnect/ethereum-provider');
  const provider = await EthereumProvider.init({
    projectId,
    chains: [2020],
    showQrModal: true,
    methods: ['eth_requestAccounts', 'personal_sign', 'eth_sign', 'eth_signTypedData', 'eth_signTypedData_v4'],
    events: ['accountsChanged', 'chainChanged', 'disconnect']
  });
  await provider.enable();
  const browserProvider = new BrowserProvider(provider as never);
  const accounts = (await browserProvider.send('eth_requestAccounts', [])) as string[];
  const address = getAddress(accounts[0]);
  return { provider, address, type: 'walletconnect' };
};

export const signMessage = async (wallet: ConnectedWallet, message: string) => {
  const browserProvider = new BrowserProvider(wallet.provider as never);
  const signer = await browserProvider.getSigner();
  return signer.signMessage(message);
};
