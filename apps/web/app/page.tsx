'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  buildLoginMessage,
  clearAuthState,
  computeExpiresAt,
  loadAuthState,
  persistAuthState,
  playerProfileKey,
  redactTokens,
  shortenAddress
} from '../lib/cwAuth';
import {
  cwApiRequest,
  cwGraphqlRequest,
  ensureFreshToken,
  exchangeCustomToken,
  loginForCustomToken,
  lookupAccountInfo
} from '../lib/cwClient';
import { CW_QUERIES } from '../lib/cwQueries';
import { ConnectedWallet, connectInjectedWallet, connectWalletConnect, signMessage } from '../lib/wallet';

type PriceRow = {
  referenceSymbol: string;
  amount: number;
  recommendation: string;
};

type ResourceRow = {
  symbol: string;
  amount: number;
};

type WalletRow = {
  address: string;
  type?: string | null;
  provider?: string | null;
  providerId?: string | null;
  primary?: boolean | null;
};

type WorkshopRow = {
  symbol: string;
  level: number;
};

type ProficiencyRow = {
  symbol: string;
  collectedAmount: number;
  claimedLevel: number;
};

type LeaderboardEntry = {
  position: number;
  collectedAmount: number;
  profile: {
    uid: string;
    walletAddress: string;
    avatarUrl?: string | null;
    displayName?: string | null;
  };
};

type LeaderboardResponse = {
  leaderboard: LeaderboardEntry[];
  entryByUserId?: LeaderboardEntry | null;
};

type TabId =
  | 'home'
  | 'calls'
  | 'prices'
  | 'resources'
  | 'wallets'
  | 'deputy'
  | 'workshop'
  | 'mastery'
  | 'leaderboards'
  | 'notes';

const tabs: Array<{ id: TabId; label: string }> = [
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

const callCatalog = [
  {
    id: 'loginForCustomToken',
    name: 'loginForCustomToken',
    requiresAuth: false,
    variables: '{ signature, walletAddress }'
  },
  {
    id: 'exchangeCustomToken',
    name: 'signInWithCustomToken',
    requiresAuth: false,
    variables: '{ token } (custom token)'
  },
  {
    id: 'accountLookup',
    name: 'accounts:lookup',
    requiresAuth: true,
    variables: '{ idToken }'
  },
  {
    id: 'getWallets',
    name: 'getWallets',
    requiresAuth: true,
    variables: '{}'
  },
  {
    id: 'exchangePriceList',
    name: 'exchangePriceList',
    requiresAuth: false,
    variables: '{}'
  },
  {
    id: 'resources',
    name: 'account.resources',
    requiresAuth: true,
    variables: '{}'
  },
  {
    id: 'deputyWalletAddress',
    name: 'deputyWalletAddress',
    requiresAuth: true,
    variables: '{ walletAddress }'
  },
  {
    id: 'workshop',
    name: 'account.workshop',
    requiresAuth: true,
    variables: '{}'
  },
  {
    id: 'proficiencies',
    name: 'account.proficiencies',
    requiresAuth: true,
    variables: '{}'
  },
  {
    id: 'proficiencyLeaderboard',
    name: 'proficiencyLeaderboard',
    requiresAuth: true,
    variables: '{ symbol, userId }'
  },
  {
    id: 'verifiedToken',
    name: 'verifiedToken (optional)',
    requiresAuth: false,
    variables: 'Not implemented in this repo.'
  },
  {
    id: 'linkedAccounts',
    name: 'linkedAccounts / wallets (optional)',
    requiresAuth: false,
    variables: 'Not implemented in this repo.'
  }
] as const;

const copyToClipboard = async (value: string, onDone?: () => void) => {
  if (!value) return;
  await navigator.clipboard.writeText(value);
  onDone?.();
};

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<TabId>('home');
  const [auth, setAuth] = useState(loadAuthState);
  const [walletConnection, setWalletConnection] = useState<ConnectedWallet | null>(null);
  const [prices, setPrices] = useState<PriceRow[]>([]);
  const [pricesUpdatedAt, setPricesUpdatedAt] = useState<string>('—');
  const [priceSearch, setPriceSearch] = useState('');
  const [resources, setResources] = useState<ResourceRow[]>([]);
  const [wallets, setWallets] = useState<WalletRow[]>([]);
  const [workshop, setWorkshop] = useState<WorkshopRow[]>([]);
  const [proficiencies, setProficiencies] = useState<ProficiencyRow[]>([]);
  const [resourceSort, setResourceSort] = useState<'value' | 'amount' | 'symbol'>('value');
  const [callResults, setCallResults] = useState<Record<string, unknown>>({});
  const [callErrors, setCallErrors] = useState<Record<string, string>>({});
  const [loadingCalls, setLoadingCalls] = useState<Record<string, boolean>>({});
  const [loginNonce, setLoginNonce] = useState<string | null>(null);
  const [deputyInput, setDeputyInput] = useState('');
  const [deputyResult, setDeputyResult] = useState<string>('');
  const [leaderboardSymbol, setLeaderboardSymbol] = useState('');
  const [leaderboardData, setLeaderboardData] = useState<LeaderboardResponse | null>(null);
  const [leaderboardStatus, setLeaderboardStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const leaderboardCache = useRef<Record<string, { data: LeaderboardResponse; fetchedAt: number }>>({});

  useEffect(() => {
    setAuth(loadAuthState());
  }, []);

  useEffect(() => {
    if (wallets.length && !deputyInput) {
      const primary = wallets.find((wallet) => wallet.primary);
      if (primary?.address) {
        setDeputyInput(primary.address);
      }
    }
  }, [wallets, deputyInput]);

  const refreshAuthState = useCallback(async () => {
    try {
      const updated = await ensureFreshToken(auth);
      setAuth((prev) => ({
        ...prev,
        ...updated,
        status: updated.idToken ? 'authenticated' : prev.status,
        error: undefined
      }));
      return updated;
    } catch (error) {
      setAuth((prev) => ({
        ...prev,
        status: 'error',
        error: error instanceof Error ? error.message : 'Authentication refresh failed.'
      }));
      throw error;
    }
  }, [auth]);

  const handleConnect = useCallback(async () => {
    setAuth((prev) => ({ ...prev, status: 'connecting', error: undefined }));
    try {
      const injected = await connectInjectedWallet();
      const connected = injected ?? (await connectWalletConnect());
      if (connected.provider.on) {
        connected.provider.on('disconnect', () => {
          setWalletConnection(null);
          setAuth({ status: 'disconnected' });
          clearAuthState();
        });
      }
      setWalletConnection(connected);
      setAuth((prev) => {
        const next = { ...prev, status: 'connected', walletAddress: connected.address, error: undefined };
        persistAuthState(next);
        return next;
      });
    } catch (error) {
      setAuth((prev) => ({
        ...prev,
        status: 'error',
        error: error instanceof Error ? error.message : 'Failed to connect wallet.'
      }));
    }
  }, []);

  const handleDisconnect = useCallback(async () => {
    if (walletConnection?.type === 'walletconnect') {
      await walletConnection.provider.disconnect?.();
    }
    setWalletConnection(null);
    setAuth({ status: 'disconnected' });
    clearAuthState();
  }, [walletConnection]);

  const handleLogin = useCallback(async () => {
    if (!walletConnection?.address) {
      setAuth((prev) => ({ ...prev, status: 'error', error: 'Connect a wallet first.' }));
      return;
    }
    setAuth((prev) => ({ ...prev, status: 'logging_in', error: undefined }));
    try {
      const nonce = crypto.randomUUID();
      setLoginNonce(nonce);
      const issuedAt = new Date().toISOString();
      const message = buildLoginMessage(walletConnection.address, nonce, issuedAt);
      const signature = await signMessage(walletConnection, message);
      const customToken = await loginForCustomToken(signature, walletConnection.address);
      const firebaseResponse = await exchangeCustomToken(customToken);
      const expiresAt = computeExpiresAt(Number(firebaseResponse.expiresIn));
      const accountInfo = await lookupAccountInfo(firebaseResponse.idToken);
      const localId = accountInfo.users?.[0]?.localId;
      const next = {
        status: 'authenticated' as const,
        walletAddress: walletConnection.address,
        idToken: firebaseResponse.idToken,
        refreshToken: firebaseResponse.refreshToken,
        expiresAt,
        localId,
        error: undefined
      };
      setAuth(next);
      persistAuthState(next);
      await refreshAllData(next);
      setLoginNonce(null);
    } catch (error) {
      setAuth((prev) => ({
        ...prev,
        status: 'error',
        error: error instanceof Error ? error.message : 'Login failed.'
      }));
      setLoginNonce(null);
    }
  }, [walletConnection]);

  const handleLogout = useCallback(() => {
    clearAuthState();
    setAuth({ status: 'disconnected' });
  }, []);

  const refreshPrices = useCallback(
    async (idToken?: string) => {
      const response = await cwGraphqlRequest<{ data?: { exchangePriceList?: PriceRow[] } }>({
        operationName: CW_QUERIES.exchangePriceList.operationName,
        query: CW_QUERIES.exchangePriceList.query,
        idToken
      });
      const next = response.data?.exchangePriceList ?? [];
      setPrices(next);
      setPricesUpdatedAt(new Date().toLocaleString());
    },
    [setPrices]
  );

  const refreshResources = useCallback(
    async (stateOverride?: typeof auth) => {
      const response = await cwApiRequest<{ data?: { account?: { resources?: ResourceRow[] } } }>({
        state: stateOverride ?? auth,
        onAuthUpdate: (next) => setAuth((prev) => ({ ...prev, ...next, status: 'authenticated' })),
        operationName: CW_QUERIES.accountResources.operationName,
        query: CW_QUERIES.accountResources.query
      });
      setResources(response.data?.account?.resources ?? []);
    },
    [auth]
  );

  const refreshWallets = useCallback(
    async (stateOverride?: typeof auth) => {
      const response = await cwApiRequest<{ data?: { account?: { wallets?: WalletRow[] } } }>({
        state: stateOverride ?? auth,
        onAuthUpdate: (next) => setAuth((prev) => ({ ...prev, ...next, status: 'authenticated' })),
        operationName: CW_QUERIES.accountWallets.operationName,
        query: CW_QUERIES.accountWallets.query
      });
      setWallets(response.data?.account?.wallets ?? []);
    },
    [auth]
  );

  const refreshWorkshop = useCallback(
    async (stateOverride?: typeof auth) => {
      const response = await cwApiRequest<{ data?: { account?: { workshop?: WorkshopRow[] } } }>({
        state: stateOverride ?? auth,
        onAuthUpdate: (next) => setAuth((prev) => ({ ...prev, ...next, status: 'authenticated' })),
        operationName: CW_QUERIES.accountWorkshop.operationName,
        query: CW_QUERIES.accountWorkshop.query
      });
      const rows = response.data?.account?.workshop ?? [];
      setWorkshop(rows);
      if (typeof window !== 'undefined') {
        const profile = { workshop: rows, updatedAt: Date.now() };
        window.localStorage.setItem(playerProfileKey, JSON.stringify(profile));
      }
    },
    [auth]
  );

  const refreshProficiencies = useCallback(
    async (stateOverride?: typeof auth) => {
      const response = await cwApiRequest<{ data?: { account?: { proficiencies?: ProficiencyRow[] } } }>({
        state: stateOverride ?? auth,
        onAuthUpdate: (next) => setAuth((prev) => ({ ...prev, ...next, status: 'authenticated' })),
        operationName: CW_QUERIES.accountProficiencies.operationName,
        query: CW_QUERIES.accountProficiencies.query
      });
      setProficiencies(response.data?.account?.proficiencies ?? []);
    },
    [auth]
  );

  const refreshAllData = useCallback(
    async (stateOverride?: typeof auth) => {
      const token = stateOverride?.idToken ?? auth.idToken;
      await refreshPrices(token);
      if (token) {
        if (!stateOverride) {
          await refreshAuthState();
        }
        const state = stateOverride ?? auth;
        await Promise.all([
          refreshResources(state),
          refreshWallets(state),
          refreshWorkshop(state),
          refreshProficiencies(state)
        ]);
      }
    },
    [
      auth.idToken,
      refreshPrices,
      refreshResources,
      refreshWallets,
      refreshWorkshop,
      refreshProficiencies,
      refreshAuthState
    ]
  );

  useEffect(() => {
    if (auth.status === 'authenticated' && auth.idToken) {
      refreshAllData(auth).catch(() => null);
    }
  }, [auth, refreshAllData]);

  const runCall = useCallback(
    async (callId: string) => {
      setLoadingCalls((prev) => ({ ...prev, [callId]: true }));
      setCallErrors((prev) => ({ ...prev, [callId]: '' }));
      try {
        let result: unknown = null;
        if (callId === 'loginForCustomToken') {
          if (!walletConnection?.address) {
            throw new Error('Connect wallet to sign login message.');
          }
          const nonce = crypto.randomUUID();
          setLoginNonce(nonce);
          const issuedAt = new Date().toISOString();
          const message = buildLoginMessage(walletConnection.address, nonce, issuedAt);
          const signature = await signMessage(walletConnection, message);
          const customToken = await loginForCustomToken(signature, walletConnection.address);
          result = { customToken };
        } else if (callId === 'exchangeCustomToken') {
          if (!walletConnection?.address) {
            throw new Error('Connect wallet to sign login message.');
          }
          const nonce = crypto.randomUUID();
          setLoginNonce(nonce);
          const issuedAt = new Date().toISOString();
          const message = buildLoginMessage(walletConnection.address, nonce, issuedAt);
          const signature = await signMessage(walletConnection, message);
          const customToken = await loginForCustomToken(signature, walletConnection.address);
          const firebaseResponse = await exchangeCustomToken(customToken);
          result = firebaseResponse;
        } else if (callId === 'accountLookup') {
          const fresh = await refreshAuthState();
          result = await lookupAccountInfo(fresh.idToken as string);
        } else if (callId === 'getWallets') {
          result = await cwApiRequest({
            state: auth,
            onAuthUpdate: (next) => setAuth((prev) => ({ ...prev, ...next, status: 'authenticated' })),
            operationName: CW_QUERIES.accountWallets.operationName,
            query: CW_QUERIES.accountWallets.query
          });
        } else if (callId === 'exchangePriceList') {
          result = await cwGraphqlRequest({
            operationName: CW_QUERIES.exchangePriceList.operationName,
            query: CW_QUERIES.exchangePriceList.query
          });
        } else if (callId === 'resources') {
          result = await cwApiRequest({
            state: auth,
            onAuthUpdate: (next) => setAuth((prev) => ({ ...prev, ...next, status: 'authenticated' })),
            operationName: CW_QUERIES.accountResources.operationName,
            query: CW_QUERIES.accountResources.query
          });
        } else if (callId === 'deputyWalletAddress') {
          result = await cwApiRequest({
            state: auth,
            onAuthUpdate: (next) => setAuth((prev) => ({ ...prev, ...next, status: 'authenticated' })),
            operationName: CW_QUERIES.deputyWalletAddress.operationName,
            query: CW_QUERIES.deputyWalletAddress.query,
            variables: { walletAddress: deputyInput || auth.walletAddress }
          });
        } else if (callId === 'workshop') {
          result = await cwApiRequest({
            state: auth,
            onAuthUpdate: (next) => setAuth((prev) => ({ ...prev, ...next, status: 'authenticated' })),
            operationName: CW_QUERIES.accountWorkshop.operationName,
            query: CW_QUERIES.accountWorkshop.query
          });
        } else if (callId === 'proficiencies') {
          result = await cwApiRequest({
            state: auth,
            onAuthUpdate: (next) => setAuth((prev) => ({ ...prev, ...next, status: 'authenticated' })),
            operationName: CW_QUERIES.accountProficiencies.operationName,
            query: CW_QUERIES.accountProficiencies.query
          });
        } else if (callId === 'proficiencyLeaderboard') {
          if (!leaderboardSymbol) {
            throw new Error('Provide a symbol for leaderboard.');
          }
          if (!auth.localId) {
            throw new Error('localId missing. Run account lookup or login again.');
          }
          result = await cwApiRequest({
            state: auth,
            onAuthUpdate: (next) => setAuth((prev) => ({ ...prev, ...next, status: 'authenticated' })),
            operationName: CW_QUERIES.proficiencyLeaderboard.operationName,
            query: CW_QUERIES.proficiencyLeaderboard.query,
            variables: { symbol: leaderboardSymbol, userId: auth.localId }
          });
        } else {
          result = { note: 'Not implemented in this repo.' };
        }
        setCallResults((prev) => ({ ...prev, [callId]: redactTokens(result) }));
      } catch (error) {
        setCallErrors((prev) => ({
          ...prev,
          [callId]: error instanceof Error ? error.message : 'Call failed.'
        }));
      } finally {
        setLoginNonce(null);
        setLoadingCalls((prev) => ({ ...prev, [callId]: false }));
      }
    },
    [walletConnection, refreshAuthState, deputyInput, auth, leaderboardSymbol]
  );

  const priceLookup = useMemo(() => {
    const lookup = new Map<string, number>();
    for (const row of prices) {
      lookup.set(row.referenceSymbol, row.amount);
    }
    return lookup;
  }, [prices]);

  const filteredPrices = useMemo(() => {
    const query = priceSearch.trim().toLowerCase();
    if (!query) return prices;
    return prices.filter((row) => row.referenceSymbol.toLowerCase().includes(query));
  }, [prices, priceSearch]);

  const resourceRows = useMemo(() => {
    const rows = resources.map((row) => {
      const price = priceLookup.get(row.symbol) ?? 0;
      return { ...row, price, value: price * row.amount };
    });
    if (resourceSort === 'symbol') {
      return rows.sort((a, b) => a.symbol.localeCompare(b.symbol));
    }
    if (resourceSort === 'amount') {
      return rows.sort((a, b) => b.amount - a.amount);
    }
    return rows.sort((a, b) => b.value - a.value);
  }, [resources, priceLookup, resourceSort]);

  const sessionExpiresIn = useMemo(() => {
    if (!auth.expiresAt) return '—';
    const remainingMs = auth.expiresAt - Date.now();
    if (remainingMs <= 0) return 'Expired';
    const minutes = Math.floor(remainingMs / 60000);
    const seconds = Math.floor((remainingMs % 60000) / 1000);
    return `${minutes}m ${seconds}s`;
  }, [auth.expiresAt]);

  const handleDeputyLookup = useCallback(async () => {
    if (!deputyInput) {
      setDeputyResult('');
      return;
    }
    try {
      const response = await cwApiRequest<{ data?: { deputyWalletAddress?: string } }>({
        state: auth,
        onAuthUpdate: (next) => setAuth((prev) => ({ ...prev, ...next, status: 'authenticated' })),
        operationName: CW_QUERIES.deputyWalletAddress.operationName,
        query: CW_QUERIES.deputyWalletAddress.query,
        variables: { walletAddress: deputyInput }
      });
      const next = response.data?.deputyWalletAddress ?? 'Not found';
      setDeputyResult(next);
    } catch (error) {
      setDeputyResult(error instanceof Error ? error.message : 'Lookup failed');
    }
  }, [deputyInput, auth]);

  const fetchLeaderboard = useCallback(async () => {
    if (!leaderboardSymbol) {
      setLeaderboardStatus('error');
      return;
    }
    const cacheKey = `${leaderboardSymbol}:${auth.localId}`;
    const cached = leaderboardCache.current[cacheKey];
    if (cached && Date.now() - cached.fetchedAt < 60_000) {
      setLeaderboardData(cached.data);
      setLeaderboardStatus('idle');
      return;
    }
    try {
      setLeaderboardStatus('loading');
      if (!auth.localId) {
        throw new Error('localId missing');
      }
      const response = await cwApiRequest<{ data?: { proficiencyLeaderboard?: LeaderboardResponse } }>({
        state: auth,
        onAuthUpdate: (next) => setAuth((prev) => ({ ...prev, ...next, status: 'authenticated' })),
        operationName: CW_QUERIES.proficiencyLeaderboard.operationName,
        query: CW_QUERIES.proficiencyLeaderboard.query,
        variables: { symbol: leaderboardSymbol, userId: auth.localId }
      });
      const data = response.data?.proficiencyLeaderboard ?? { leaderboard: [] };
      leaderboardCache.current[cacheKey] = { data, fetchedAt: Date.now() };
      setLeaderboardData(data);
      setLeaderboardStatus('idle');
    } catch (error) {
      setLeaderboardStatus('error');
    }
  }, [leaderboardSymbol, auth]);

  const onLeaderboardSymbol = useCallback((symbol: string) => {
    setLeaderboardSymbol(symbol);
    setActiveTab('leaderboards');
  }, []);

  const statusLabel = useMemo(() => {
    if (auth.status === 'authenticated') return 'Logged in';
    if (auth.status === 'connected') return 'Wallet connected';
    if (auth.status === 'connecting') return 'Connecting';
    if (auth.status === 'logging_in') return 'Signing in';
    if (auth.status === 'error') return 'Error';
    return 'Disconnected';
  }, [auth.status]);

  return (
    <section className="space-y-6">
      <div className="rounded border border-slate-800 bg-slate-900 p-4">
        <h1 className="text-2xl font-semibold">Craft World Wallet Console</h1>
        <p className="text-slate-300">Connect, sign, and explore Craft World APIs with a mobile-first tabbed UI.</p>
      </div>

      <div className="rounded border border-slate-800 bg-slate-950/40 p-2">
        <div className="flex gap-2 overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`whitespace-nowrap rounded px-3 py-2 text-sm font-semibold transition ${
                activeTab === tab.id
                  ? 'bg-cyan-500/20 text-cyan-100'
                  : 'bg-slate-900 text-slate-300 hover:bg-slate-800'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === 'home' ? (
        <div className="space-y-4">
          <div className="rounded border border-slate-800 bg-slate-900 p-4">
            <h2 className="text-lg font-semibold">Status</h2>
            <div className="mt-2 grid gap-2 text-sm text-slate-300">
              <div>
                <span className="text-slate-400">Wallet:</span> {shortenAddress(auth.walletAddress)}
              </div>
              <div>
                <span className="text-slate-400">Session:</span> {statusLabel}
              </div>
              <div>
                <span className="text-slate-400">Expires In:</span> {sessionExpiresIn}
              </div>
              <div>
                <span className="text-slate-400">Local ID:</span> {auth.localId ?? '—'}
              </div>
              {auth.error ? <div className="text-amber-300">{auth.error}</div> : null}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleConnect}
              className="rounded bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-400"
            >
              Connect Wallet
            </button>
            <button
              type="button"
              onClick={handleDisconnect}
              className="rounded bg-slate-700 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-600"
            >
              Disconnect
            </button>
            <button
              type="button"
              onClick={handleLogin}
              className="rounded bg-cyan-500 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-400"
            >
              Login
            </button>
            <button
              type="button"
              onClick={handleLogout}
              className="rounded bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-400"
            >
              Logout
            </button>
            <button
              type="button"
              onClick={() => refreshAllData().catch(() => null)}
              className="rounded bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-200 hover:bg-slate-700"
            >
              Refresh data
            </button>
          </div>
        </div>
      ) : null}

      {activeTab === 'calls' ? (
        <div className="space-y-4">
          <div className="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
            Do not share outputs containing tokens.
          </div>
          <div className="space-y-4">
            {callCatalog.map((call) => (
              <div key={call.id} className="rounded border border-slate-800 bg-slate-900 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 className="text-base font-semibold text-white">{call.name}</h3>
                    <p className="text-xs text-slate-400">Variables: {call.variables}</p>
                    <p className="text-xs text-slate-500">Auth required: {call.requiresAuth ? 'Yes' : 'No'}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => runCall(call.id)}
                    className="rounded bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-700"
                    disabled={loadingCalls[call.id]}
                  >
                    {loadingCalls[call.id] ? 'Running...' : 'Run'}
                  </button>
                </div>
                {callErrors[call.id] ? (
                  <p className="mt-2 text-xs text-rose-300">{callErrors[call.id]}</p>
                ) : null}
                {callResults[call.id] ? (
                  <pre className="mt-3 max-h-64 overflow-auto rounded bg-slate-950/60 p-3 text-xs text-slate-200">
                    {JSON.stringify(callResults[call.id], null, 2)}
                  </pre>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {activeTab === 'prices' ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold">Exchange Price List</h2>
              <p className="text-xs text-slate-400">Last updated: {pricesUpdatedAt}</p>
            </div>
            <button
              type="button"
              onClick={() => refreshPrices(auth.idToken).catch(() => null)}
              className="rounded bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-700"
            >
              Refresh
            </button>
          </div>
          <input
            value={priceSearch}
            onChange={(event) => setPriceSearch(event.target.value)}
            placeholder="Search symbol"
            className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200"
          />
          <div className="overflow-auto rounded border border-slate-800">
            <table className="min-w-full text-left text-sm text-slate-200">
              <thead className="bg-slate-900 text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-3 py-2">Reference</th>
                  <th className="px-3 py-2">Amount</th>
                  <th className="px-3 py-2">Recommendation</th>
                </tr>
              </thead>
              <tbody>
                {filteredPrices.map((row) => (
                  <tr key={`${row.referenceSymbol}-${row.amount}`} className="border-t border-slate-800">
                    <td className="px-3 py-2 font-semibold">{row.referenceSymbol}</td>
                    <td className="px-3 py-2">{row.amount}</td>
                    <td className="px-3 py-2 text-slate-300">{row.recommendation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {activeTab === 'resources' ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold">Resources</h2>
              <p className="text-xs text-slate-400">Estimated COIN value uses exchangePriceList.</p>
            </div>
            <select
              value={resourceSort}
              onChange={(event) => setResourceSort(event.target.value as typeof resourceSort)}
              className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200"
            >
              <option value="value">Sort by value</option>
              <option value="amount">Sort by amount</option>
              <option value="symbol">Sort by symbol</option>
            </select>
          </div>
          <div className="overflow-auto rounded border border-slate-800">
            <table className="min-w-full text-left text-sm text-slate-200">
              <thead className="bg-slate-900 text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-3 py-2">Symbol</th>
                  <th className="px-3 py-2">Amount</th>
                  <th className="px-3 py-2">COIN Value</th>
                </tr>
              </thead>
              <tbody>
                {resourceRows.map((row) => (
                  <tr key={row.symbol} className="border-t border-slate-800">
                    <td className="px-3 py-2 font-semibold">{row.symbol}</td>
                    <td className="px-3 py-2">{row.amount}</td>
                    <td className="px-3 py-2">{row.value.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {activeTab === 'wallets' ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Wallets</h2>
            <button
              type="button"
              onClick={() => (auth.idToken ? refreshWallets().catch(() => null) : null)}
              className="rounded bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-700"
            >
              Refresh
            </button>
          </div>
          <div className="space-y-3">
            {wallets.map((wallet) => (
              <div
                key={wallet.address}
                className={`rounded border p-3 ${
                  wallet.primary ? 'border-emerald-500/60 bg-emerald-500/10' : 'border-slate-800 bg-slate-900'
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-slate-100">{wallet.address}</div>
                    <div className="text-xs text-slate-400">
                      {wallet.type ?? 'unknown'} • {wallet.provider ?? 'provider'}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setDeputyInput(wallet.address)}
                    className="rounded bg-slate-800 px-3 py-1 text-xs text-slate-100 hover:bg-slate-700"
                  >
                    Use for deputy
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {activeTab === 'deputy' ? (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Deputy Wallet Address</h2>
          <div className="space-y-2">
            <input
              value={deputyInput}
              onChange={(event) => setDeputyInput(event.target.value)}
              placeholder="Wallet address"
              className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200"
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={handleDeputyLookup}
                className="rounded bg-cyan-500 px-3 py-2 text-xs font-semibold text-white hover:bg-cyan-400"
              >
                Lookup
              </button>
              <button
                type="button"
                onClick={() => copyToClipboard(deputyResult)}
                className="rounded bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-700"
              >
                Copy
              </button>
            </div>
            <div className="rounded border border-slate-800 bg-slate-900 p-3 text-sm text-slate-200">
              {deputyResult || '—'}
            </div>
          </div>
        </div>
      ) : null}

      {activeTab === 'workshop' ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Workshop Levels</h2>
            <button
              type="button"
              onClick={() => (auth.idToken ? refreshWorkshop().catch(() => null) : null)}
              className="rounded bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-700"
            >
              Refresh
            </button>
          </div>
          <div className="grid gap-2">
            {workshop
              .slice()
              .sort((a, b) => b.level - a.level || a.symbol.localeCompare(b.symbol))
              .map((row) => (
                <div key={row.symbol} className="rounded border border-slate-800 bg-slate-900 p-3">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-100">{row.symbol}</span>
                    <span className="text-sm text-slate-300">Level {row.level}</span>
                  </div>
                </div>
              ))}
          </div>
        </div>
      ) : null}

      {activeTab === 'mastery' ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Mastery</h2>
            <button
              type="button"
              onClick={() => (auth.idToken ? refreshProficiencies().catch(() => null) : null)}
              className="rounded bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-700"
            >
              Refresh
            </button>
          </div>
          <div className="space-y-2">
            {proficiencies.map((row) => (
              <div key={row.symbol} className="rounded border border-slate-800 bg-slate-900 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-100">{row.symbol}</div>
                    <div className="text-xs text-slate-400">Collected: {row.collectedAmount}</div>
                    <div className="text-xs text-slate-400">Claimed Level: {row.claimedLevel}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onLeaderboardSymbol(row.symbol)}
                    className="rounded bg-cyan-500 px-3 py-2 text-xs font-semibold text-white hover:bg-cyan-400"
                  >
                    Leaderboard
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {activeTab === 'leaderboards' ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={leaderboardSymbol}
              onChange={(event) => setLeaderboardSymbol(event.target.value)}
              placeholder="Symbol (e.g. MUD)"
              className="flex-1 rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200"
            />
            <button
              type="button"
              onClick={fetchLeaderboard}
              className="rounded bg-cyan-500 px-3 py-2 text-xs font-semibold text-white hover:bg-cyan-400"
            >
              Fetch
            </button>
          </div>
          {leaderboardData?.entryByUserId ? (
            <div className="sticky top-0 rounded border border-cyan-500/50 bg-cyan-500/10 p-3 text-sm text-cyan-100">
              <div className="font-semibold">Your Position</div>
              <div>#{leaderboardData.entryByUserId.position}</div>
              <div>Collected: {leaderboardData.entryByUserId.collectedAmount}</div>
            </div>
          ) : null}
          {leaderboardStatus === 'loading' ? <p className="text-sm text-slate-300">Loading...</p> : null}
          {leaderboardStatus === 'error' ? (
            <p className="text-sm text-rose-300">Failed to load leaderboard.</p>
          ) : null}
          <div className="space-y-2">
            {leaderboardData?.leaderboard?.map((entry) => (
              <div key={`${entry.profile.uid}-${entry.position}`} className="rounded border border-slate-800 bg-slate-900 p-3">
                <div className="flex items-center gap-3">
                  {entry.profile.avatarUrl ? (
                    <img
                      src={entry.profile.avatarUrl}
                      alt={entry.profile.displayName || entry.profile.walletAddress}
                      className="h-10 w-10 rounded-full object-cover"
                    />
                  ) : (
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-800 text-xs text-slate-400">
                      N/A
                    </div>
                  )}
                  <div>
                    <div className="text-sm font-semibold text-slate-100">
                      #{entry.position} {entry.profile.displayName || shortenAddress(entry.profile.walletAddress)}
                    </div>
                    <div className="text-xs text-slate-400">Collected: {entry.collectedAmount}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {activeTab === 'notes' ? (
        <div className="space-y-4 rounded border border-slate-800 bg-slate-900 p-4 text-sm text-slate-200">
          <h2 className="text-lg font-semibold">How it works</h2>
          <ul className="list-disc space-y-2 pl-5 text-slate-300">
            <li>Connect wallet (injected or WalletConnect), then sign the Craft World login message.</li>
            <li>The signature is exchanged for a Firebase custom token via loginForCustomToken.</li>
            <li>The custom token is exchanged for Firebase idToken/refreshToken via Identity Toolkit.</li>
            <li>All Craft World GraphQL calls use the idToken as the session credential.</li>
          </ul>
          <h3 className="mt-4 font-semibold text-slate-100">Local storage</h3>
          <ul className="list-disc space-y-2 pl-5 text-slate-300">
            <li>Stored locally: wallet address, idToken, refreshToken, expiresAt, localId.</li>
            <li>Workshop data is cached locally for the player profile view.</li>
            <li>Not stored: signatures, custom tokens, or raw login messages.</li>
          </ul>
          <h3 className="mt-4 font-semibold text-slate-100">Logout behavior</h3>
          <p className="text-slate-300">Logout clears localStorage keys and resets the session state.</p>
          <h3 className="mt-4 font-semibold text-slate-100">Common failure modes</h3>
          <ul className="list-disc space-y-2 pl-5 text-slate-300">
            <li>WalletConnect doesn’t return accounts — reconnect from the wallet app.</li>
            <li>Signature rejected — ensure the active wallet matches the connected address.</li>
            <li>Token expired — login again to refresh the session.</li>
          </ul>
          <h3 className="mt-4 font-semibold text-slate-100">iPhone Safari</h3>
          <p className="text-slate-300">iPhone Safari requires WalletConnect because injected providers are unavailable.</p>
        </div>
      ) : null}
    </section>
  );
}
