import { test, expect, Page } from '@playwright/test';

/**
 * CodeBoard CRUD Operations E2E Tests
 *
 * Tests cover the complete lifecycle of issue management:
 * - Create: Fill form and submit new issue
 * - Read: Open detail modal and verify content
 * - Update: Edit issue and save changes
 * - Delete: Delete issue with confirmation
 *
 * These tests use API mocking to ensure reliable, isolated testing.
 */

// Test data
const testProject = {
  id: 'test-project-1',
  name: 'Test Project',
  path: '/test/path',
  description: 'Test project for CRUD testing',
};

const testIssue = {
  id: 'test-issue-1',
  key: 'TEST-1',
  title: 'Test Issue for CRUD',
  description: 'This is a test issue description',
  type: 'TASK',
  status: 'TODO',
  priority: 'HIGH',
  sequence: 1,
  storyPoints: 3,
  assignee: 'test-user',
  reporter: 'admin',
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
};

// Helper to set up API mocks
async function setupApiMocks(page: Page, issues: typeof testIssue[] = [testIssue]) {
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

  // Mock issues endpoint
  await page.route(`**/api/codeboard/projects/${testProject.id}/issues*`, async (route) => {
    const method = route.request().method();

    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: issues,
          total: issues.length,
          page: 1,
          pageSize: 50,
        }),
      });
    } else if (method === 'POST') {
      // Handle create
      const body = route.request().postDataJSON();
      const newIssue = {
        ...testIssue,
        id: `new-issue-${Date.now()}`,
        key: `TEST-${issues.length + 1}`,
        ...body,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      issues.push(newIssue);
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(newIssue),
      });
    } else {
      await route.continue();
    }
  });

  // Mock single issue endpoint for updates and deletes
  await page.route('**/api/codeboard/issues/*', async (route) => {
    const method = route.request().method();
    const url = route.request().url();
    const issueId = url.split('/').pop()?.split('?')[0];

    if (method === 'GET') {
      const issue = issues.find((i) => i.id === issueId);
      if (issue) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(issue),
        });
      } else {
        await route.fulfill({ status: 404 });
      }
    } else if (method === 'PATCH') {
      const body = route.request().postDataJSON();
      const issueIndex = issues.findIndex((i) => i.id === issueId);
      if (issueIndex !== -1) {
        issues[issueIndex] = { ...issues[issueIndex], ...body, updatedAt: new Date().toISOString() };
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(issues[issueIndex]),
        });
      } else {
        await route.fulfill({ status: 404 });
      }
    } else if (method === 'DELETE') {
      const issueIndex = issues.findIndex((i) => i.id === issueId);
      if (issueIndex !== -1) {
        issues.splice(issueIndex, 1);
        await route.fulfill({ status: 204 });
      } else {
        await route.fulfill({ status: 404 });
      }
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

test.describe('Issue CRUD Operations', () => {
  test('should create a new issue', async ({ page }) => {
    const issues: typeof testIssue[] = [];
    await setupApiMocks(page, issues);

    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Wait for the page to stabilize
    await page.waitForTimeout(500);

    // Click the New Issue button
    await page.click('button:has-text("New Issue")');

    // Wait for the create modal to appear
    await expect(page.locator('h2:has-text("Create Issue")')).toBeVisible();

    // Fill in the title
    const titleInput = page.locator('input[placeholder*="What needs to be done"]');
    await titleInput.fill('New Test Issue');

    // Fill in description
    const descriptionInput = page.locator('textarea[placeholder*="Add more details"]');
    await descriptionInput.fill('Test description for new issue');

    // Select issue type
    const modal = page.locator('.fixed.inset-0.z-50');
    const typeSelect = modal.locator('select').first();
    await typeSelect.selectOption('TASK');

    // Select priority
    const prioritySelect = modal.locator('select').nth(1);
    await prioritySelect.selectOption('HIGH');

    // Click Create Issue button
    const submitButton = page.locator('button:has-text("Create Issue")');
    await expect(submitButton).toBeEnabled();
    await submitButton.click();

    // Wait for modal to close (indicates success)
    await expect(page.locator('h2:has-text("Create Issue")')).not.toBeVisible({ timeout: 10000 });

    // Verify issue was created (check that the issues array was updated)
    expect(issues.length).toBe(1);
    expect(issues[0].title).toBe('New Test Issue');
  });

  test('should read issue details', async ({ page }) => {
    const issues = [{ ...testIssue }];
    await setupApiMocks(page, issues);

    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Wait for the issue to be visible
    await expect(page.locator(`text=${testIssue.title}`)).toBeVisible({ timeout: 10000 });

    // Find and click the issue card
    const issueCard = page.locator(`[data-issue-id="${testIssue.id}"]`);
    await issueCard.click();

    // Wait for the detail modal to appear
    await page.waitForTimeout(500);

    // Verify the modal shows the issue details
    const modal = page.locator('.fixed.inset-0.z-50');
    await expect(modal).toBeVisible();

    // Verify title is displayed
    await expect(modal.locator(`text=${testIssue.title}`)).toBeVisible();

    // Verify description is displayed
    await expect(modal.locator(`text=${testIssue.description}`)).toBeVisible();

    // Verify issue key is displayed
    await expect(modal.locator(`text=${testIssue.key}`)).toBeVisible();

    // Close the modal
    await page.keyboard.press('Escape');
    await expect(modal).not.toBeVisible({ timeout: 5000 });
  });

  test('should update an issue', async ({ page }) => {
    const issues = [{ ...testIssue }];
    await setupApiMocks(page, issues);

    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Wait for the issue to be visible
    await expect(page.locator(`text=${testIssue.title}`)).toBeVisible({ timeout: 10000 });

    // Find and click the issue card to open detail modal
    const issueCard = page.locator(`[data-issue-id="${testIssue.id}"]`);
    await issueCard.click();

    // Wait for the detail modal
    await page.waitForTimeout(500);
    const modal = page.locator('.fixed.inset-0.z-50');
    await expect(modal).toBeVisible();

    // Click the edit button (Edit2 icon button)
    const editButton = modal.locator('button').filter({ has: page.locator('svg.lucide-edit-2') });
    await editButton.click();

    // Wait for edit mode to activate
    await page.waitForTimeout(300);

    // Update the title (input appears when in edit mode)
    const titleInput = modal.locator('input[type="text"]').first();
    await titleInput.clear();
    await titleInput.fill('Updated Issue Title');

    // Click Save button
    const saveButton = modal.locator('button:has-text("Save")');
    await saveButton.click();

    // Wait for save to complete
    await page.waitForTimeout(500);

    // Verify the title was updated in the mock data
    expect(issues[0].title).toBe('Updated Issue Title');

    // Verify the updated title is displayed in the modal
    await expect(modal.locator('text=Updated Issue Title')).toBeVisible();

    // Close modal
    await page.keyboard.press('Escape');
  });

  test('should delete an issue', async ({ page }) => {
    const issues = [{ ...testIssue }];
    await setupApiMocks(page, issues);

    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Wait for the issue to be visible
    await expect(page.locator(`text=${testIssue.title}`)).toBeVisible({ timeout: 10000 });

    // Verify we have 1 issue initially
    expect(issues.length).toBe(1);

    // Find and click the issue card to open detail modal
    const issueCard = page.locator(`[data-issue-id="${testIssue.id}"]`);
    await issueCard.click();

    // Wait for the detail modal
    await page.waitForTimeout(500);
    const modal = page.locator('.fixed.inset-0.z-50');
    await expect(modal).toBeVisible();

    // Set up dialog handler BEFORE clicking delete (handles the confirm dialog)
    page.once('dialog', async (dialog) => {
      expect(dialog.type()).toBe('confirm');
      await dialog.accept();
    });

    // Click the delete button (Trash2 icon button)
    const deleteButton = modal.locator('button').filter({ has: page.locator('svg.lucide-trash-2') });
    await deleteButton.click();

    // Wait for deletion to complete and modal to close
    await expect(modal).not.toBeVisible({ timeout: 10000 });

    // Verify the issue was deleted from mock data
    expect(issues.length).toBe(0);
  });
});

test.describe('Issue CRUD - Additional Scenarios', () => {
  test('should create issue with all fields populated', async ({ page }) => {
    const issues: typeof testIssue[] = [];
    await setupApiMocks(page, issues);

    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');
    await page.waitForTimeout(500);

    // Open create modal
    await page.click('button:has-text("New Issue")');
    await expect(page.locator('h2:has-text("Create Issue")')).toBeVisible();

    const modal = page.locator('.fixed.inset-0.z-50');

    // Fill title
    await page.fill('input[placeholder*="What needs to be done"]', 'Full Test Issue');

    // Select type as STORY
    await modal.locator('select').first().selectOption('STORY');

    // Select priority as CRITICAL
    await modal.locator('select').nth(1).selectOption('CRITICAL');

    // Fill story points
    const storyPointsInput = page.locator('input[placeholder="0"]');
    if (await storyPointsInput.isVisible()) {
      await storyPointsInput.fill('5');
    }

    // Fill assignee
    const assigneeInput = page.locator('input[placeholder*="Who will work on this"]');
    if (await assigneeInput.isVisible()) {
      await assigneeInput.fill('test-user');
    }

    // Fill description
    await page.fill('textarea[placeholder*="Add more details"]', 'Full test description with all fields');

    // Submit
    await page.click('button:has-text("Create Issue")');

    // Verify modal closes
    await expect(page.locator('h2:has-text("Create Issue")')).not.toBeVisible({ timeout: 10000 });

    // Verify issue was created with correct data
    expect(issues.length).toBe(1);
    expect(issues[0].title).toBe('Full Test Issue');
    expect(issues[0].type).toBe('STORY');
    expect(issues[0].priority).toBe('CRITICAL');
  });

  test('should update issue status via dropdown', async ({ page }) => {
    const issues = [{ ...testIssue, status: 'TODO' }];
    await setupApiMocks(page, issues);

    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Wait for the issue to be visible
    await expect(page.locator(`text=${testIssue.title}`)).toBeVisible({ timeout: 10000 });

    // Open the issue detail
    const issueCard = page.locator(`[data-issue-id="${testIssue.id}"]`);
    await issueCard.click();
    await page.waitForTimeout(500);

    const modal = page.locator('.fixed.inset-0.z-50');
    await expect(modal).toBeVisible();

    // Find the status dropdown (first select in modal properties area)
    const statusSelect = modal.locator('select').first();

    // Change status to IN_PROGRESS
    await statusSelect.selectOption('IN_PROGRESS');

    // Wait for the update to be saved
    await page.waitForTimeout(500);

    // Verify the status was updated in mock data
    expect(issues[0].status).toBe('IN_PROGRESS');

    // Close modal
    await page.keyboard.press('Escape');
  });

  test('should update issue priority via dropdown', async ({ page }) => {
    const issues = [{ ...testIssue, priority: 'MEDIUM' }];
    await setupApiMocks(page, issues);

    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Wait for the issue to be visible
    await expect(page.locator(`text=${testIssue.title}`)).toBeVisible({ timeout: 10000 });

    // Open the issue detail
    const issueCard = page.locator(`[data-issue-id="${testIssue.id}"]`);
    await issueCard.click();
    await page.waitForTimeout(500);

    const modal = page.locator('.fixed.inset-0.z-50');
    await expect(modal).toBeVisible();

    // Find the priority dropdown (second select in modal properties area)
    const prioritySelect = modal.locator('select').nth(1);

    // Change priority to CRITICAL
    await prioritySelect.selectOption('CRITICAL');

    // Wait for the update to be saved
    await page.waitForTimeout(500);

    // Verify the priority was updated in mock data
    expect(issues[0].priority).toBe('CRITICAL');

    // Close modal
    await page.keyboard.press('Escape');
  });

  test('should cancel issue creation without saving', async ({ page }) => {
    const issues: typeof testIssue[] = [];
    await setupApiMocks(page, issues);

    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');
    await page.waitForTimeout(500);

    // Open create modal
    await page.click('button:has-text("New Issue")');
    await expect(page.locator('h2:has-text("Create Issue")')).toBeVisible();

    // Fill in the title
    await page.fill('input[placeholder*="What needs to be done"]', 'Issue That Should Not Be Created');

    // Click Cancel button
    await page.click('button:has-text("Cancel")');

    // Verify modal closes
    await expect(page.locator('h2:has-text("Create Issue")')).not.toBeVisible({ timeout: 5000 });

    // Verify the issue was NOT created
    expect(issues.length).toBe(0);
  });

  test('should cancel edit without saving changes', async ({ page }) => {
    const originalTitle = testIssue.title;
    const issues = [{ ...testIssue }];
    await setupApiMocks(page, issues);

    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Wait for the issue to be visible
    await expect(page.locator(`text=${testIssue.title}`)).toBeVisible({ timeout: 10000 });

    // Open the issue detail
    const issueCard = page.locator(`[data-issue-id="${testIssue.id}"]`);
    await issueCard.click();
    await page.waitForTimeout(500);

    const modal = page.locator('.fixed.inset-0.z-50');
    await expect(modal).toBeVisible();

    // Click edit button
    const editButton = modal.locator('button').filter({ has: page.locator('svg.lucide-edit-2') });
    await editButton.click();
    await page.waitForTimeout(300);

    // Change the title
    const titleInput = modal.locator('input[type="text"]').first();
    await titleInput.clear();
    await titleInput.fill('This Title Should Not Be Saved');

    // Click Cancel (not Save)
    await modal.locator('button:has-text("Cancel")').click();
    await page.waitForTimeout(300);

    // Verify the original title is still in the data
    expect(issues[0].title).toBe(originalTitle);

    // Verify the original title is still displayed in the modal
    await expect(modal.locator(`text=${originalTitle}`)).toBeVisible();

    // Close modal
    await page.keyboard.press('Escape');
  });

  test('should decline delete confirmation', async ({ page }) => {
    const issues = [{ ...testIssue }];
    await setupApiMocks(page, issues);

    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');

    // Wait for the issue to be visible
    await expect(page.locator(`text=${testIssue.title}`)).toBeVisible({ timeout: 10000 });

    // Open the issue detail
    const issueCard = page.locator(`[data-issue-id="${testIssue.id}"]`);
    await issueCard.click();
    await page.waitForTimeout(500);

    const modal = page.locator('.fixed.inset-0.z-50');
    await expect(modal).toBeVisible();

    // Set up dialog handler to DISMISS (cancel) the deletion
    page.once('dialog', async (dialog) => {
      expect(dialog.type()).toBe('confirm');
      await dialog.dismiss(); // Click "Cancel" on confirm dialog
    });

    // Click delete button
    const deleteButton = modal.locator('button').filter({ has: page.locator('svg.lucide-trash-2') });
    await deleteButton.click();

    // Wait a moment
    await page.waitForTimeout(500);

    // Verify modal is still visible (deletion was cancelled)
    await expect(modal).toBeVisible();

    // Verify the issue still exists in mock data
    expect(issues.length).toBe(1);

    // Close modal
    await page.keyboard.press('Escape');
  });
});
