'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { WagmiProvider, useAccount, useConnect, useDisconnect, useSignMessage } from 'wagmi';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cwGraphqlRequest } from '../../lib/cwClient';
import { exchangeCustomToken, lookupAccountInfo, refreshIdToken } from '../../lib/firebaseAuth';
import {
  clearStoredSession,
  readStoredSession,
  readWorkshopCache,
  writeStoredSession,
  writeWorkshopCache
} from '../../lib/authStorage';
import { isWalletConnectConfigured, wagmiConfig } from '../../lib/wagmiConfig';

type AuthStatus = 'disconnected' | 'connecting' | 'connected' | 'logging_in' | 'authenticated' | 'error';

type AuthState = {
  status: AuthStatus;
  walletAddress: string | null;
  idToken: string | null;
  refreshToken: string | null;
  expiresAt: number | null;
  localId: string | null;
  error: string | null;
};

type ExchangePriceListResponse = {
  exchangePriceList: Array<{
    baseSymbol: string;
    prices: Array<{ referenceSymbol: string; amount: number; recommendation?: string | null }>;
  }>;
};

type ResourcesResponse = {
  account: { resources: Array<{ symbol: string; amount: number }> };
};

type WalletsResponse = {
  account: { wallets: Array<{ address: string; type?: string | null; provider?: string | null; providerId?: string | null; primary?: boolean | null }> };
};

type WorkshopResponse = {
  account: { workshop: Array<{ symbol: string; level: number }> };
};

type ProficienciesResponse = {
  account: { proficiencies: Array<{ symbol: string; collectedAmount: number; claimedLevel: number }> };
};

type ProficiencyLeaderboardResponse = {
  proficiencyLeaderboard: {
    leaderboard: Array<{
      position: number;
      collectedAmount: number;
      profile: { uid: string; walletAddress?: string | null; avatarUrl?: string | null; displayName?: string | null };
    }>;
    entryByUserId?: {
      position: number;
      collectedAmount: number;
      profile: { uid: string; walletAddress?: string | null; avatarUrl?: string | null; displayName?: string | null };
    } | null;
  };
};

const queryClient = new QueryClient();

const LOGIN_FOR_CUSTOM_TOKEN = `
  mutation LoginForCustomToken($signature: String!, $walletAddress: String!) {
    loginForCustomToken(signature: $signature, walletAddress: $walletAddress) {
      customToken
    }
  }
`;

const EXCHANGE_PRICE_LIST_QUERY = `
  query ExchangePriceList {
    exchangePriceList {
      baseSymbol
      prices {
        referenceSymbol
        amount
        recommendation
      }
    }
  }
`;

const ACCOUNT_RESOURCES_QUERY = `
  query AccountResources {
    account {
      resources {
        symbol
        amount
      }
    }
  }
`;

const ACCOUNT_WALLETS_QUERY = `
  query AccountWallets {
    account {
      wallets {
        address
        type
        provider
        providerId
        primary
      }
    }
  }
`;

const ACCOUNT_WORKSHOP_QUERY = `
  query AccountWorkshop {
    account {
      workshop {
        symbol
        level
      }
    }
  }
`;

const ACCOUNT_PROFICIENCIES_QUERY = `
  query AccountProficiencies {
    account {
      proficiencies {
        symbol
        collectedAmount
        claimedLevel
      }
    }
  }
`;

const PROFICIENCY_LEADERBOARD_QUERY = `
  query ProficiencyLeaderboard($symbol: String!, $userId: String!) {
    proficiencyLeaderboard(symbol: $symbol) {
      leaderboard(count: 100) {
        position
        collectedAmount
        profile {
          uid
          walletAddress
          avatarUrl
          displayName
        }
      }
      entryByUserId(userId: $userId) {
        position
        collectedAmount
        profile {
          uid
          walletAddress
          avatarUrl
          displayName
        }
      }
    }
  }
`;

const DEPUTY_WALLET_QUERY = `
  query DeputyWalletAddress($walletAddress: String!) {
    deputyWalletAddress(walletAddress: $walletAddress)
  }
`;

const GET_WALLETS_QUERY = `
  query GetWallets {
    getWallets {
      address
      type
      provider
      providerId
      primary
    }
  }
`;

const formatAddress = (address?: string | null) => {
  if (!address) return '—';
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
};

const formatDuration = (expiresAt?: number | null) => {
  if (!expiresAt) return '—';
  const ms = expiresAt - Date.now();
  if (ms <= 0) return 'expired';
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
};

const redactSensitive = (value: unknown): unknown => {
  if (Array.isArray(value)) {
    return value.map((entry) => redactSensitive(entry));
  }
  if (value && typeof value === 'object') {
    const result: Record<string, unknown> = {};
    for (const [key, entry] of Object.entries(value as Record<string, unknown>)) {
      if (['idToken', 'refreshToken', 'customToken', 'token', 'accessToken'].includes(key)) {
        result[key] = '[redacted]';
      } else {
        result[key] = redactSensitive(entry);
      }
    }
    return result;
  }
  return value;
};

const CopyButton = ({ value, label }: { value?: string | null; label?: string }) => (
  <button
    type="button"
    className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
    onClick={async () => {
      if (!value) return;
      await navigator.clipboard.writeText(value);
    }}
  >
    {label ?? 'Copy'}
  </button>
);

const SectionCard = ({ title, children }: { title: string; children: ReactNode }) => (
  <section className="rounded border border-slate-800 bg-slate-900 p-4 shadow-sm">
    <h2 className="text-lg font-semibold text-white">{title}</h2>
    <div className="mt-3 space-y-3 text-sm text-slate-200">{children}</div>
  </section>
);

const WarningBanner = ({ text }: { text: string }) => (
  <div className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">{text}</div>
);

const Tabs = ({
  tabs,
  active,
  onChange
}: {
  tabs: Array<{ id: string; label: string }>;
  active: string;
  onChange: (id: string) => void;
}) => (
  <div className="sticky top-0 z-10 -mx-4 bg-slate-950/80 px-4 py-2 backdrop-blur">
    <div className="flex gap-2 overflow-x-auto pb-1">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={`whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold ${
            active === tab.id ? 'bg-emerald-500 text-slate-950' : 'border border-slate-700 text-slate-200'
          }`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  </div>
);

const useAuthState = () => {
  const [state, setState] = useState<AuthState>({
    status: 'disconnected',
    walletAddress: null,
    idToken: null,
    refreshToken: null,
    expiresAt: null,
    localId: null,
    error: null
  });

  useEffect(() => {
    const stored = readStoredSession();
    setState((prev) => ({
      ...prev,
      walletAddress: stored.walletAddress ?? null,
      idToken: stored.idToken ?? null,
      refreshToken: stored.refreshToken ?? null,
      expiresAt: stored.expiresAt ?? null,
      localId: stored.localId ?? null,
      status: stored.idToken ? 'authenticated' : stored.walletAddress ? 'connected' : 'disconnected'
    }));
  }, []);

  const updateSession = useCallback((partial: Partial<AuthState>) => {
    setState((prev) => {
      const next = { ...prev, ...partial };
      writeStoredSession({
        walletAddress: next.walletAddress,
        idToken: next.idToken,
        refreshToken: next.refreshToken,
        expiresAt: next.expiresAt,
        localId: next.localId
      });
      return next;
    });
  }, []);

  const setStatus = useCallback((status: AuthStatus, error: string | null = null) => {
    setState((prev) => ({ ...prev, status, error }));
  }, []);

  return { state, setState, updateSession, setStatus };
};

const CWAppShell = () => {
  const { state, setState, updateSession, setStatus } = useAuthState();
  const { address, isConnected } = useAccount();
  const { connectAsync, connectors, isPending: isConnecting } = useConnect();
  const { disconnectAsync } = useDisconnect();
  const { signMessageAsync } = useSignMessage();
  const [activeTab, setActiveTab] = useState('home');
  const [loginNonce, setLoginNonce] = useState<string | null>(null);
  const [latestCustomToken, setLatestCustomToken] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const [prices, setPrices] = useState<ExchangePriceListResponse['exchangePriceList']>([]);
  const [pricesUpdatedAt, setPricesUpdatedAt] = useState<number | null>(null);
  const [resources, setResources] = useState<ResourcesResponse['account']['resources']>([]);
  const [wallets, setWallets] = useState<WalletsResponse['account']['wallets']>([]);
  const [selectedDeputyWallet, setSelectedDeputyWallet] = useState<string>('');
  const [deputyResult, setDeputyResult] = useState<string | null>(null);
  const [workshop, setWorkshop] = useState<WorkshopResponse['account']['workshop']>([]);
  const [proficiencies, setProficiencies] = useState<ProficienciesResponse['account']['proficiencies']>([]);
  const [leaderboardSymbol, setLeaderboardSymbol] = useState<string>('');
  const [leaderboardData, setLeaderboardData] = useState<ProficiencyLeaderboardResponse['proficiencyLeaderboard'] | null>(null);
  const [leaderboardFetchedAt, setLeaderboardFetchedAt] = useState<number | null>(null);
  const [callResults, setCallResults] = useState<Record<string, { data?: unknown; error?: string; loading?: boolean }>>({});
  const leaderboardCache = useRef(new Map<string, { data: ProficiencyLeaderboardResponse['proficiencyLeaderboard']; fetchedAt: number }>());

  const handleError = (error: unknown) => {
    const message = (error as Error).message;
    setStatusMessage(message);
    setStatus('error', message);
  };

  useEffect(() => {
    if (address) {
      updateSession({ walletAddress: address, status: state.idToken ? 'authenticated' : 'connected' });
    } else if (!isConnected && state.status !== 'authenticated') {
      updateSession({ walletAddress: null, status: 'disconnected' });
    }
  }, [address, isConnected, state.idToken, state.status, updateSession]);

  useEffect(() => {
    const cached = readWorkshopCache();
    if (cached?.payload) {
      setWorkshop(cached.payload as WorkshopResponse['account']['workshop']);
    }
  }, []);

  const selectConnector = () => {
    const hasInjected = typeof window !== 'undefined' && (window as Window & { ronin?: unknown; ethereum?: unknown }).ronin;
    const hasEthereum = typeof window !== 'undefined' && (window as Window & { ethereum?: unknown }).ethereum;
    if (hasInjected || hasEthereum) {
      return connectors.find((connector) => connector.id === 'injected') ?? connectors[0];
    }
    return connectors.find((connector) => connector.id === 'walletConnect') ?? connectors[0];
  };

  const ensureFreshToken = async () => {
    if (!state.idToken) {
      throw new Error('No active session');
    }
    if (state.expiresAt && Date.now() > state.expiresAt) {
      if (!state.refreshToken) {
        throw new Error('Session expired, please log in again.');
      }
      const refreshed = await refreshIdToken(state.refreshToken);
      updateSession({
        idToken: refreshed.idToken,
        refreshToken: refreshed.refreshToken,
        expiresAt: refreshed.expiresAt,
        status: 'authenticated'
      });
      return refreshed.idToken;
    }
    return state.idToken;
  };

  const handleConnect = async () => {
    setStatusMessage(null);
    setStatus('connecting');
    try {
      const connector = selectConnector();
      if (connector.id === 'walletConnect' && !isWalletConnectConfigured) {
        throw new Error('WalletConnect requires NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID.');
      }
      await connectAsync({ connector });
      setStatus('connected');
    } catch (error) {
      setStatus('error', (error as Error).message);
    }
  };

  const handleDisconnect = async () => {
    setStatusMessage(null);
    await disconnectAsync();
    clearStoredSession();
    setState({
      status: 'disconnected',
      walletAddress: null,
      idToken: null,
      refreshToken: null,
      expiresAt: null,
      localId: null,
      error: null
    });
  };

  const handleLogin = async () => {
    if (!address) {
      setStatusMessage('Connect a wallet first.');
      return;
    }
    setStatus('logging_in');
    setStatusMessage(null);
    try {
      const nonce = crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Array.from(crypto.getRandomValues(new Uint8Array(8)))
            .map((byte) => byte.toString(16).padStart(2, '0'))
            .join('')}`;
      setLoginNonce(nonce);
      const issuedAt = new Date().toISOString();
      const message = `CraftWorld login\nwallet: ${address}\nnonce: ${nonce}\nissuedAt: ${issuedAt}`;
      const signature = await signMessageAsync({ message });
      const loginResponse = await cwGraphqlRequest<{ loginForCustomToken: { customToken: string } }>(
        {
          operationName: 'LoginForCustomToken',
          query: LOGIN_FOR_CUSTOM_TOKEN,
          variables: { signature, walletAddress: address }
        }
      );
      const customToken = loginResponse.loginForCustomToken.customToken;
      setLatestCustomToken(customToken);
      const tokenExchange = await exchangeCustomToken(customToken);
      const localId = await lookupAccountInfo(tokenExchange.idToken);
      updateSession({
        status: 'authenticated',
        walletAddress: address,
        idToken: tokenExchange.idToken,
        refreshToken: tokenExchange.refreshToken,
        expiresAt: tokenExchange.expiresAt,
        localId
      });
    } catch (error) {
      setStatus('error', (error as Error).message);
    }
  };

  const handleLogout = () => {
    setStatusMessage(null);
    updateSession({
      status: state.walletAddress ? 'connected' : 'disconnected',
      idToken: null,
      refreshToken: null,
      expiresAt: null,
      localId: null
    });
  };

  const runAuthenticatedRequest = async <T,>(request: Parameters<typeof cwGraphqlRequest<T>>[0]) => {
    const token = await ensureFreshToken();
    return cwGraphqlRequest<T>(request, { idToken: token });
  };

  const handleRefreshAll = async () => {
    setStatusMessage(null);
    try {
      await Promise.all([fetchPrices(), fetchResources(), fetchWallets(), fetchWorkshop(), fetchProficiencies()]);
      setStatusMessage('Data refreshed.');
    } catch (error) {
      setStatusMessage((error as Error).message);
    }
  };

  const fetchPrices = async () => {
    const data = await cwGraphqlRequest<ExchangePriceListResponse>({
      operationName: 'ExchangePriceList',
      query: EXCHANGE_PRICE_LIST_QUERY
    });
    setPrices(data.exchangePriceList);
    setPricesUpdatedAt(Date.now());
  };

  const fetchResources = async () => {
    const data = await runAuthenticatedRequest<ResourcesResponse>({
      operationName: 'AccountResources',
      query: ACCOUNT_RESOURCES_QUERY
    });
    setResources(data.account.resources ?? []);
  };

  const fetchWallets = async () => {
    const data = await runAuthenticatedRequest<WalletsResponse>({
      operationName: 'AccountWallets',
      query: ACCOUNT_WALLETS_QUERY
    });
    setWallets(data.account.wallets ?? []);
    const primary = data.account.wallets?.find((wallet) => wallet.primary);
    if (primary?.address) {
      setSelectedDeputyWallet(primary.address);
    }
  };

  const fetchWorkshop = async () => {
    const data = await runAuthenticatedRequest<WorkshopResponse>({
      operationName: 'AccountWorkshop',
      query: ACCOUNT_WORKSHOP_QUERY
    });
    const sorted = [...(data.account.workshop ?? [])].sort((a, b) => b.level - a.level || a.symbol.localeCompare(b.symbol));
    setWorkshop(sorted);
    writeWorkshopCache(sorted);
  };

  const fetchProficiencies = async () => {
    const data = await runAuthenticatedRequest<ProficienciesResponse>({
      operationName: 'AccountProficiencies',
      query: ACCOUNT_PROFICIENCIES_QUERY
    });
    setProficiencies(data.account.proficiencies ?? []);
  };

  const fetchDeputy = async () => {
    if (!selectedDeputyWallet) return;
    const data = await runAuthenticatedRequest<{ deputyWalletAddress: string | null }>({
      operationName: 'DeputyWalletAddress',
      query: DEPUTY_WALLET_QUERY,
      variables: { walletAddress: selectedDeputyWallet }
    });
    setDeputyResult(data.deputyWalletAddress ?? null);
  };

  const fetchLeaderboard = async (symbol: string, useCache = true) => {
    if (!symbol) {
      setStatusMessage('Enter a symbol to fetch leaderboards.');
      return;
    }
    if (!state.localId) {
      setStatusMessage('Local ID missing. Re-login to fetch leaderboards.');
      return;
    }
    const cached = leaderboardCache.current.get(symbol);
    if (useCache && cached && Date.now() - cached.fetchedAt < 60_000) {
      setLeaderboardData(cached.data);
      setLeaderboardFetchedAt(cached.fetchedAt);
      return;
    }
    const data = await runAuthenticatedRequest<ProficiencyLeaderboardResponse>({
      operationName: 'ProficiencyLeaderboard',
      query: PROFICIENCY_LEADERBOARD_QUERY,
      variables: { symbol, userId: state.localId }
    });
    leaderboardCache.current.set(symbol, { data: data.proficiencyLeaderboard, fetchedAt: Date.now() });
    setLeaderboardData(data.proficiencyLeaderboard);
    setLeaderboardFetchedAt(Date.now());
  };

  const priceIndex = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of prices) {
      const coin = row.prices.find((entry) => entry.referenceSymbol === 'COIN');
      if (coin) {
        map.set(row.baseSymbol, coin.amount);
      }
    }
    return map;
  }, [prices]);

  const callCatalog = [
    {
      key: 'loginForCustomToken',
      name: 'loginForCustomToken',
      requiresAuth: false,
      variablesExample: { signature: '<signature>', walletAddress: '<address>' },
      run: async () => {
        if (!address) throw new Error('Connect a wallet first.');
        const nonce = crypto.randomUUID
          ? crypto.randomUUID()
          : `${Date.now()}-${Array.from(crypto.getRandomValues(new Uint8Array(8)))
              .map((byte) => byte.toString(16).padStart(2, '0'))
              .join('')}`;
        const issuedAt = new Date().toISOString();
        const message = `CraftWorld login\nwallet: ${address}\nnonce: ${nonce}\nissuedAt: ${issuedAt}`;
        const signature = await signMessageAsync({ message });
        const loginResponse = await cwGraphqlRequest<{ loginForCustomToken: { customToken: string } }>(
          {
            operationName: 'LoginForCustomToken',
            query: LOGIN_FOR_CUSTOM_TOKEN,
            variables: { signature, walletAddress: address }
          }
        );
        setLatestCustomToken(loginResponse.loginForCustomToken.customToken);
        return { customToken: '[redacted]' };
      }
    },
    {
      key: 'exchangeCustomToken',
      name: 'exchange custom token (signInWithCustomToken)',
      requiresAuth: false,
      variablesExample: { token: '<customToken>' },
      run: async () => {
        if (!latestCustomToken) {
          throw new Error('Run loginForCustomToken first to generate a custom token.');
        }
        await exchangeCustomToken(latestCustomToken);
        return { idToken: '[redacted]', refreshToken: '[redacted]', expiresIn: '[redacted]' };
      }
    },
    {
      key: 'lookupAccountInfo',
      name: 'getAccountInfo (accounts:lookup)',
      requiresAuth: true,
      variablesExample: { idToken: '<idToken>' },
      run: async () => {
        const token = await ensureFreshToken();
        const localId = await lookupAccountInfo(token);
        return { localId };
      }
    },
    {
      key: 'getWallets',
      name: 'getWallets query',
      requiresAuth: true,
      variablesExample: {},
      run: async () => {
        const data = await runAuthenticatedRequest<{ getWallets: WalletsResponse['account']['wallets'] }>({
          operationName: 'GetWallets',
          query: GET_WALLETS_QUERY
        });
        return data;
      }
    },
    {
      key: 'verifiedToken',
      name: 'verifiedToken (optional / not implemented)',
      requiresAuth: true,
      variablesExample: {}
    },
    {
      key: 'linkedAccounts',
      name: 'linkedAccounts / wallets (optional / not implemented)',
      requiresAuth: true,
      variablesExample: {}
    },
    {
      key: 'exchangePriceList',
      name: 'exchangePriceList query',
      requiresAuth: false,
      variablesExample: {},
      run: async () => {
        const data = await cwGraphqlRequest<ExchangePriceListResponse>({
          operationName: 'ExchangePriceList',
          query: EXCHANGE_PRICE_LIST_QUERY
        });
        return data;
      }
    },
    {
      key: 'accountResources',
      name: 'account resources query',
      requiresAuth: true,
      variablesExample: {},
      run: async () => runAuthenticatedRequest<ResourcesResponse>({ operationName: 'AccountResources', query: ACCOUNT_RESOURCES_QUERY })
    },
    {
      key: 'deputyWalletAddress',
      name: 'deputyWalletAddress query',
      requiresAuth: true,
      variablesExample: { walletAddress: '<walletAddress>' },
      run: async () => {
        if (!selectedDeputyWallet) throw new Error('Provide a wallet address first.');
        return runAuthenticatedRequest({
          operationName: 'DeputyWalletAddress',
          query: DEPUTY_WALLET_QUERY,
          variables: { walletAddress: selectedDeputyWallet }
        });
      }
    },
    {
      key: 'workshop',
      name: 'workshop query',
      requiresAuth: true,
      variablesExample: {},
      run: async () => runAuthenticatedRequest({ operationName: 'AccountWorkshop', query: ACCOUNT_WORKSHOP_QUERY })
    },
    {
      key: 'proficiencies',
      name: 'proficiencies query',
      requiresAuth: true,
      variablesExample: {},
      run: async () => runAuthenticatedRequest({ operationName: 'AccountProficiencies', query: ACCOUNT_PROFICIENCIES_QUERY })
    },
    {
      key: 'proficiencyLeaderboard',
      name: 'proficiencyLeaderboard query',
      requiresAuth: true,
      variablesExample: { symbol: '<symbol>', userId: '<localId>' },
      run: async () => {
        if (!state.localId) throw new Error('Missing localId. Run account lookup first.');
        return runAuthenticatedRequest({
          operationName: 'ProficiencyLeaderboard',
          query: PROFICIENCY_LEADERBOARD_QUERY,
          variables: { symbol: leaderboardSymbol || 'WOOD', userId: state.localId }
        });
      }
    }
  ];

  const runCatalogCall = async (key: string, runner?: () => Promise<unknown>) => {
    if (!runner) {
      setCallResults((prev) => ({ ...prev, [key]: { error: 'Not implemented', loading: false } }));
      return;
    }
    setCallResults((prev) => ({ ...prev, [key]: { loading: true } }));
    try {
      const data = await runner();
      setCallResults((prev) => ({ ...prev, [key]: { data: redactSensitive(data), loading: false } }));
    } catch (error) {
      setCallResults((prev) => ({ ...prev, [key]: { error: (error as Error).message, loading: false } }));
    }
  };

  const tabs = [
    { id: 'home', label: 'Home' },
    { id: 'calls', label: 'Calls' },
    { id: 'prices', label: 'Prices' },
    { id: 'resources', label: 'Resources' },
    { id: 'wallets', label: 'Wallets' },
    { id: 'deputy', label: 'Deputy' },
    { id: 'workshop', label: 'Workshop' },
    { id: 'mastery', label: 'Mastery' },
    { id: 'leaderboards', label: 'Leaderboards' },
    { id: 'notes', label: 'Notes' }
  ];

  const resourcesWithValue = useMemo(() => {
    return resources.map((resource) => {
      const price = priceIndex.get(resource.symbol) ?? 0;
      return { ...resource, value: price * resource.amount };
    });
  }, [resources, priceIndex]);

  const [resourceSort, setResourceSort] = useState<'value' | 'amount' | 'symbol'>('value');
  const sortedResources = useMemo(() => {
    const list = [...resourcesWithValue];
    if (resourceSort === 'value') {
      list.sort((a, b) => b.value - a.value);
    } else if (resourceSort === 'amount') {
      list.sort((a, b) => b.amount - a.amount);
    } else {
      list.sort((a, b) => a.symbol.localeCompare(b.symbol));
    }
    return list;
  }, [resourceSort, resourcesWithValue]);

  const [priceSearch, setPriceSearch] = useState('');
  const filteredPrices = useMemo(() => {
    if (!priceSearch) return prices;
    const query = priceSearch.toLowerCase();
    return prices.filter((row) => row.baseSymbol.toLowerCase().includes(query));
  }, [prices, priceSearch]);

  return (
    <div className="space-y-6 text-slate-200">
      <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />

      {state.error ? (
        <div className="rounded border border-rose-500/40 bg-rose-500/10 px-4 py-2 text-sm text-rose-200">{state.error}</div>
      ) : null}
      {statusMessage ? (
        <div className="rounded border border-slate-700 bg-slate-900 px-4 py-2 text-sm text-slate-200">{statusMessage}</div>
      ) : null}

      {activeTab === 'home' ? (
        <div className="space-y-4">
          <SectionCard title="Status">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="rounded bg-slate-800 px-2 py-1 text-xs uppercase text-slate-300">{state.status}</span>
              <span>Wallet: {formatAddress(state.walletAddress)}</span>
              <CopyButton value={state.walletAddress} label="Copy address" />
            </div>
            <div className="text-xs text-slate-400">Session expires in: {formatDuration(state.expiresAt)}</div>
            <div className="text-xs text-slate-400">Local ID: {state.localId ?? '—'}</div>
          </SectionCard>

          <SectionCard title="Actions">
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded bg-emerald-500 px-3 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50"
                onClick={handleConnect}
                disabled={isConnecting || state.status === 'connecting'}
              >
                Connect wallet
              </button>
              <button
                type="button"
                className="rounded border border-slate-700 px-3 py-2 text-sm text-slate-200 disabled:opacity-50"
                onClick={handleDisconnect}
                disabled={!isConnected}
              >
                Disconnect
              </button>
              <button
                type="button"
                className="rounded bg-slate-200 px-3 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50"
                onClick={handleLogin}
                disabled={!state.walletAddress || state.status === 'logging_in'}
              >
                Login
              </button>
              <button
                type="button"
                className="rounded border border-slate-700 px-3 py-2 text-sm text-slate-200 disabled:opacity-50"
                onClick={handleLogout}
                disabled={!state.idToken}
              >
                Logout
              </button>
              <button
                type="button"
                className="rounded border border-slate-700 px-3 py-2 text-sm text-slate-200"
                onClick={handleRefreshAll}
              >
                Refresh data
              </button>
            </div>
            <div className="text-xs text-slate-400">
              Nonce: {loginNonce ?? '—'} (stored only during login)
            </div>
          </SectionCard>
        </div>
      ) : null}

      {activeTab === 'calls' ? (
        <div className="space-y-4">
          <WarningBanner text="Do not share outputs containing tokens." />
          <div className="space-y-3">
            {callCatalog.map((call) => (
              <SectionCard key={call.key} title={call.name}>
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                  <span>{call.requiresAuth ? 'Auth required' : 'No auth required'}</span>
                  <span>Variables example: {JSON.stringify(call.variablesExample)}</span>
                </div>
                <button
                  type="button"
                  className="mt-2 rounded bg-emerald-500 px-3 py-1 text-xs font-semibold text-slate-950 disabled:opacity-40"
                  onClick={() => runCatalogCall(call.key, call.run)}
                  disabled={callResults[call.key]?.loading}
                >
                  Run
                </button>
                {callResults[call.key]?.error ? (
                  <div className="mt-2 text-xs text-rose-300">{callResults[call.key]?.error}</div>
                ) : null}
                {callResults[call.key]?.data ? (
                  <pre className="mt-2 max-h-72 overflow-auto rounded bg-slate-950 p-3 text-xs text-slate-200">
                    {JSON.stringify(callResults[call.key]?.data, null, 2)}
                  </pre>
                ) : null}
              </SectionCard>
            ))}
          </div>
        </div>
      ) : null}

      {activeTab === 'prices' ? (
        <div className="space-y-4">
          <SectionCard title="Exchange Price List">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <button
                type="button"
                className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-200"
                onClick={() => void fetchPrices().catch(handleError)}
              >
                Load prices
              </button>
              <span>Last updated: {pricesUpdatedAt ? new Date(pricesUpdatedAt).toLocaleTimeString() : '—'}</span>
              <input
                value={priceSearch}
                onChange={(event) => setPriceSearch(event.target.value)}
                placeholder="Search symbol"
                className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
              />
            </div>
            <div className="mt-3 divide-y divide-slate-800">
              {filteredPrices.map((row) => {
                const coin = row.prices.find((entry) => entry.referenceSymbol === 'COIN');
                return (
                  <div key={row.baseSymbol} className="flex items-center justify-between py-2 text-sm">
                    <div>
                      <div className="font-semibold">{row.baseSymbol}</div>
                      <div className="text-xs text-slate-400">{coin?.recommendation ?? '—'}</div>
                    </div>
                    <div className="text-right text-sm text-emerald-300">{coin?.amount ?? '—'}</div>
                  </div>
                );
              })}
            </div>
          </SectionCard>
        </div>
      ) : null}

      {activeTab === 'resources' ? (
        <SectionCard title="Resources">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <button
                type="button"
                className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-200"
                onClick={() => void fetchResources().catch(handleError)}
              >
                Load resources
              </button>
            <label className="text-xs">
              Sort by:{' '}
              <select
                className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
                value={resourceSort}
                onChange={(event) => setResourceSort(event.target.value as typeof resourceSort)}
              >
                <option value="value">Value</option>
                <option value="amount">Amount</option>
                <option value="symbol">Symbol</option>
              </select>
            </label>
          </div>
          <div className="mt-3 divide-y divide-slate-800 text-sm">
            {sortedResources.map((resource) => (
              <div key={resource.symbol} className="flex items-center justify-between py-2">
                <div>
                  <div className="font-semibold">{resource.symbol}</div>
                  <div className="text-xs text-slate-400">Amount: {resource.amount}</div>
                </div>
                <div className="text-right text-emerald-300">
                  {resource.value ? resource.value.toFixed(2) : '—'} COIN
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {activeTab === 'wallets' ? (
        <SectionCard title="Wallets">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <button
                type="button"
                className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-200"
                onClick={() => void fetchWallets().catch(handleError)}
              >
                Load wallets
              </button>
          </div>
          <div className="mt-3 space-y-3 text-sm">
            {wallets.map((wallet) => (
              <div key={wallet.address} className="rounded border border-slate-800 p-3">
                <div className="flex items-center justify-between">
                  <div className="font-semibold">{formatAddress(wallet.address)}</div>
                  {wallet.primary ? <span className="text-xs text-emerald-300">Primary</span> : null}
                </div>
                <div className="text-xs text-slate-400">
                  {wallet.type ?? '—'} · {wallet.provider ?? '—'} {wallet.providerId ? `· ${wallet.providerId}` : ''}
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <CopyButton value={wallet.address} label="Copy" />
                  <button
                    type="button"
                    className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-200"
                    onClick={() => setSelectedDeputyWallet(wallet.address)}
                  >
                    Use for deputy
                  </button>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {activeTab === 'deputy' ? (
        <SectionCard title="Deputy Wallet">
          <div className="space-y-2 text-sm">
            <label className="text-xs text-slate-400">Wallet address</label>
            <input
              value={selectedDeputyWallet}
              onChange={(event) => setSelectedDeputyWallet(event.target.value)}
              placeholder="0x..."
              className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
            />
            <button
              type="button"
              className="rounded bg-emerald-500 px-3 py-2 text-sm font-semibold text-slate-950"
              onClick={() => void fetchDeputy().catch(handleError)}
            >
              Lookup deputy
            </button>
            {deputyResult ? (
              <div className="rounded border border-slate-800 p-3 text-sm">
                <div className="text-xs text-slate-400">Deputy wallet address</div>
                <div className="mt-1 flex items-center gap-2">
                  <span>{deputyResult}</span>
                  <CopyButton value={deputyResult} />
                </div>
              </div>
            ) : null}
          </div>
        </SectionCard>
      ) : null}

      {activeTab === 'workshop' ? (
        <SectionCard title="Workshop">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <button
                type="button"
                className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-200"
                onClick={() => void fetchWorkshop().catch(handleError)}
              >
                Load workshop
              </button>
            <span>Cached in local storage for player profile.</span>
          </div>
          <div className="mt-3 divide-y divide-slate-800 text-sm">
            {workshop.map((item) => (
              <div key={item.symbol} className="flex items-center justify-between py-2">
                <div className="font-semibold">{item.symbol}</div>
                <div className="text-emerald-300">Level {item.level}</div>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {activeTab === 'mastery' ? (
        <SectionCard title="Mastery (Proficiencies)">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <button
                type="button"
                className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-200"
                onClick={() => void fetchProficiencies().catch(handleError)}
              >
                Load proficiencies
              </button>
          </div>
          <div className="mt-3 space-y-3 text-sm">
            {proficiencies.map((item) => (
              <div key={item.symbol} className="rounded border border-slate-800 p-3">
                <div className="flex items-center justify-between">
                  <div className="font-semibold">{item.symbol}</div>
                  <div className="text-emerald-300">Level {item.claimedLevel}</div>
                </div>
                <div className="text-xs text-slate-400">Collected: {item.collectedAmount}</div>
                <button
                  type="button"
                  className="mt-2 rounded border border-slate-700 px-2 py-1 text-xs text-slate-200"
                  onClick={() => {
                    setLeaderboardSymbol(item.symbol);
                    setActiveTab('leaderboards');
                  }}
                >
                  View leaderboard
                </button>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {activeTab === 'leaderboards' ? (
        <SectionCard title="Leaderboards">
          <div className="space-y-2 text-sm">
            <label className="text-xs text-slate-400">Symbol</label>
            <input
              value={leaderboardSymbol}
              onChange={(event) => setLeaderboardSymbol(event.target.value.toUpperCase())}
              placeholder="WOOD"
              className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
            />
            <button
              type="button"
              className="rounded bg-emerald-500 px-3 py-2 text-sm font-semibold text-slate-950"
              onClick={() => void fetchLeaderboard(leaderboardSymbol, false).catch(handleError)}
            >
              Load leaderboard
            </button>
            <div className="text-xs text-slate-400">
              Cached for 60s per symbol. Last fetched:{' '}
              {leaderboardFetchedAt ? new Date(leaderboardFetchedAt).toLocaleTimeString() : '—'}
            </div>
          </div>
          {leaderboardData?.entryByUserId ? (
            <div className="mt-4 rounded border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm">
              <div className="text-xs text-emerald-200">Your position</div>
              <div className="mt-1 flex items-center justify-between">
                <span>#{leaderboardData.entryByUserId.position}</span>
                <span>{leaderboardData.entryByUserId.collectedAmount}</span>
              </div>
            </div>
          ) : null}
          <div className="mt-4 space-y-3">
            {leaderboardData?.leaderboard?.map((entry) => (
              <div key={`${entry.profile.uid}-${entry.position}`} className="rounded border border-slate-800 p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-semibold">#{entry.position}</span>
                  <span>{entry.collectedAmount}</span>
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-slate-400">
                  {entry.profile.avatarUrl ? (
                    <img
                      src={entry.profile.avatarUrl}
                      alt={entry.profile.displayName ?? entry.profile.walletAddress ?? 'avatar'}
                      className="h-6 w-6 rounded-full"
                    />
                  ) : null}
                  <span>{entry.profile.displayName ?? formatAddress(entry.profile.walletAddress) ?? entry.profile.uid}</span>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {activeTab === 'notes' ? (
        <SectionCard title="How it works">
          <div className="space-y-2 text-sm text-slate-300">
            <p>
              <strong>Auth steps:</strong> connect wallet → sign message → loginForCustomToken → exchange custom token →
              Firebase idToken → Craft World GraphQL calls with Bearer jwt_&lt;idToken&gt;.
            </p>
            <p>
              <strong>Stored locally:</strong> wallet address, Firebase idToken, refreshToken (if available), expiresAt, and
              Firebase localId. Tokens are not printed in the UI.
            </p>
            <p>
              <strong>Logout:</strong> clears local storage keys and resets session state.
            </p>
            <p>
              <strong>Common failures:</strong> WalletConnect missing project ID, signature rejected, account lookup fails, or
              expired token requiring re-login.
            </p>
            <p>
              <strong>iPhone Safari:</strong> use WalletConnect (no injected provider), so ensure WalletConnect project ID is
              configured.
            </p>
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
};

export default function CWApp() {
  return (
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={queryClient}>
        <CWAppShell />
      </QueryClientProvider>
    </WagmiProvider>
  );
}
