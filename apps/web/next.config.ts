import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Workspace packages ship TypeScript source; Next.js compiles them with the app.
  transpilePackages: ["@multiverse/contracts"],
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;
