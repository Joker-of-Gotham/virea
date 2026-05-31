import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function argValue(name, fallback = "") {
  const index = process.argv.indexOf(name);
  return index >= 0 && index + 1 < process.argv.length ? process.argv[index + 1] : fallback;
}

function requiredValue(name, envName) {
  const value = argValue(name, process.env[envName] || "");
  if (!value) {
    throw new Error(`Missing ${name}. Pass ${name} or set ${envName}.`);
  }
  return value;
}

async function loadPlaywright() {
  const moduleSpec = process.env.PLAYWRIGHT_MODULE || "playwright";
  if (/^[a-zA-Z]:[\\/]/.test(moduleSpec) || moduleSpec.startsWith("/")) {
    return import(pathToFileURL(moduleSpec).href);
  }
  return import(moduleSpec);
}

function slugPart(value) {
  return String(value)
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 72)
    .toLowerCase();
}

async function waitForSample(page, sampleId) {
  await page.waitForFunction(
    (id) => {
      const title = document.querySelector("#sampleTitle")?.textContent || "";
      const max = Number(document.querySelector("#modelFrameSlider")?.max || 0);
      return title === id && max > 0;
    },
    sampleId,
    { timeout: 30000 },
  );
  await page.waitForTimeout(800);
}

async function loadSample(page, dataSource, dataset, sampleId, maxFrames) {
  await page.waitForFunction(() => Boolean(window.__vireaShowcase?.loadSample), { timeout: 30000 });
  await page.evaluate(
    (payload) => window.__vireaShowcase.loadSample(payload),
    { dataSource, dataset, sampleId, maxFrames },
  );
  await waitForSample(page, sampleId);
}

async function recordCanvas(page, outPath, seconds, bitrate) {
  const downloadPromise = page.waitForEvent("download", { timeout: seconds * 1000 + 30000 });
  await page.evaluate(
    async ({ seconds, bitrate }) => {
      const canvas = document.querySelector("#modelCanvas");
      const playButton = document.querySelector("#modelPlayButton");
      if (!canvas || !playButton) {
        throw new Error("model canvas or play button is missing");
      }
      const mimeType = MediaRecorder.isTypeSupported("video/webm;codecs=vp8")
        ? "video/webm;codecs=vp8"
        : "video/webm";
      const stream = canvas.captureStream(24);
      const chunks = [];
      const recorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: bitrate });
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size > 0) chunks.push(event.data);
      });
      const stopped = new Promise((resolve) => {
        recorder.addEventListener("stop", resolve, { once: true });
      });
      recorder.start(100);
      playButton.click();
      await new Promise((resolve) => setTimeout(resolve, seconds * 1000));
      playButton.click();
      recorder.stop();
      await stopped;
      const blob = new Blob(chunks, { type: mimeType });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "clip.webm";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
    { seconds, bitrate },
  );
  const download = await downloadPromise;
  await download.saveAs(outPath);
}

async function zoomModelCanvas(page) {
  const canvas = page.locator("#modelCanvas");
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox();
  if (!box) return;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, -1400);
  await page.waitForTimeout(300);
}

async function main() {
  const server = requiredValue("--server", "VIREA_SHOWCASE_SERVER");
  const dataSource = argValue("--data-source", "demo");
  const manifestPath = path.resolve(repoRoot, argValue("--manifest", "doc/showcase/showcase-samples.json"));
  const outDir = path.resolve(repoRoot, argValue("--out-dir", "doc/showcase/videos"));
  const vrmPath = path.resolve(requiredValue("--vrm", "VIREA_SHOWCASE_VRM"));
  const maxFrames = Number(argValue("--max-frames", "180"));
  const seconds = Number(argValue("--seconds", "3.5"));
  const bitrate = Number(argValue("--bitrate", "1200000"));
  const executablePath = argValue("--executable", process.env.PLAYWRIGHT_CHROMIUM || "");

  await fs.mkdir(outDir, { recursive: true });
  const manifest = JSON.parse(await fs.readFile(manifestPath, "utf-8"));
  const { chromium } = await loadPlaywright();
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
  });
  const page = await browser.newPage({ viewport: { width: 960, height: 720 } });
  await page.goto(server, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#modelFileInput", { timeout: 30000 });
  await page.setInputFiles("#modelFileInput", vrmPath);
  await page.waitForFunction(
    () => (document.querySelector("#modelStatus")?.textContent || "").includes("loaded as VRM"),
    { timeout: 30000 },
  );
  const rendered = [];
  for (const [dataset, rows] of Object.entries(manifest)) {
    for (let index = 0; index < rows.length; index += 1) {
      const row = rows[index];
      const fileName = `${String(index + 1).padStart(2, "0")}_${dataset}_${slugPart(row.sample_id)}.webm`;
      const outPath = path.join(outDir, fileName);
      console.log(`[showcase] ${dataset} ${index + 1}/${rows.length}: ${row.sample_id}`);
      await loadSample(page, dataSource, dataset, row.sample_id, maxFrames);
      await zoomModelCanvas(page);
      await recordCanvas(page, outPath, seconds, bitrate);
      row.video = `doc/showcase/videos/${fileName}`;
      rendered.push(outPath);
      console.log(`[showcase] wrote ${outPath}`);
    }
  }

  await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf-8");
  await browser.close();
  console.log(`[showcase] rendered ${rendered.length} videos`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
