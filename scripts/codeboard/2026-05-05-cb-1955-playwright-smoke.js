// Playwright smoke test for CB-1955 UI — substitutes Chrome MCP when the
// MCP transport is wedged. Drives a real headless Chromium, captures
// console errors + screenshots, and verifies the EPIC 5 components I
// shipped this session actually mount and render.
//
// Run from PMv2 frontend dir:
//   cd frontend && npx playwright install chromium  # one-time
//   node ../scripts/codeboard/2026-05-05-cb-1955-playwright-smoke.js
const { chromium } = require('/Volumes/Seagate/Claude/ProjectsManagerWebV2Production/frontend/node_modules/playwright-core');
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost:3601';
const PROJECT_ID = '1511e54f71dccd3fa79f67fe';
const SCREENSHOT_DIR = '/tmp/cb1955-screenshots';
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

const errors = [];
const warnings = [];
const networkFails = [];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
    if (msg.type() === 'warning') warnings.push(msg.text());
  });
  page.on('pageerror', (err) => errors.push(`PAGEERROR: ${err.message}`));
  page.on('requestfailed', (req) => {
    networkFails.push(`${req.method()} ${req.url()} — ${req.failure()?.errorText}`);
  });

  console.log(`\n=== Phase 1: load codeboard ===`);
  const t0 = Date.now();
  try {
    await page.goto(`${BASE}/codeboard?project=${PROJECT_ID}&view=list`, {
      waitUntil: 'networkidle',
      timeout: 90000,
    });
    console.log(`  loaded in ${Date.now() - t0}ms`);
  } catch (e) {
    console.log(`  FAIL: page.goto threw: ${e.message}`);
  }
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '01-codeboard-list.png'), fullPage: false });

  console.log(`\n=== Phase 2: check EPIC 5 toolbar buttons ===`);
  const newGroupBtn = await page.$('button:has-text("New Group")');
  const selectBtn = await page.$('button:has-text("Select")');
  console.log(`  '+ New Group' button visible: ${!!newGroupBtn}`);
  console.log(`  'Select' (multi-select toggle) visible: ${!!selectBtn}`);

  console.log(`\n=== Phase 3: open the New Group modal ===`);
  if (newGroupBtn) {
    await newGroupBtn.click();
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '02-new-group-modal.png') });
    const modalTitle = await page.$('text=Create issue group');
    console.log(`  Modal title 'Create issue group' present: ${!!modalTitle}`);
    const titleInput = await page.$('#group-title');
    const memberSearch = await page.$('#group-member-search');
    console.log(`  Title input present: ${!!titleInput}`);
    console.log(`  Member search input present: ${!!memberSearch}`);

    // Close modal by ESC
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);
  }

  console.log(`\n=== Phase 4: toggle multi-select mode ===`);
  if (selectBtn) {
    await selectBtn.click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03-select-mode-on.png') });
    // Look for any checkbox in the list view (HierarchyListView injects them)
    const checkboxes = await page.$$('input[type="checkbox"][aria-label^="Select "]');
    console.log(`  Checkboxes visible in list view: ${checkboxes.length}`);
    // Toggle off
    await selectBtn.click();
    await page.waitForTimeout(200);
  }

  console.log(`\n=== Phase 5: open the existing CB-1945 cascade-walker group detail page ===`);
  // Group id from yesterday's CB-2024 migration
  const GROUP_ID = 'f8224ae9-68d0-4632-a56a-61de4f6a8312';
  try {
    await page.goto(`${BASE}/codeboard/groups/${GROUP_ID}`, {
      waitUntil: 'networkidle',
      timeout: 30000,
    });
    await page.waitForTimeout(500);
  } catch (e) {
    console.log(`  FAIL: group page goto: ${e.message}`);
  }
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04-group-detail.png') });

  // CB-2016 — segmented status bar should render
  const statusBar = await page.$('div[role="img"][aria-label]');
  console.log(`  CB-2016 segmented status bar present: ${!!statusBar}`);
  if (statusBar) {
    const ariaLabel = await statusBar.getAttribute('aria-label');
    console.log(`  Bar aria-label: "${ariaLabel}"`);
  }

  console.log(`\n=== Summary ===`);
  console.log(`  Console errors: ${errors.length}`);
  errors.slice(0, 10).forEach((e) => console.log(`    - ${e.slice(0, 200)}`));
  console.log(`  Console warnings: ${warnings.length}`);
  console.log(`  Network failures: ${networkFails.length}`);
  networkFails.slice(0, 10).forEach((f) => console.log(`    - ${f}`));
  console.log(`  Screenshots: ${SCREENSHOT_DIR}`);

  await browser.close();
  // Exit with non-zero if any console errors so Bash sees the failure.
  process.exit(errors.length > 0 ? 1 : 0);
})();
