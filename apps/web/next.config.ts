import type { NextConfig } from "next";
import { securityHeaders } from "./security-headers";

const nextConfig: NextConfig = {
  // Workspace packages ship TypeScript source; Next.js compiles them with the app.
  transpilePackages: ["@multiverse/contracts"],
  poweredByHeader: false,
  reactStrictMode: true,
  async headers() {
    const development = process.env.NODE_ENV === "development";
    return [{ source: "/:path*", headers: securityHeaders(development) }];
  },
};

export default nextConfig;
