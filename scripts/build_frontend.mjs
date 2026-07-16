import { cp, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceDir = path.join(rootDir, "frontend");
const outputDir = path.resolve(process.env.OUTPUT_DIR || process.env.OUT_DIR || path.join(sourceDir, "dist"));
const apiBaseUrl = (process.env.FRONTEND_API_BASE_URL || "").replace(/\/$/, "");
const configPath = process.env.FRONTEND_CONFIG_PATH || "/config";

if (!apiBaseUrl) {
  throw new Error("FRONTEND_API_BASE_URL must be set for the Vercel frontend build.");
}

await rm(outputDir, { recursive: true, force: true });
await mkdir(outputDir, { recursive: true });
for (const entry of await readdir(sourceDir, { withFileTypes: true })) {
  if (entry.name === "dist") continue;
  const src = path.join(sourceDir, entry.name);
  const dest = path.join(outputDir, entry.name);
  await cp(src, dest, { recursive: true });
}

const indexPath = path.join(outputDir, "index.html");
const indexHtml = await readFile(indexPath, "utf8");
const configUrl = `${apiBaseUrl}${configPath.startsWith("/") ? configPath : `/${configPath}`}`;

if (!indexHtml.includes("__API_CONFIG_PATH__")) {
  throw new Error("Frontend config placeholder was not found.");
}

await writeFile(indexPath, indexHtml.replaceAll("__API_CONFIG_PATH__", configUrl));
console.log(`Built standalone frontend with backend config: ${configUrl}`);
