import { useEffect, useState } from 'react';
import { apiClient } from '../services/apiClient';
import {
  ACCOUNT_STATUS_KEY,
  EXPIRES_AT_KEY,
  getActiveWallet,
  ID_TOKEN_KEY,
  normalizeWalletAddress,
} from '../services/storage';
import { connectWallet, getSession, isSessionExpired } from '../services/wallet';

export default function WalletStatus() {
  const [status, setStatus] = useState<'disconnected' | 'connecting' | 'connected' | 'error'>(
    'disconnected',
  );
  const [wallet, setWallet] = useState('');
  const [power, setPower] = useState<number | null>(null);
  const [refill, setRefill] = useState('00:00:00');

  useEffect(() => {
    const session = getSession();
    setWallet(normalizeWalletAddress(session.wallet || getActiveWallet()));
    if (session.cwToken && !isSessionExpired(session.expiresAt)) {
      refreshStatus();
    }
  }, []);

  async function refreshStatus() {
    const session = getSession();
    if (!session.cwToken || isSessionExpired(session.expiresAt)) {
      setStatus('disconnected');
      setPower(null);
      setRefill('00:00:00');
      return;
    }

    setStatus('connecting');
    try {
      const data: any = await apiClient.accountStatus(session.cwToken);
      if (!data.ok || data.auth !== 'ok') {
        setStatus('error');
        return;
      }
      localStorage.setItem(ACCOUNT_STATUS_KEY, JSON.stringify(data));
      setStatus('connected');
      setPower(Number(data.power || 0));
      setRefill(String(data.refillHMS || '00:00:00'));
    } catch {
      setStatus('error');
    }
  }

  async function handleConnect(connectionType: 'injected' | 'walletconnect') {
    try {
      setStatus('connecting');
      const result = await connectWallet(connectionType);
      setWallet(result.walletAddress);
      localStorage.setItem(ID_TOKEN_KEY, getSession().idToken);
      localStorage.setItem(EXPIRES_AT_KEY, String(result.expiresAt));
      await refreshStatus();
    } catch {
      setStatus('error');
    }
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
      <span className="badge">
        {status === 'connected' ? 'Connected' : status === 'connecting' ? 'Connecting' : 'Disconnected'}
      </span>
      {wallet ? <span className="muted">{wallet.slice(0, 6)}…{wallet.slice(-4)}</span> : null}
      <span className="muted">Power: {power ?? '—'}</span>
      <span className="muted">Refill: {refill}</span>
      <button type="button" onClick={() => handleConnect('injected')} className="secondary">
        Connect Ronin
      </button>
      <button type="button" onClick={() => handleConnect('walletconnect')} className="secondary">
        WalletConnect
      </button>
      <button type="button" onClick={refreshStatus} className="secondary">
        Refresh
      </button>
    </div>
  );
}
