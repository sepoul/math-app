import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // The SDK ships compiled JS in dist/; transpiling it through Next keeps
  // module/type resolution consistent across Turbopack + the build.
  transpilePackages: ["@sepoul-packages/sdk"],
};

export default nextConfig;
