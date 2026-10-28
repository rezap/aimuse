import type { NextConfig } from "next";

// Static export: the app is plain HTML/JS served by Firebase Hosting and talks to Firebase
// directly from the browser. No server needed.
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
