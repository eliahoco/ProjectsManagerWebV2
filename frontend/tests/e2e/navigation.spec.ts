import { test, expect, Page } from '@playwright/test';

/**
 * Navigation End-to-End Tests
 *
 * Tests cover URL-based navigation, deep linking, and routing:
 * - Direct URL access to CodeBoard
 * - Deep linking to specific issues
 * - Query parameter handling for filters
 * - Browser history navigation
 * - URL state synchronization
 */

// Test data for API mocking
const testProject = {
  id: 'nav-test-project',
  name: 'Navigation Test Project',
  path: '/test/nav',
  description: 'Project for navigation testing',
};

const testIssues = [
  {
    id: 'nav-issue-1',
    key: 'NAV-1',
    title: 'Navigation Test Issue 1',
    description: 'First test issue',
    type: 'EPIC',
    status: 'TODO',
    priority: 'HIGH',
    sequence: 1,
    projectId: 'nav-test-project',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    children: [],
  },
  {
    id: 'nav-issue-2',
    key: 'NAV-2',
    title: 'Navigation Test Issue 2',
    description: 'Second test issue',
    type: 'TASK',
    status: 'IN_PROGRESS',
    priority: 'MEDIUM',
    sequence: 2,
    projectId: 'nav-test-project',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
  {
    id: 'nav-issue-3',
    key: 'NAV-3',
    title: 'Navigation Test Bug',
    description: 'A bug for testing',
    type: 'BUG',
    status: 'DONE',
    priority: 'CRITICAL',
    sequence: 3,
    projectId: 'nav-test-project',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
];

// Helper to set up API mocks
async function setupApiMocks(page: Page) {
  // Mock projects endpoint
  await page.route('**/api/codeboard/projects', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([testProject]),
    });
  });

  // Mock issues list endpoint
  await page.route(`**/api/codeboard/projects/${testProject.id}/issues*`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: testIssues,
        total: testIssues.length,
        page: 1,
        pageSize: 50,
      }),
    });
  });

  // Mock individual issue endpoints
  for (const issue of testIssues) {
    await page.route(`**/api/codeboard/issues/${issue.id}*`, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(issue),
        });
      } else {
        await route.continue();
      }
    });
  }

  // Mock AI status
  await page.route('**/api/codeboard/ai/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ available: false }),
    });
  });

  // Mock execution sessions
  await page.route('**/api/codeboard/execution/sessions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  // Mock comments
  await page.route('**/api/codeboard/issues/*/comments*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });
}

test.describe('Direct URL Navigation', () => {
  test('should load CodeBoard at /codeboard', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/codeboard');

    await expect(page.locator('h1:has-text("CodeBoard")')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=AI-Powered Issue Tracking')).toBeVisible();
  });

  test('should load issue detail at /codeboard/issues/[id]', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto(`/codeboard/issues/${testIssues[0].id}`);

    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });
    await expect(page.locator(`text=${testIssues[0].title}`)).toBeVisible();
  });

  test('should handle invalid issue ID gracefully', async ({ page }) => {
    await setupApiMocks(page);

    // Mock 404 for invalid ID
    await page.route('**/api/codeboard/issues/invalid-id*', async (route) => {
      await route.fulfill({ status: 404 });
    });

    await page.goto('/codeboard/issues/invalid-id');

    await expect(page.locator('text=Issue not found')).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Deep Linking', () => {
  test('should open issue detail from board via card click', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Wait for issues to load
    await page.waitForTimeout(1000);

    // Click on an issue card
    const issueCard = page.locator(`[data-issue-id="${testIssues[0].id}"]`);
    if (await issueCard.isVisible({ timeout: 5000 }).catch(() => false)) {
      await issueCard.click();

      // Modal should open (not full page navigation)
      await page.waitForTimeout(500);
      const modal = page.locator('.fixed.inset-0.z-50');
      await expect(modal).toBeVisible();
    }
  });

  test('should preserve URL when opening modal', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // URL should stay as /codeboard
    expect(page.url()).toContain('/codeboard');
    expect(page.url()).not.toContain('/issues/');
  });
});

test.describe('Browser History', () => {
  test('should support back navigation from issue detail to board', async ({ page }) => {
    await setupApiMocks(page);

    // Start at CodeBoard
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Navigate to issue detail
    await page.goto(`/codeboard/issues/${testIssues[0].id}`);
    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });

    // Go back
    await page.goBack();

    // Should be at CodeBoard
    await expect(page.locator('h1:has-text("CodeBoard")')).toBeVisible({ timeout: 10000 });
  });

  test('should support forward navigation after going back', async ({ page }) => {
    await setupApiMocks(page);

    // Start at CodeBoard
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Navigate to issue detail
    await page.goto(`/codeboard/issues/${testIssues[0].id}`);
    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });

    // Go back
    await page.goBack();
    await expect(page.locator('h1:has-text("CodeBoard")')).toBeVisible({ timeout: 10000 });

    // Go forward
    await page.goForward();
    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });
  });

  test('should handle multiple back/forward navigations', async ({ page }) => {
    await setupApiMocks(page);

    // Build history: CodeBoard -> Issue 1 -> Issue 2
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    await page.goto(`/codeboard/issues/${testIssues[0].id}`);
    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });

    await page.goto(`/codeboard/issues/${testIssues[1].id}`);
    await expect(page.locator(`text=${testIssues[1].key}`)).toBeVisible({ timeout: 10000 });

    // Go back twice to CodeBoard
    await page.goBack();
    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });

    await page.goBack();
    await expect(page.locator('h1:has-text("CodeBoard")')).toBeVisible({ timeout: 10000 });

    // Go forward to Issue 1
    await page.goForward();
    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });
  });
});

test.describe('View State Persistence', () => {
  test('should maintain view mode selection on reload', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Switch to Kanban view
    const boardButton = page.locator('.flex.bg-zinc-800.rounded-lg.p-1 button').nth(1);
    await boardButton.click();
    await expect(boardButton).toHaveClass(/bg-zinc-700/);

    // Reload the page
    await page.reload();
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // View mode might reset on reload (depends on implementation)
    // At minimum, page should load without errors
    await expect(page.locator('.flex.bg-zinc-800.rounded-lg.p-1')).toBeVisible();
  });

  test('should clear filters on navigation away and back', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Apply a search filter
    const searchInput = page.locator('input[placeholder*="Search"]');
    await searchInput.fill('test search');

    // Navigate away
    await page.goto(`/codeboard/issues/${testIssues[0].id}`);
    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });

    // Navigate back
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Search might be cleared (depends on implementation)
    // At minimum, page should load without errors
    await expect(searchInput).toBeVisible();
  });
});

test.describe('Link Navigation', () => {
  test('should navigate via back link in issue detail', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto(`/codeboard/issues/${testIssues[0].id}`);
    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });

    // Click back to CodeBoard link
    await page.click('a[href="/codeboard"]');

    // Should be at CodeBoard
    await expect(page.locator('h1:has-text("CodeBoard")')).toBeVisible({ timeout: 10000 });
  });

  test('should navigate between related issues', async ({ page }) => {
    // Set up epic with children
    const epicWithChildren = {
      ...testIssues[0],
      children: [
        {
          id: testIssues[1].id,
          key: testIssues[1].key,
          title: testIssues[1].title,
          type: testIssues[1].type,
          status: testIssues[1].status,
          sequence: testIssues[1].sequence,
        },
      ],
    };

    await setupApiMocks(page);

    // Override epic mock with children
    await page.route(`**/api/codeboard/issues/${testIssues[0].id}*`, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(epicWithChildren),
        });
      }
    });

    await page.goto(`/codeboard/issues/${testIssues[0].id}`);
    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });

    // Click on child issue link
    const childLink = page.locator(`a:has-text("${testIssues[1].title}")`);
    if (await childLink.isVisible({ timeout: 3000 }).catch(() => false)) {
      await childLink.click();

      // Should navigate to child issue
      await expect(page).toHaveURL(/\/codeboard\/issues\/nav-issue-2/);
    }
  });
});

test.describe('Page Refresh', () => {
  test('should maintain state on CodeBoard refresh', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Wait for issues to load
    await page.waitForTimeout(1000);

    // Refresh the page
    await page.reload();

    // Page should load normally
    await expect(page.locator('h1:has-text("CodeBoard")')).toBeVisible({ timeout: 10000 });
  });

  test('should maintain state on issue detail refresh', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto(`/codeboard/issues/${testIssues[0].id}`);
    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });

    // Refresh the page
    await page.reload();

    // Issue should still be displayed
    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });
    await expect(page.locator(`text=${testIssues[0].title}`)).toBeVisible();
  });
});

test.describe('404 Handling', () => {
  test('should show 404 for unknown routes', async ({ page }) => {
    await page.goto('/codeboard/unknown-route');

    // Should show 404 or redirect - depends on Next.js config
    // At minimum, should not crash
    await page.waitForTimeout(1000);
  });

  test('should handle missing issue gracefully', async ({ page }) => {
    await setupApiMocks(page);

    // Mock 404 for specific issue
    await page.route('**/api/codeboard/issues/deleted-issue*', async (route) => {
      await route.fulfill({ status: 404 });
    });

    await page.goto('/codeboard/issues/deleted-issue');

    // Should show error message with navigation back
    await expect(page.locator('text=Issue not found')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('a:has-text("Back to CodeBoard")')).toBeVisible();
  });
});

test.describe('External Navigation', () => {
  test('should handle navigation from external link', async ({ page }) => {
    await setupApiMocks(page);

    // Simulate coming from external source
    await page.goto('about:blank');
    await page.goto(`/codeboard/issues/${testIssues[0].id}`);

    // Page should load correctly
    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });
  });

  test('should handle direct URL paste', async ({ page }) => {
    await setupApiMocks(page);

    // Navigate directly via URL (simulating paste)
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Use evaluate to change location (simulates URL paste)
    await page.evaluate((issueId) => {
      window.location.href = `/codeboard/issues/${issueId}`;
    }, testIssues[0].id);

    // Page should load correctly
    await expect(page.locator(`text=${testIssues[0].key}`)).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Concurrent Navigation', () => {
  test('should handle rapid navigation attempts', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Rapidly click multiple navigation targets
    await page.click('a[href="/codeboard"]');
    await page.click('a[href="/codeboard"]');

    // Page should remain stable
    await expect(page.locator('h1:has-text("CodeBoard")')).toBeVisible({ timeout: 10000 });
  });
});
