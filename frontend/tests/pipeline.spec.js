import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import process from "node:process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const frontend = fileURLToPath(new URL("../", import.meta.url));
const runsDirectory = new URL("../../sem_pipeline/website/runs/", import.meta.url);
const runs = readdirSync(runsDirectory)
  .filter((run) => existsSync(new URL(`${run}/output/facts.json`, runsDirectory)))
  .sort();
const facts = Object.fromEntries(
  runs.map((run) => [run, JSON.parse(readFileSync(new URL(`${run}/output/facts.json`, runsDirectory), "utf8"))]),
);
const baseURL = "http://127.0.0.1:5189";
const apiURL = "http://127.0.0.1:8019";
let server;

if (existsSync("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")) {
  test.use({ launchOptions: { channel: "chrome" } });
}

test.beforeAll(async () => {
  server = spawn(
    process.execPath,
    ["node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "5189", "--strictPort"],
    {
      cwd: frontend,
      env: { ...process.env, VITE_API_URL: apiURL },
      stdio: "pipe",
    },
  );
  await expect
    .poll(
      async () => {
        if (server.exitCode !== null) throw new Error("Test website did not start");
        try {
          return (await fetch(baseURL)).status;
        } catch {
          return 0;
        }
      },
      { timeout: 15000 },
    )
    .toBe(200);
});

test.afterAll(async () => {
  if (server && server.exitCode === null) {
    await new Promise((resolve) => {
      server.once("exit", resolve);
      server.kill("SIGTERM");
    });
  }
});

async function mockAPI(page, options = {}) {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) => {
    const origin = new URL(route.request().url()).origin;
    return origin === baseURL || origin === apiURL ? route.continue() : route.abort();
  });
  await page.route(`${apiURL}/**`, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    options.requests?.push(path);
    if (path === "/health") return route.fulfill({ json: { status: "ok" } });
    if (path === "/batches/inventory") return route.fulfill({ json: options.inventory ?? [] });
    const images = path.match(/^\/batches\/([^/]+)\/images$/);
    if (images) return route.fulfill({ json: options.images?.[images[1]] ?? [] });
    if (path === "/v3/jobs") return route.fulfill({ json: options.runs ?? runs });
    const report = path.match(/^\/v3\/jobs\/([^/]+)\/report(?:\/cancel)?$/);
    if (report) {
      if (options.report) return options.report(route, url);
      if (route.request().method() !== "GET") throw new Error("Unexpected report-generation request");
      return route.fulfill({ json: { status: "none" } });
    }
    const job = path.match(/^\/v3\/jobs\/([^/]+)$/);
    if (job && facts[job[1]])
      return route.fulfill({
        json: {
          status: "done",
          steps: [],
          inputs: [],
          facts: options.facts ?? facts[job[1]],
        },
      });
    if (path.startsWith("/v3/runs/") || /^\/batches\/[^/]+\/images\//.test(path))
      return route.fulfill({
        contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100" fill="#506578"/></svg>',
      });
    return route.fulfill({ status: 404, json: { detail: "Unknown test request" } });
  });
  return errors;
}

function libraryFixture() {
  const groups = ["spotA", "spotB"].map((id) => ({
    specimen_id: id,
    grouping: "filename",
    images: ["BSE", "ETD", "Inlens"].map((filter) => ({ filter, filename: `img_${id}_${filter}.tif` })),
  }));
  return {
    inventory: ["1", "2", "3"].map((batch_id) => ({
      batch_id,
      role: "reference",
      source: `ReferenceBatches/Batch_${batch_id}`,
      status: "ready",
      image_count: 6,
      group_count: 2,
      grouping: "filename",
      detectors: { BSE: 2, ETD: 2, INLENS: 2 },
      preview: "img_spotA_BSE.tif",
    })),
    images: { 1: groups, 2: groups, 3: groups },
    requests: [],
  };
}

test("Local reference cards show supplied files and the gallery filters detector views", async ({ page }) => {
  const library = libraryFixture();
  const errors = await mockAPI(page, library);
  await page.goto(baseURL);
  await expect(page.getByRole("heading", { name: "Your reference batches" })).toBeVisible();
  await expect(page.locator(".reference-summary")).toContainText("18");
  await expect(page.locator(".batch-cover img")).toHaveCount(3);
  const batch = page.getByRole("button", { name: "Browse Batch 1", exact: true });
  await expect(batch).toContainText("ReferenceBatches/Batch_1");
  await expect(batch).toContainText("6 TIFF views");
  await batch.click();
  await expect(page.getByRole("heading", { name: "Batch 1 microscopy images" })).toBeVisible();
  await expect(page.locator(".microscopy-image")).toHaveCount(6);
  await page.getByLabel("Detector view", { exact: true }).selectOption("BSE");
  await expect(page.locator(".microscopy-image")).toHaveCount(2);
  await page.getByRole("searchbox", { name: "Search images" }).fill("spotA");
  await expect(page.locator(".microscopy-image")).toHaveCount(1);
  await expect(page.getByRole("link", { name: "Download TIFF", exact: true })).toHaveAttribute(
    "href",
    /img_spotA_BSE.tif\?download=true$/,
  );
  await page.getByRole("searchbox", { name: "Search images" }).fill("not-present");
  await expect(page.getByRole("button", { name: "Reset filters" })).toBeVisible();
  await page.getByRole("button", { name: "Reset filters" }).click();
  await expect(page.locator(".microscopy-image")).toHaveCount(6);
  await expect(page.getByRole("tab", { name: "General report" })).toBeVisible();
  expect(library.requests.some((path) => path.includes("analysis-report"))).toBe(false);
  expect(errors).toEqual([]);
});

test("Refresh discovers newly added local images without replacing the original workflow", async ({ page }) => {
  const library = libraryFixture();
  const errors = await mockAPI(page, library);
  await page.goto(baseURL);
  await page.getByRole("button", { name: "Browse Batch 1", exact: true }).click();
  await expect(page.locator(".microscopy-image")).toHaveCount(6);
  library.images["1"] = [
    ...library.images["1"],
    { specimen_id: "newspot", grouping: "filename", images: [{ filter: "BSE", filename: "img_newspot_BSE.tif" }] },
  ];
  library.inventory[0] = {
    ...library.inventory[0],
    image_count: 7,
    group_count: 3,
    detectors: { BSE: 3, ETD: 2, INLENS: 2 },
  };
  await page.getByRole("button", { name: "Refresh local images", exact: true }).click();
  await expect(page.locator(".microscopy-image")).toHaveCount(7);
  await expect(page.getByRole("button", { name: "Browse Batch 1", exact: true })).toContainText("7 TIFF views");
  await page.getByRole("link", { name: "Analyse a new image set", exact: true }).click();
  await expect(page.getByRole("button", { name: "Identify the batch" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("The local reference library remains usable on a narrow screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const errors = await mockAPI(page, libraryFixture());
  await page.goto(baseURL);
  await expect(page.getByRole("button", { name: "Browse Batch 3", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test("Pipeline navigation renders before a run has been selected", async ({ page }) => {
  const errors = await mockAPI(page);
  await page.goto(baseURL);
  await page.getByRole("link", { name: "3 · Pipeline", exact: true }).click();
  await expect(page.getByRole("heading", { name: "From images to a batch call, step by step" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate report", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("Pipeline with no saved runs keeps the navigation and empty state", async ({ page }) => {
  const errors = await mockAPI(page, { runs: [] });
  await page.goto(`${baseURL}/#pipeline`);
  await expect(page.getByText("No runs yet. Upload a location on the Demo page.")).toBeVisible();
  await page.getByRole("link", { name: "2 · Demo", exact: true }).click();
  await expect(page.getByRole("button", { name: "Identify the batch" })).toBeVisible();
  expect(errors).toEqual([]);
});

for (const run of runs) {
  test(`Pipeline displays saved CV outputs for ${run}`, async ({ page }) => {
    const errors = await mockAPI(page);
    await page.goto(`${baseURL}/#pipeline/${run}`);
    await expect(page.getByRole("heading", { name: "Result", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Timings", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Generate report", exact: true })).toBeVisible();
    await page.getByAltText("segmentation overlay", { exact: true }).click();
    await expect(page.getByAltText("enlarged", { exact: true })).toBeVisible();
    await page.locator(".v3-zoom").click({ position: { x: 10, y: 10 } });
    await expect(page.locator(".v3-zoom")).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}

const reportFixture = {
  version: "crag-v1",
  status: "done",
  research_status: "supported",
  markdown: "## Checked report\n- Evidence-linked explanation.",
  explanations: { sample_one: "- Evidence-linked explanation." },
  claims: [
    {
      id: "c1",
      sample_id: "sample_one",
      kind: "interpretation",
      text: "Evidence-linked explanation.",
      fact_ids: ["F0_0"],
      supporting_fact_ids: ["F0_1"],
      citations: [{ source_id: "S1", quote: "A supporting scientific passage." }],
    },
  ],
  facts: {
    F0_0: { label: "Measured area", display: "5.7%", pointer: "/measurement", method: "Segmentation" },
    F0_1: {
      label: "Model calculation",
      display: "0.3 score",
      pointer: "/calculation",
      method: "Reported model",
      formula: "reported score contribution",
    },
  },
  sources: {
    S1: {
      id: "S1",
      title: "Scientific source",
      text: "A supporting scientific passage.",
      location: "Methods",
      url: "https://example.org/paper",
      access: "full_text",
      status: "candidate",
      updates: "none_found",
      checked_at: 1700000000,
      caveats: [],
    },
  },
  audit: { trace: [], calls: [], retrieval_grades: [], research_gaps: [] },
};

test("The research report preserves generation, evidence, regeneration and download controls", async ({ page }) => {
  let started = false;
  const requests = [];
  const errors = await mockAPI(page, {
    report: async (route, url) => {
      if (route.request().method() === "POST") {
        requests.push(url.searchParams.get("force"));
        started = true;
        return route.fulfill({ json: { status: "running", stage: "analyzing" } });
      }
      return route.fulfill({ json: started ? reportFixture : { status: "none" } });
    },
  });
  await page.goto(`${baseURL}/#pipeline/${runs[0]}`);
  await page.getByRole("button", { name: "Generate report", exact: true }).click();
  await expect(page.getByRole("button", { name: "Regenerate", exact: true })).toBeVisible();
  await page.getByText("Supporting measurements, mathematics and research", { exact: true }).click();
  await expect(page.getByRole("table").filter({ hasText: "Source-linked evidence" })).toHaveClass(/v3live-table/);
  await expect(page.getByRole("cell", { name: /Model calculation/ })).toBeVisible();
  await page.getByText("Scientific source", { exact: true }).click();
  await expect(page.getByText("A supporting scientific passage.", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download (.md)" })).toHaveAttribute("href", /^data:text\/markdown/);
  await page.getByRole("button", { name: "Regenerate", exact: true }).click();
  await expect.poll(() => requests).toEqual(["false", "true"]);
  expect(errors).toEqual([]);
});

test("A running report resumes polling after reload and can be cancelled", async ({ page }) => {
  let cancelled = false;
  const errors = await mockAPI(page, {
    report: async (route, url) => {
      if (url.pathname.endsWith("/cancel")) cancelled = true;
      return route.fulfill({
        json: cancelled
          ? { status: "cancelled", error: "Report generation was cancelled." }
          : { status: "running", stage: "reviewing" },
      });
    },
  });
  await page.goto(`${baseURL}/#pipeline/${runs[0]}`);
  await expect(page.getByRole("status")).toHaveText("reviewing");
  await page.reload();
  await expect(page.getByRole("status")).toHaveText("reviewing");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByRole("button", { name: "Try again", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
