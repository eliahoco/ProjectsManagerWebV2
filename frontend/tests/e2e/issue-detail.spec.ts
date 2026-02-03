import { test, expect, Page } from '@playwright/test';

/**
 * Issue Detail Page End-to-End Tests
 *
 * Tests cover the full-page issue detail view at /codeboard/issues/[id]:
 * - Page loading and navigation
 * - Issue properties display and editing
 * - Tab navigation (Details, Activity, Comments)
 * - Child issues display for Epics/Stories
 * - Status/Priority/Type updates
 * - Breadcrumb navigation
 */

// Test data for API mocking
const testProject = {
  id: 'test-project-1',
  name: 'Test Project',
  path: '/test/path',
  description: 'Test project for issue detail testing',
};

const testEpicIssue = {
  id: 'test-epic-1',
  key: 'TEST-1',
  title: 'Test Epic Issue',
  description: 'This is a test epic description with detailed information.',
  type: 'EPIC',
  status: 'IN_PROGRESS',
  priority: 'HIGH',
  sequence: 1,
  storyPoints: 13,
  assignee: 'john.doe',
  reporter: 'admin',
  projectId: 'test-project-1',
  labels: 'frontend,testing',
  createdAt: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
  updatedAt: new Date().toISOString(),
  startedAt: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
  children: [
    {
      id: 'test-story-1',
      key: 'TEST-2',
      title: 'Child Story',
      type: 'STORY',
      status: 'TODO',
      sequence: 1,
    },
    {
      id: 'test-task-1',
      key: 'TEST-3',
      title: 'Child Task',
      type: 'TASK',
      status: 'DONE',
      sequence: 2,
    },
  ],
};

const testTaskIssue = {
  id: 'test-task-2',
  key: 'TEST-4',
  title: 'Test Task Issue',
  description: 'A standalone task for testing.',
  type: 'TASK',
  status: 'TODO',
  priority: 'MEDIUM',
  sequence: 4,
  storyPoints: 3,
  assignee: 'jane.doe',
  reporter: 'admin',
  projectId: 'test-project-1',
  parentId: 'test-epic-1',
  createdAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
  updatedAt: new Date().toISOString(),
};

// Helper to set up API mocks
async function setupApiMocks(page: Page, issue: typeof testEpicIssue | typeof testTaskIssue) {
  // Mock projects endpoint
  await page.route('**/api/codeboard/projects', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([testProject]),
      });
    } else {
      await route.continue();
    }
  });

  // Mock single issue endpoint
  await page.route(`**/api/codeboard/issues/${issue.id}*`, async (route) => {
    const method = route.request().method();

    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(issue),
      });
    } else if (method === 'PATCH') {
      const body = route.request().postDataJSON();
      const updatedIssue = { ...issue, ...body, updatedAt: new Date().toISOString() };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(updatedIssue),
      });
    } else if (method === 'DELETE') {
      await route.fulfill({ status: 204 });
    } else {
      await route.continue();
    }
  });

  // Mock linked commits
  await page.route(`**/api/codeboard/issues/${issue.id}/commits*`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  // Mock comments
  await page.route(`**/api/codeboard/issues/${issue.id}/comments*`, async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    } else {
      await route.continue();
    }
  });

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
}

test.describe('Issue Detail Page', () => {
  test.describe('Page Loading', () => {
    test('should load and display issue details', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      // Wait for page to load
      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Verify title is displayed
      await expect(page.locator(`h1:has-text("${testEpicIssue.title}")`)).toBeVisible();

      // Verify description is displayed
      await expect(page.locator(`text=${testEpicIssue.description}`)).toBeVisible();
    });

    test('should display back button to CodeBoard', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Back button should be visible
      const backButton = page.locator('a[href="/codeboard"]').first();
      await expect(backButton).toBeVisible();
    });

    test('should display breadcrumb with project name', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Project name should be in breadcrumb
      await expect(page.locator(`text=${testProject.name}`)).toBeVisible();
    });

    test('should show 404 for non-existent issue', async ({ page }) => {
      // Mock 404 response
      await page.route('**/api/codeboard/issues/non-existent-id*', async (route) => {
        await route.fulfill({ status: 404 });
      });
      await page.route('**/api/codeboard/projects', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([testProject]),
        });
      });

      await page.goto('/codeboard/issues/non-existent-id');

      // Should show error message
      await expect(page.locator('text=Issue not found')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('text=Back to CodeBoard')).toBeVisible();
    });
  });

  test.describe('Issue Properties', () => {
    test('should display status dropdown', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Status dropdown should be visible
      const statusSelect = page.locator('select').first();
      await expect(statusSelect).toBeVisible();
      await expect(statusSelect).toHaveValue(testEpicIssue.status);
    });

    test('should display priority dropdown', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Priority should be displayed
      const prioritySelect = page.locator('select').nth(1);
      await expect(prioritySelect).toBeVisible();
    });

    test('should display type dropdown', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Type should be displayed
      const typeSelect = page.locator('select').nth(2);
      await expect(typeSelect).toBeVisible();
    });

    test('should display story points', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Story points should be displayed
      await expect(page.locator(`text=${testEpicIssue.storyPoints}`)).toBeVisible();
    });

    test('should display assignee', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Assignee should be displayed
      await expect(page.locator(`text=${testEpicIssue.assignee}`)).toBeVisible();
    });

    test('should display labels', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Labels should be displayed
      await expect(page.locator('text=frontend')).toBeVisible();
      await expect(page.locator('text=testing')).toBeVisible();
    });

    test('should display dates', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Created date label should be visible
      await expect(page.locator('text=Created')).toBeVisible();
    });
  });

  test.describe('Status Updates', () => {
    test('should update status via dropdown', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Change status
      const statusSelect = page.locator('select').first();
      await statusSelect.selectOption('DONE');

      // Wait for update
      await page.waitForTimeout(500);
      await expect(statusSelect).toHaveValue('DONE');
    });

    test('should update priority via dropdown', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Change priority
      const prioritySelect = page.locator('select').nth(1);
      await prioritySelect.selectOption('CRITICAL');

      // Wait for update
      await page.waitForTimeout(500);
      await expect(prioritySelect).toHaveValue('CRITICAL');
    });
  });

  test.describe('Edit Mode', () => {
    test('should enter edit mode when clicking edit button', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Click edit button
      const editButton = page.locator('button').filter({ has: page.locator('svg.lucide-edit-2') });
      await editButton.click();

      // Edit inputs should appear
      await expect(page.locator('input[type="text"]').first()).toBeVisible();
      await expect(page.locator('textarea')).toBeVisible();
    });

    test('should save changes in edit mode', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Click edit button
      const editButton = page.locator('button').filter({ has: page.locator('svg.lucide-edit-2') });
      await editButton.click();

      // Modify title
      const titleInput = page.locator('input[type="text"]').first();
      await titleInput.clear();
      await titleInput.fill('Updated Epic Title');

      // Click save
      await page.click('button:has-text("Save")');

      // Wait for save to complete
      await page.waitForTimeout(500);

      // Should exit edit mode
      await expect(page.locator('h1:has-text("Updated Epic Title")')).toBeVisible();
    });

    test('should cancel edit mode', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Click edit button
      const editButton = page.locator('button').filter({ has: page.locator('svg.lucide-edit-2') });
      await editButton.click();

      // Modify title
      const titleInput = page.locator('input[type="text"]').first();
      await titleInput.clear();
      await titleInput.fill('Should Not Be Saved');

      // Click cancel
      await page.click('button:has-text("Cancel")');

      // Should exit edit mode and show original title
      await expect(page.locator(`h1:has-text("${testEpicIssue.title}")`)).toBeVisible();
    });
  });

  test.describe('Tab Navigation', () => {
    test('should switch to Activity tab', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Click Activity tab
      await page.click('button:has-text("Activity")');

      // Activity tab should be active
      const activityTab = page.locator('button:has-text("Activity")');
      await expect(activityTab).toHaveClass(/border-cyan-500/);
    });

    test('should switch to Comments tab', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Click Comments tab
      await page.click('button:has-text("Comments")');

      // Comments tab should be active
      const commentsTab = page.locator('button:has-text("Comments")');
      await expect(commentsTab).toHaveClass(/border-cyan-500/);
    });

    test('should switch back to Details tab', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Switch to Activity then back to Details
      await page.click('button:has-text("Activity")');
      await page.click('button:has-text("Details")');

      // Details tab should be active
      const detailsTab = page.locator('button:has-text("Details")');
      await expect(detailsTab).toHaveClass(/border-cyan-500/);
    });
  });

  test.describe('Child Issues (Epic/Story)', () => {
    test('should display child issues for Epic', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Child issues section should be visible
      await expect(page.locator('text=Stories & Tasks')).toBeVisible();

      // Child issues should be listed
      await expect(page.locator('text=Child Story')).toBeVisible();
      await expect(page.locator('text=Child Task')).toBeVisible();
    });

    test('should navigate to child issue when clicked', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);

      // Also mock the child issue
      await page.route('**/api/codeboard/issues/test-story-1*', async (route) => {
        if (route.request().method() === 'GET') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: 'test-story-1',
              key: 'TEST-2',
              title: 'Child Story',
              type: 'STORY',
              status: 'TODO',
              priority: 'MEDIUM',
              projectId: 'test-project-1',
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
            }),
          });
        }
      });

      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Click on child issue
      await page.click('a:has-text("Child Story")');

      // Should navigate to child issue page
      await expect(page).toHaveURL(/\/codeboard\/issues\/test-story-1/);
    });
  });

  test.describe('Parent Issue Link', () => {
    test('should display parent issue link when issue has parent', async ({ page }) => {
      await setupApiMocks(page, testTaskIssue);
      await page.goto(`/codeboard/issues/${testTaskIssue.id}`);

      await expect(page.locator(`text=${testTaskIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Parent issue link should be visible
      await expect(page.locator('text=Parent Issue')).toBeVisible();
      await expect(page.locator('text=View Parent Issue')).toBeVisible();
    });
  });

  test.describe('Delete Issue', () => {
    test('should delete issue with confirmation', async ({ page }) => {
      await setupApiMocks(page, testTaskIssue);
      await page.goto(`/codeboard/issues/${testTaskIssue.id}`);

      await expect(page.locator(`text=${testTaskIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Set up dialog handler
      page.once('dialog', async (dialog) => {
        expect(dialog.type()).toBe('confirm');
        await dialog.accept();
      });

      // Click delete button
      const deleteButton = page.locator('button').filter({ has: page.locator('svg.lucide-trash-2') });
      await deleteButton.click();

      // Should redirect to CodeBoard
      await expect(page).toHaveURL('/codeboard', { timeout: 10000 });
    });

    test('should not delete issue when confirmation is declined', async ({ page }) => {
      await setupApiMocks(page, testTaskIssue);
      await page.goto(`/codeboard/issues/${testTaskIssue.id}`);

      await expect(page.locator(`text=${testTaskIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Set up dialog handler to decline
      page.once('dialog', async (dialog) => {
        await dialog.dismiss();
      });

      // Click delete button
      const deleteButton = page.locator('button').filter({ has: page.locator('svg.lucide-trash-2') });
      await deleteButton.click();

      // Should stay on the page
      await expect(page.locator(`text=${testTaskIssue.key}`)).toBeVisible();
    });
  });

  test.describe('Navigation', () => {
    test('should navigate back to CodeBoard via back button', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Click back button
      await page.click('a[href="/codeboard"]');

      // Should navigate to CodeBoard
      await expect(page).toHaveURL('/codeboard');
    });

    test('should handle browser back navigation', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);

      // Navigate to CodeBoard first, then to issue detail
      await page.goto('/codeboard');
      await page.waitForSelector('h1:has-text("CodeBoard")');

      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);
      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Go back
      await page.goBack();

      // Should be on CodeBoard
      await expect(page.locator('h1:has-text("CodeBoard")')).toBeVisible();
    });
  });

  test.describe('Execute Button', () => {
    test('should display Execute button', async ({ page }) => {
      await setupApiMocks(page, testEpicIssue);
      await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

      await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 10000 });

      // Execute button should be visible
      await expect(page.locator('button:has-text("Execute")')).toBeVisible();
    });
  });
});

test.describe('Issue Detail Page - Error Handling', () => {
  test('should handle network errors gracefully', async ({ page }) => {
    // Mock network error
    await page.route('**/api/**', (route) => route.abort('connectionfailed'));

    await page.goto('/codeboard/issues/test-issue-1');

    // Should show error state
    await expect(page.locator('text=Issue not found').or(page.locator('text=error'))).toBeVisible({
      timeout: 10000,
    });
  });

  test('should handle slow API responses', async ({ page }) => {
    // Mock slow response
    await page.route('**/api/codeboard/issues/*', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(testEpicIssue),
      });
    });
    await page.route('**/api/codeboard/projects', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([testProject]),
      });
    });

    await page.goto(`/codeboard/issues/${testEpicIssue.id}`);

    // Should show loading state initially
    const loadingSpinner = page.locator('.animate-spin');
    await expect(loadingSpinner).toBeVisible({ timeout: 1000 });

    // Eventually should show the issue
    await expect(page.locator(`text=${testEpicIssue.key}`)).toBeVisible({ timeout: 15000 });
  });
});
