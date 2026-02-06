export default function WalletStatus() {
  return (
    <div className="wallet-widget">
      <div id="account-power-widget" className="wallet-power">
        <button type="button" id="cw-connect-btn">
          Connect Ronin Wallet
        </button>
        <span>
          <span className="label">Power:</span> <strong id="power-value">—</strong>
        </span>
        <span>
          <span className="label">Refill in:</span> <strong id="refill-value">—</strong>
        </span>
        <button type="button" id="cw-refresh-btn">
          Refresh
        </button>
      </div>

      <div id="cw-status-banner" className="wallet-banner" style={{ display: 'none' }}>
        <div className="summary" id="cw-status-summary"></div>
        <details>
          <summary>Details</summary>
          <pre id="cw-status-details"></pre>
        </details>
      </div>

      <div id="cw-token-modal" className="wallet-modal" role="dialog" aria-modal="true">
        <div className="wallet-modal-card">
          <h3>Connect Ronin Wallet</h3>
          <p>Sign in with your wallet to get a Craft World Firebase session.</p>
          <div id="cw-wallet-status" className="wallet-status">
            Disconnected
          </div>
          <div className="wallet-provider-actions">
            <button type="button" id="cw-connect-injected">
              Connect Ronin Extension
            </button>
            <button type="button" id="cw-connect-walletconnect">
              Connect WalletConnect
            </button>
          </div>
          <div id="cw-provider-hint" className="wallet-hint"></div>
          <div id="cw-token-help" className="wallet-help"></div>
          <div className="wallet-modal-actions">
            <button type="button" id="cw-token-close">
              Close
            </button>
            <button type="button" id="cw-token-clear">
              Disconnect
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
