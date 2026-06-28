import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const repoName = process.env.GITHUB_REPOSITORY?.split("/")[1] || "";
const isGitHubPagesBuild = process.env.GITHUB_ACTIONS === "true";
const base = isGitHubPagesBuild && repoName ? `/${repoName}/` : "/";

export default defineConfig({
  plugins: [react()],
  base,
  server: {
    port: 5173,
  },
});
