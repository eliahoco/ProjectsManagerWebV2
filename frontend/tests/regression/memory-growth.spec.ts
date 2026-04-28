import { test, expect } from '@playwright/test';

test('20× codeboard navigation: RSS growth < 50MB', async ({ page }) => {
  await page.goto('http://localhost:3601/codeboard');
  await page.waitForLoadState('domcontentloaded');
  const before = await page.evaluate(() => (performance as any).memory?.usedJSHeapSize ?? 0);

  for (let i = 0; i < 20; i++) {
    await page.goto('http://localhost:3601/codeboard');
    await page.waitForLoadState('domcontentloaded');
    await page.goto('http://localhost:3601/projects');
    await page.waitForLoadState('domcontentloaded');
  }
  // Force GC hint
  await page.evaluate(() => (window as any).gc?.());
  const after = await page.evaluate(() => (performance as any).memory?.usedJSHeapSize ?? 0);

  if (before === 0) test.skip(true, 'JSHeapSize not available — run chromium with --js-flags=--expose-gc');

  const growthMB = (after - before) / 1024 / 1024;
  console.log(`Heap growth: ${growthMB.toFixed(1)}MB (before=${before}, after=${after})`);
  expect(growthMB).toBeLessThan(50);
});
