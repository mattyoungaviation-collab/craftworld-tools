export const CW_QUERIES = {
  exchangePriceList: {
    operationName: 'ExchangePriceList',
    query: `query ExchangePriceList {\n  exchangePriceList {\n    referenceSymbol\n    amount\n    recommendation\n  }\n}`
  },
  accountResources: {
    operationName: 'AccountResources',
    query: `query AccountResources {\n  account {\n    resources {\n      symbol\n      amount\n    }\n  }\n}`
  },
  accountWallets: {
    operationName: 'AccountWallets',
    query: `query AccountWallets {\n  account {\n    wallets {\n      address\n      type\n      provider\n      providerId\n      primary\n    }\n  }\n}`
  },
  deputyWalletAddress: {
    operationName: 'DeputyWalletAddress',
    query: `query DeputyWalletAddress($walletAddress: String!) {\n  deputyWalletAddress(walletAddress: $walletAddress)\n}`
  },
  accountWorkshop: {
    operationName: 'AccountWorkshop',
    query: `query AccountWorkshop {\n  account {\n    workshop {\n      symbol\n      level\n    }\n  }\n}`
  },
  accountProficiencies: {
    operationName: 'AccountProficiencies',
    query: `query AccountProficiencies {\n  account {\n    proficiencies {\n      symbol\n      collectedAmount\n      claimedLevel\n    }\n  }\n}`
  },
  proficiencyLeaderboard: {
    operationName: 'ProficiencyLeaderboard',
    query: `query ProficiencyLeaderboard($symbol: String!, $userId: String!) {\n  proficiencyLeaderboard(symbol: $symbol) {\n    leaderboard(count: 100) {\n      position\n      collectedAmount\n      profile {\n        uid\n        walletAddress\n        avatarUrl\n        displayName\n      }\n    }\n    entryByUserId(userId: $userId) {\n      position\n      collectedAmount\n      profile {\n        uid\n        walletAddress\n        avatarUrl\n        displayName\n      }\n    }\n  }\n}`
  }
} as const;
