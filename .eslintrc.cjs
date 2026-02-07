module.exports = {
  root: true,
  env: { es2022: true, node: true, browser: true },
  parserOptions: { ecmaVersion: 2022, sourceType: "module" },
  plugins: ["import", "unused-imports"],
  extends: ["eslint:recommended", "plugin:import/recommended", "prettier"],
  rules: {
    "unused-imports/no-unused-imports": "error"
  }
};
