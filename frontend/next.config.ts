import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone is for Docker; Netlify uses its own Next.js runtime.
  ...(process.env.NETLIFY !== "true" && process.env.CI !== "true"
    ? { output: "standalone" as const, outputFileTracingRoot: __dirname }
    : {})
};

export default nextConfig;
