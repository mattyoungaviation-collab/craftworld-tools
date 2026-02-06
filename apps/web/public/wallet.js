(function () {
  const env = window.CW_ENV || {};
  const API_BASE = env.apiBaseUrl || '';
  const ID_TOKEN_KEY = 'cw_idToken';
  const CW_TOKEN_KEY = 'cw_token';
  const REFRESH_TOKEN_KEY = 'cw_refreshToken';
  const EXPIRES_AT_KEY = 'cw_expiresAt';
  const WALLET_KEY = 'cw_wallet';
  const CW_SESSION_INDEX_KEY = 'cw_sessions';
  const CW_ACTIVE_WALLET_KEY = 'cw_active_wallet';
  const ACCOUNT_STATUS_KEY = 'cw_account_status';
  const CONNECTION_TYPE_KEY = 'cw_connection_type';

  let statusPollInterval = null;

  function normalizeWalletAddress(addr) {
    return String(addr || '').trim().toLowerCase();
  }

  function readSessionIndex() {
    try {
      const parsed = JSON.parse(localStorage.getItem(CW_SESSION_INDEX_KEY) || '{}');
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (_) {
      return {};
    }
  }

  function writeSessionIndex(index) {
    localStorage.setItem(CW_SESSION_INDEX_KEY, JSON.stringify(index || {}));
  }

  function setActiveWallet(wallet) {
    const normalized = normalizeWalletAddress(wallet);
    if (normalized) {
      localStorage.setItem(CW_ACTIVE_WALLET_KEY, normalized);
      localStorage.setItem(WALLET_KEY, normalized);
    } else {
      localStorage.removeItem(CW_ACTIVE_WALLET_KEY);
      localStorage.removeItem(WALLET_KEY);
    }
  }

  function getActiveWallet() {
    return normalizeWalletAddress(localStorage.getItem(CW_ACTIVE_WALLET_KEY) || '');
  }

  function upsertWalletSession(wallet, payload) {
    const normalized = normalizeWalletAddress(wallet);
    if (!normalized) return;
    const sessions = readSessionIndex();
    sessions[normalized] = {
      token: String(payload.token || ''),
      expiresAt: Number(payload.expiresAt || 0),
      refreshToken: String(payload.refreshToken || ''),
      lastLoginAt: Number(payload.lastLoginAt || Date.now()),
      idToken: String(payload.idToken || ''),
    };
    writeSessionIndex(sessions);
    setActiveWallet(normalized);
  }

  function syncLegacySessionFromActiveWallet() {
    const wallet = getActiveWallet();
    const sessions = readSessionIndex();
    const entry = sessions[wallet];
    if (!wallet || !entry) {
      localStorage.removeItem(ID_TOKEN_KEY);
      localStorage.removeItem(CW_TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      localStorage.removeItem(EXPIRES_AT_KEY);
      return;
    }
    localStorage.setItem(ID_TOKEN_KEY, String(entry.idToken || ''));
    localStorage.setItem(CW_TOKEN_KEY, String(entry.token || ''));
    localStorage.setItem(REFRESH_TOKEN_KEY, String(entry.refreshToken || ''));
    localStorage.setItem(EXPIRES_AT_KEY, String(Number(entry.expiresAt || 0)));
  }

  function shortWallet(wallet) {
    if (!wallet) return '—';
    return `${wallet.slice(0, 6)}...${wallet.slice(-4)}`;
  }

  function getSession() {
    return {
      idToken: localStorage.getItem(ID_TOKEN_KEY) || '',
      cwToken: localStorage.getItem(CW_TOKEN_KEY) || '',
      refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY) || '',
      expiresAt: Number(localStorage.getItem(EXPIRES_AT_KEY) || 0),
      wallet: localStorage.getItem(WALLET_KEY) || '',
    };
  }

  function setBanner(message) {
    const banner = document.getElementById('cw-status-banner');
    const summary = document.getElementById('cw-status-summary');
    if (!banner || !summary) return;
    if (!message) {
      banner.style.display = 'none';
      summary.textContent = '';
      return;
    }
    banner.style.display = 'block';
    summary.textContent = message;
  }

  async function fetchAccountStatus() {
    syncLegacySessionFromActiveWallet();
    const token = localStorage.getItem(CW_TOKEN_KEY) || '';
    if (!token) {
      setBanner('Not connected.');
      return null;
    }
    const res = await fetch(`${API_BASE}/api/account_status`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    localStorage.setItem(ACCOUNT_STATUS_KEY, JSON.stringify(data));
    return data;
  }

  function updateAccountWidget(data) {
    const powerEl = document.getElementById('power-value');
    const refillEl = document.getElementById('refill-value');
    if (!powerEl || !refillEl) return;
    if (!data || !data.ok) {
      powerEl.textContent = '—';
      refillEl.textContent = '—';
      return;
    }
    powerEl.textContent = String(data.power ?? '—');
    refillEl.textContent = String(data.refillHMS ?? '—');
  }

  async function refreshAccountStatusOnce() {
    try {
      const data = await fetchAccountStatus();
      updateAccountWidget(data);
    } catch (_) {
      updateAccountWidget(null);
    }
  }

  function getInjectedProvider() {
    const provider = (window.ronin && (window.ronin.provider || window.ronin.ethereum)) || window.ethereum || null;
    if (provider && typeof provider.request === 'function') return provider;
    return null;
  }

  function buildRoninChain() {
    const chainId = Number(env.roninChainId || 2020);
    const rpcUrl = env.roninRpcUrl || 'https://api.roninchain.com/rpc';
    return {
      chainId,
      chainName: chainId === 2020 ? 'Ronin Mainnet' : `Ronin ${chainId}`,
      nativeCurrency: { name: 'Ronin', symbol: 'RON', decimals: 18 },
      rpcUrls: [rpcUrl],
      blockExplorerUrls: [chainId === 2020 ? 'https://app.roninchain.com' : 'https://saigon-app.roninchain.com'],
    };
  }

  async function ensureRoninChain(provider) {
    const chain = buildRoninChain();
    const targetHex = `0x${Number(chain.chainId).toString(16)}`;
    try {
      const current = await provider.request({ method: 'eth_chainId' });
      if (String(current).toLowerCase() === targetHex.toLowerCase()) return;
    } catch (_) {
      // continue
    }

    try {
      await provider.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: targetHex }] });
    } catch (err) {
      const code = Number((err && err.code) || 0);
      if (code === 4902 || code === -32603) {
        await provider.request({
          method: 'wallet_addEthereumChain',
          params: [
            {
              chainId: targetHex,
              chainName: chain.chainName,
              nativeCurrency: chain.nativeCurrency,
              rpcUrls: chain.rpcUrls,
              blockExplorerUrls: chain.blockExplorerUrls,
            },
          ],
        });
      } else {
        throw err;
      }
    }
  }

  async function getWalletConnectProvider() {
    const projectId = env.walletConnectProjectId || '';
    if (!projectId) {
      throw new Error('WalletConnect is not configured.');
    }
    const EthereumProvider = window.WalletConnectEthereumProvider;
    if (!EthereumProvider || typeof EthereumProvider.init !== 'function') {
      throw new Error('WalletConnect client failed to load.');
    }
    const chain = buildRoninChain();
    return EthereumProvider.init({
      projectId,
      chains: [chain.chainId],
      optionalChains: [chain.chainId],
      showQrModal: true,
      methods: ['eth_sendTransaction', 'personal_sign', 'eth_signTypedData', 'eth_signTypedData_v4'],
      rpcMap: { [chain.chainId]: chain.rpcUrls[0] },
    });
  }

  async function connectWalletAndSignin(options) {
    const connectionType = (options && options.connectionType) || 'injected';
    const statusEl = document.getElementById('cw-wallet-status');
    const help = document.getElementById('cw-token-help');
    let provider = null;

    if (connectionType === 'walletconnect') {
      statusEl.textContent = 'Opening WalletConnect...';
      provider = await getWalletConnectProvider();
    } else {
      provider = getInjectedProvider();
      if (!provider) {
        throw new Error('No injected wallet provider found.');
      }
    }

    statusEl.textContent = `Connecting via ${connectionType}...`;
    const accounts = await provider.request({ method: 'eth_requestAccounts' });
    const walletAddress = accounts && accounts[0] ? String(accounts[0]).toLowerCase() : '';
    if (!walletAddress) {
      throw new Error('No wallet address returned by provider.');
    }

    await ensureRoninChain(provider);
    statusEl.textContent = `Connected ${shortWallet(walletAddress)}. Requesting nonce...`;

    const nonceRes = await fetch(`${API_BASE}/api/cw/get_nonce`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ walletAddress }),
    });
    const nonceData = await nonceRes.json();
    if (!nonceData.ok || !nonceData.nonce) {
      throw new Error(nonceData.error || 'Failed to get nonce.');
    }

    statusEl.textContent = 'Please sign nonce in wallet...';
    const signature = await provider.request({
      method: 'personal_sign',
      params: [nonceData.nonce, walletAddress],
    });
    if (!signature) {
      throw new Error('Wallet signature was not returned.');
    }

    statusEl.textContent = 'Exchanging signature for custom token...';
    const customRes = await fetch(`${API_BASE}/api/cw/login_for_custom_token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ walletAddress, signature }),
    });
    const customData = await customRes.json();
    if (!customData.ok || !customData.customToken) {
      throw new Error(customData.error || 'Failed to exchange signature.');
    }

    statusEl.textContent = 'Signing in with Firebase custom token...';
    const signinRes = await fetch(`${API_BASE}/api/cw/signin_with_custom_token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ customToken: customData.customToken }),
    });
    const signinData = await signinRes.json();
    if (!signinData.ok || !signinData.idToken) {
      throw new Error(signinData.error || 'Failed Firebase sign-in.');
    }

    const expiresIn = Number(signinData.expiresIn || 0);
    const expiresAt = Date.now() + Math.max(0, expiresIn) * 1000;

    localStorage.setItem(ID_TOKEN_KEY, signinData.idToken);
    localStorage.setItem(CW_TOKEN_KEY, signinData.idToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, signinData.refreshToken || '');
    localStorage.setItem(EXPIRES_AT_KEY, String(expiresAt));
    localStorage.setItem(WALLET_KEY, walletAddress);
    localStorage.setItem(CONNECTION_TYPE_KEY, connectionType);

    upsertWalletSession(walletAddress, {
      token: signinData.idToken,
      expiresAt,
      refreshToken: signinData.refreshToken || '',
      idToken: signinData.idToken,
      lastLoginAt: Date.now(),
    });

    help.textContent = 'Signed in successfully.';
    statusEl.textContent = `Connected: ${shortWallet(walletAddress)}`;
  }

  function startStatusPolling() {
    if (statusPollInterval) return;
    statusPollInterval = setInterval(refreshAccountStatusOnce, 15000);
  }

  function stopStatusPolling() {
    if (statusPollInterval) {
      clearInterval(statusPollInterval);
      statusPollInterval = null;
    }
  }

  window.addEventListener('DOMContentLoaded', () => {
    const connectBtn = document.getElementById('cw-connect-btn');
    const refreshBtn = document.getElementById('cw-refresh-btn');
    const modal = document.getElementById('cw-token-modal');
    const statusEl = document.getElementById('cw-wallet-status');
    const help = document.getElementById('cw-token-help');
    const closeBtn = document.getElementById('cw-token-close');
    const clearBtn = document.getElementById('cw-token-clear');
    const injectedBtn = document.getElementById('cw-connect-injected');
    const walletConnectBtn = document.getElementById('cw-connect-walletconnect');

    function openModal() {
      modal?.classList.add('open');
      const session = getSession();
      if (session.wallet) {
        statusEl.textContent = `Connected ${shortWallet(session.wallet)}`;
      } else {
        statusEl.textContent = 'Disconnected';
      }
      help.textContent = '';
    }

    function closeModal() {
      modal?.classList.remove('open');
    }

    connectBtn?.addEventListener('click', () => {
      openModal();
    });

    closeBtn?.addEventListener('click', closeModal);

    modal?.addEventListener('click', (event) => {
      if (event.target === modal) closeModal();
    });

    injectedBtn?.addEventListener('click', async () => {
      try {
        await connectWalletAndSignin({ connectionType: 'injected' });
        await refreshAccountStatusOnce();
        startStatusPolling();
      } catch (err) {
        help.textContent = String(err && err.message ? err.message : err);
      }
    });

    walletConnectBtn?.addEventListener('click', async () => {
      try {
        await connectWalletAndSignin({ connectionType: 'walletconnect' });
        await refreshAccountStatusOnce();
        startStatusPolling();
      } catch (err) {
        help.textContent = String(err && err.message ? err.message : err);
      }
    });

    refreshBtn?.addEventListener('click', async () => {
      await refreshAccountStatusOnce();
    });

    clearBtn?.addEventListener('click', () => {
      localStorage.removeItem(ID_TOKEN_KEY);
      localStorage.removeItem(CW_TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      localStorage.removeItem(EXPIRES_AT_KEY);
      localStorage.removeItem(WALLET_KEY);
      localStorage.removeItem(CW_ACTIVE_WALLET_KEY);
      localStorage.removeItem(CW_SESSION_INDEX_KEY);
      localStorage.removeItem(ACCOUNT_STATUS_KEY);
      localStorage.removeItem(CONNECTION_TYPE_KEY);
      stopStatusPolling();
      updateAccountWidget(null);
      closeModal();
    });

    refreshAccountStatusOnce();
    startStatusPolling();
  });
})();
