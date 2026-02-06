import {
  ACCOUNT_STATUS_KEY,
  CONNECTION_TYPE_KEY,
  CW_ACTIVE_WALLET_KEY,
  CW_TOKEN_KEY,
  EXPIRES_AT_KEY,
  ID_TOKEN_KEY,
  REFRESH_TOKEN_KEY,
  WALLET_KEY,
  getActiveWallet,
  normalizeWalletAddress,
  readSessionIndex,
  setActiveWallet,
  writeSessionIndex,
} from './storage';
import { apiClient } from './apiClient';

declare global {
  interface Window {
    WalletConnectEthereumProvider?: any;
    ronin?: any;
    ethereum?: any;
  }
}

export type ConnectionType = 'injected' | 'walletconnect';

export interface WalletSessionPayload {
  idToken: string;
  refreshToken: string;
  expiresIn: number;
  walletAddress: string;
  connectionType: ConnectionType;
}

export function getCwToken() {
  const raw = String(localStorage.getItem(CW_TOKEN_KEY) || '').trim();
  if (!raw) return '';
  return raw.toLowerCase().startsWith('bearer ') ? raw.slice(7).trim() : raw;
}

export function isSessionExpired(expiresAt: number) {
  return !expiresAt || Date.now() >= Number(expiresAt || 0);
}

export function getSession() {
  return {
    idToken: localStorage.getItem(ID_TOKEN_KEY) || '',
    cwToken: getCwToken(),
    refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY) || '',
    expiresAt: Number(localStorage.getItem(EXPIRES_AT_KEY) || 0),
    wallet: localStorage.getItem(WALLET_KEY) || '',
  };
}

export function clearSession() {
  localStorage.removeItem(ID_TOKEN_KEY);
  localStorage.removeItem(CW_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(EXPIRES_AT_KEY);
  localStorage.removeItem(WALLET_KEY);
  localStorage.removeItem(CW_ACTIVE_WALLET_KEY);
  localStorage.removeItem(ACCOUNT_STATUS_KEY);
  localStorage.removeItem(CONNECTION_TYPE_KEY);
}

function getInjectedProvider() {
  return (window.ronin && (window.ronin.provider || window.ronin.ethereum)) || window.ethereum || null;
}

async function ensureRoninChain(provider: any) {
  const chainId = Number(import.meta.env.VITE_RONIN_CHAIN_ID || 2020);
  const rpcUrl = import.meta.env.VITE_RONIN_RPC_URL || 'https://api.roninchain.com/rpc';
  const targetHex = `0x${chainId.toString(16)}`;

  try {
    const current = await provider.request({ method: 'eth_chainId' });
    if (String(current).toLowerCase() === targetHex.toLowerCase()) return;
  } catch {
    // continue
  }

  try {
    await provider.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: targetHex }] });
  } catch (err: any) {
    const code = Number(err?.code || 0);
    if (code === 4902 || code === -32603) {
      await provider.request({
        method: 'wallet_addEthereumChain',
        params: [
          {
            chainId: targetHex,
            chainName: chainId === 2020 ? 'Ronin Mainnet' : `Ronin ${chainId}`,
            nativeCurrency: { name: 'Ronin', symbol: 'RON', decimals: 18 },
            rpcUrls: [rpcUrl],
            blockExplorerUrls: [
              chainId === 2020
                ? 'https://app.roninchain.com'
                : 'https://saigon-app.roninchain.com',
            ],
          },
        ],
      });
    } else {
      throw err;
    }
  }
}

async function getWalletConnectProvider() {
  const projectId = import.meta.env.VITE_WALLETCONNECT_PROJECT_ID;
  if (!projectId) throw new Error('WalletConnect is not configured.');
  const EthereumProvider = window.WalletConnectEthereumProvider;
  if (!EthereumProvider) throw new Error('WalletConnect client failed to load.');
  const chainId = Number(import.meta.env.VITE_RONIN_CHAIN_ID || 2020);
  const rpcUrl = import.meta.env.VITE_RONIN_RPC_URL || 'https://api.roninchain.com/rpc';
  return EthereumProvider.init({
    projectId,
    chains: [chainId],
    optionalChains: [chainId],
    showQrModal: true,
    methods: ['eth_sendTransaction', 'personal_sign', 'eth_signTypedData', 'eth_signTypedData_v4'],
    rpcMap: { [chainId]: rpcUrl },
  });
}

export async function connectWallet(connectionType: ConnectionType) {
  const provider = connectionType === 'walletconnect' ? await getWalletConnectProvider() : getInjectedProvider();
  if (!provider) throw new Error('No injected wallet provider found.');

  const accounts = await provider.request({ method: 'eth_requestAccounts' });
  const walletAddress = normalizeWalletAddress(accounts?.[0] || '');
  if (!walletAddress) throw new Error('No wallet address returned by provider.');

  await ensureRoninChain(provider);
  const nonceData = await apiClient.getNonce(walletAddress);
  const signature = await provider.request({
    method: 'personal_sign',
    params: [nonceData.nonce, walletAddress],
  });

  const customTokenData = await apiClient.loginForCustomToken(walletAddress, signature);
  const signinData = await apiClient.signinWithCustomToken(customTokenData.customToken);

  const expiresAt = Date.now() + Number(signinData.expiresIn || 0) * 1000;

  const sessionPayload: WalletSessionPayload = {
    idToken: signinData.idToken,
    refreshToken: signinData.refreshToken || '',
    expiresIn: signinData.expiresIn || 0,
    walletAddress,
    connectionType,
  };

  localStorage.setItem(ID_TOKEN_KEY, sessionPayload.idToken);
  localStorage.setItem(CW_TOKEN_KEY, sessionPayload.idToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, sessionPayload.refreshToken);
  localStorage.setItem(EXPIRES_AT_KEY, String(expiresAt));
  localStorage.setItem(WALLET_KEY, walletAddress);
  localStorage.setItem(CONNECTION_TYPE_KEY, connectionType);

  const sessions = readSessionIndex();
  sessions[walletAddress] = {
    token: sessionPayload.idToken,
    expiresAt,
    refreshToken: sessionPayload.refreshToken,
    lastLoginAt: Date.now(),
    idToken: sessionPayload.idToken,
  };
  writeSessionIndex(sessions);
  setActiveWallet(walletAddress);

  return { provider, walletAddress, expiresAt };
}
