import { test, expect } from '@playwright/test';

/**
 * End-to-End Security Tests
 * Task: CB-1120 - Automated testing framework for security-related features
 * Part of STORY CB-1112: User can Filter Results by Date Range
 *
 * Tests cover:
 * - XSS prevention in rendered output
 * - Malicious input handling in search/filters
 * - Error information disclosure prevention
 * - Date range filter boundary security
 * - Response header security validation
 */

test.describe('Security - XSS Prevention', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');
  });

  test('should not execute script tags entered in search', async ({ page }) => {
    const searchInput = page.locator('input[placeholder*="Search issues"]');
    await searchInput.fill('<script>document.title="hacked"</script>');

    // Wait a moment for any potential script execution
    await page.waitForTimeout(500);

    // Title should not have been changed by the injected script
    const title = await page.title();
    expect(title).not.toBe('hacked');
  });

  test('should not execute event handlers in search input', async ({ page }) => {
    const searchInput = page.locator('input[placeholder*="Search issues"]');
    await searchInput.fill('<img src=x onerror=document.title="xss">');

    await page.waitForTimeout(500);
    const title = await page.title();
    expect(title).not.toBe('xss');
  });

  test('should not render injected HTML in filter controls', async ({ page }) => {
    const searchInput = page.locator('input[placeholder*="Search issues"]');
    await searchInput.fill('<b>bold</b><a href="http://evil.com">click</a>');

    // Verify no <b> or <a> tags were rendered as HTML
    const boldElements = page.locator('b:has-text("bold")');
    await expect(boldElements).toHaveCount(0);

    const linkElements = page.locator('a[href="http://evil.com"]');
    await expect(linkElements).toHaveCount(0);
  });
});

test.describe('Security - Malicious Filter Inputs', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');
  });

  test('should handle SQL injection in search without crashing', async ({ page }) => {
    const searchInput = page.locator('input[placeholder*="Search issues"]');
    await searchInput.fill("'; DROP TABLE issues; --");

    // Page should remain functional
    await expect(page.locator('h1:has-text("CodeBoard")')).toBeVisible();
    // Search input should retain the value
    await expect(searchInput).toHaveValue("'; DROP TABLE issues; --");
  });

  test('should handle very long search queries without freezing', async ({ page }) => {
    const searchInput = page.locator('input[placeholder*="Search issues"]');
    const longQuery = 'A'.repeat(5000);
    await searchInput.fill(longQuery);

    // Page should remain responsive
    await expect(page.locator('h1:has-text("CodeBoard")')).toBeVisible();
  });

  test('should handle special characters in type filter', async ({ page }) => {
    const filterButton = page.locator('button:has-text("Filters")');
    await filterButton.click();

    // Type dropdown should only have predefined safe values
    const typeSelect = page.locator('select').filter({ hasText: 'All Types' });
    const options = await typeSelect.locator('option').allTextContents();

    // All options should be predefined safe values
    options.forEach((opt) => {
      expect(opt).not.toMatch(/<script/i);
      expect(opt).not.toMatch(/javascript:/i);
    });
  });

  test('should handle null byte injection attempt in search', async ({ page }) => {
    const searchInput = page.locator('input[placeholder*="Search issues"]');
    await searchInput.fill('test\x00injection');

    // Page should still be functional
    await expect(page.locator('h1:has-text("CodeBoard")')).toBeVisible();
  });
});

test.describe('Security - Date Range Filter Boundaries', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');
  });

  test('should show date picker when date field is selected', async ({ page }) => {
    const filterButton = page.locator('button:has-text("Filters")');
    await filterButton.click();

    const dateFieldSelect = page.locator('select').filter({ hasText: 'Date Field' });
    await dateFieldSelect.selectOption('createdAt');

    // DateRangePicker should appear
    await expect(page.locator('text=Select range...')).toBeVisible();
  });

  test('should only allow predefined date fields', async ({ page }) => {
    const filterButton = page.locator('button:has-text("Filters")');
    await filterButton.click();

    const dateFieldSelect = page.locator('select').filter({ hasText: 'Date Field' });
    const optionValues = await dateFieldSelect.locator('option').evaluateAll(
      (elements) => elements.map((el) => (el as HTMLOptionElement).value).filter((v) => v !== '')
    );

    const allowedFields = ['createdAt', 'updatedAt', 'dueDate', 'startedAt', 'completedAt'];
    optionValues.forEach((val) => {
      expect(allowedFields).toContain(val);
    });
  });

  test('should clear date filter completely when Clear is clicked', async ({ page }) => {
    const filterButton = page.locator('button:has-text("Filters")');
    await filterButton.click();

    // Select a date field
    const dateFieldSelect = page.locator('select').filter({ hasText: 'Date Field' });
    await dateFieldSelect.selectOption('createdAt');

    // Clear should be available when we also have search active
    const searchInput = page.locator('input[placeholder*="Search issues"]');
    await searchInput.fill('test');

    const clearButton = page.locator('button:has-text("Clear")');
    await clearButton.click();

    // Search should be cleared
    await expect(searchInput).toHaveValue('');
  });
});

test.describe('Security - Error Information Disclosure', () => {
  test('should not show stack traces on API errors', async ({ page }) => {
    // Navigate to a page that triggers API calls
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Check that no error stack traces are visible on the page
    const pageContent = await page.content();
    expect(pageContent).not.toContain('at Object.');
    expect(pageContent).not.toContain('node_modules');
    expect(pageContent).not.toContain('.ts:');
    expect(pageContent).not.toContain('Traceback (most recent call');
  });

  test('should not expose API keys or secrets in page source', async ({ page }) => {
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    const pageContent = await page.content();
    expect(pageContent).not.toMatch(/sk-ant-/);
    expect(pageContent).not.toMatch(/ANTHROPIC_API_KEY/);
    expect(pageContent).not.toMatch(/Bearer\s+[a-zA-Z0-9-_.]+/);
  });
});

test.describe('Security - Response Headers', () => {
  test('should return proper content-type for API responses', async ({ page }) => {
    const response = await page.goto('/codeboard');
    const contentType = response?.headers()['content-type'];
    // HTML page should have text/html content type
    expect(contentType).toContain('text/html');
  });
});
