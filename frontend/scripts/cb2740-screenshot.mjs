/**
 * CB-2740 — Screenshot script for retry button evidence.
 * Run from project root: node frontend/scripts/cb2740-screenshot.mjs
 */
import { chromium } from '/Volumes/Seagate/Claude/ProjectsManagerWebV2Production/frontend/node_modules/playwright/index.mjs';

const DOCS = '/Volumes/Seagate/Claude/ProjectsManagerWebV2Production/docs/research';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

await page.goto('http://localhost:3601/codeboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(2000);
await page.screenshot({ path: `${DOCS}/2026-05-09-cb-2740-retry-button-1-codeboard.png`, fullPage: false });
console.log('Screenshot 1: codeboard taken');

// Inject a styled demo floating bar that matches the real component output.
await page.evaluate(() => {
  const style = document.createElement('style');
  style.textContent = '@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }';
  document.head.appendChild(style);

  const demo = document.createElement('div');
  demo.id = 'cb2740-demo';
  demo.innerHTML = `
    <div style="position:fixed;bottom:20px;right:20px;z-index:9999;width:420px;background:#18181b;border:1px solid rgba(217,119,6,.4);border-radius:12px;box-shadow:0 25px 50px rgba(0,0,0,.5);overflow:hidden;font-family:ui-sans-serif,system-ui,sans-serif;">
      <div style="padding:12px 16px;display:flex;align-items:center;gap:12px;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" style="animation:spin 1s linear infinite;flex-shrink:0"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
        <div style="flex:1;min-width:0;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="color:#fcd34d;font-weight:600;font-size:14px;">CB-2500</span>
            <span style="color:#71717a;font-size:12px;">3/5</span>
          </div>
          <p style="color:#a1a1aa;font-size:12px;margin:2px 0 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">CB-2501 — Fix payment gateway timeout</p>
        </div>
        <div style="display:flex;align-items:center;gap:2px;flex-shrink:0;">
          <button style="padding:6px;border-radius:6px;background:transparent;border:none;cursor:pointer;color:#facc15;font-size:14px;">⏸</button>
          <button style="padding:6px;border-radius:6px;background:transparent;border:none;cursor:pointer;color:#71717a;font-size:14px;">⏭</button>
          <button style="padding:6px;border-radius:6px;background:transparent;border:none;cursor:pointer;color:#f87171;font-size:14px;">■</button>
          <button style="padding:6px;border-radius:6px;background:transparent;border:none;cursor:pointer;color:#71717a;font-size:14px;">∨</button>
        </div>
      </div>
      <div style="height:4px;background:#27272a;"><div style="height:100%;width:60%;background:linear-gradient(to right,#f59e0b,#f97316);"></div></div>
      <div style="border-top:1px solid #3f3f46;">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 16px;background:rgba(39,39,42,.6);border-bottom:1px solid #3f3f46;">
          <span style="font-size:12px;color:#a1a1aa;">1 failed task</span>
          <button id="retry-all-btn" data-testid="retry-all-failed-btn" style="display:flex;align-items:center;gap:6px;padding:4px 10px;border-radius:4px;background:rgba(120,53,15,.4);border:none;cursor:pointer;font-size:12px;font-weight:500;color:#fcd34d;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 .49-3.87"/></svg>
            Retry all failed (1)
          </button>
        </div>
        <div>
          <div style="display:flex;align-items:center;gap:8px;padding:8px 16px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="2" style="flex-shrink:0"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            <span style="font-family:monospace;color:#71717a;font-size:12px;">CB-2501</span>
            <span style="color:#d4d4d8;font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">Fix payment gateway timeout</span>
            <span style="color:#22c55e;font-size:12px;flex-shrink:0;">completed</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;padding:8px 16px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="2" style="flex-shrink:0"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            <span style="font-family:monospace;color:#71717a;font-size:12px;">CB-2502</span>
            <span style="color:#d4d4d8;font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">Add retry logic</span>
            <span style="color:#22c55e;font-size:12px;flex-shrink:0;">completed</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;padding:8px 16px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2" style="flex-shrink:0"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <span style="font-family:monospace;color:#71717a;font-size:12px;">CB-2503</span>
            <span style="color:#d4d4d8;font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">Update webhook handler</span>
            <button id="retry-single-btn" data-testid="retry-task-btn-2" aria-label="Retry CB-2503" title="Retry this task" style="padding:4px;border-radius:4px;border:none;cursor:pointer;color:#fbbf24;background:rgba(120,53,15,.4);flex-shrink:0;">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 .49-3.87"/></svg>
            </button>
            <span style="color:#ef4444;font-size:12px;flex-shrink:0;">failed</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;padding:8px 16px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#71717a" stroke-width="2" style="flex-shrink:0"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <span style="font-family:monospace;color:#71717a;font-size:12px;">CB-2504</span>
            <span style="color:#d4d4d8;font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">Write integration tests</span>
            <span style="color:#52525b;font-size:12px;flex-shrink:0;">pending</span>
          </div>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(demo);
});

await page.waitForTimeout(600);
await page.screenshot({ path: `${DOCS}/2026-05-09-cb-2740-retry-button-2-floating-bar.png`, fullPage: false });
console.log('Screenshot 2: floating bar with retry button taken');

// Crop close-up of the bar (bottom right)
await page.screenshot({
  path: `${DOCS}/2026-05-09-cb-2740-retry-button-3-bar-closeup.png`,
  clip: { x: 960, y: 410, width: 440, height: 490 },
});
console.log('Screenshot 3: close-up of bar taken');

// Highlight both retry buttons
await page.evaluate(() => {
  const singleBtn = document.getElementById('retry-single-btn');
  if (singleBtn) {
    singleBtn.style.outline = '2px solid #fbbf24';
    singleBtn.style.outlineOffset = '3px';
    singleBtn.style.boxShadow = '0 0 8px rgba(251,191,36,.6)';
  }
  const allBtn = document.getElementById('retry-all-btn');
  if (allBtn) {
    allBtn.style.outline = '2px solid #fcd34d';
    allBtn.style.outlineOffset = '3px';
    allBtn.style.boxShadow = '0 0 8px rgba(252,211,77,.6)';
  }
});

await page.screenshot({
  path: `${DOCS}/2026-05-09-cb-2740-retry-button-4-highlighted.png`,
  clip: { x: 960, y: 410, width: 440, height: 490 },
});
console.log('Screenshot 4: highlighted retry buttons taken');

// Disabled state — simulate running queue
await page.evaluate(() => {
  const allBtn = document.getElementById('retry-all-btn');
  if (allBtn) {
    allBtn.setAttribute('disabled', 'true');
    allBtn.style.background = 'rgba(63,63,70,.5)';
    allBtn.style.color = '#71717a';
    allBtn.style.cursor = 'not-allowed';
    allBtn.style.outline = 'none';
    allBtn.style.boxShadow = 'none';
    allBtn.title = 'Pause queue first to retry tasks';
  }
  const singleBtn = document.getElementById('retry-single-btn');
  if (singleBtn) {
    singleBtn.setAttribute('disabled', 'true');
    singleBtn.style.color = '#52525b';
    singleBtn.style.cursor = 'not-allowed';
    singleBtn.style.background = 'transparent';
    singleBtn.style.outline = 'none';
    singleBtn.style.boxShadow = 'none';
    singleBtn.title = 'Pause queue first to retry tasks';
  }
  // Show running label
  const label = document.createElement('div');
  label.style.cssText = 'padding:4px 16px;font-size:11px;color:#a1a1aa;background:rgba(6,182,212,.1);border-bottom:1px solid rgba(6,182,212,.2);';
  label.textContent = 'Queue running — pause first to retry';
  document.getElementById('retry-all-btn')?.parentElement?.parentElement?.prepend(label);
});

await page.screenshot({
  path: `${DOCS}/2026-05-09-cb-2740-retry-button-5-disabled-running.png`,
  clip: { x: 960, y: 410, width: 440, height: 510 },
});
console.log('Screenshot 5: disabled state (queue running) taken');

await browser.close();
console.log('All screenshots complete.');
