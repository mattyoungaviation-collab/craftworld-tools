/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: {
    ignoreDuringBuilds: true,
  },
  webpack: (config) => {
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      // prevents optional/react-native-only deps from breaking Next build
      '@react-native-async-storage/async-storage': false,
      // (optional) helps if pino-pretty ever gets pulled during bundling
      'pino-pretty': false,
    }
    return config
  },
};

export default nextConfig;
;
