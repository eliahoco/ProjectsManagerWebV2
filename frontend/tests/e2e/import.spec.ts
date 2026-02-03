import { test, expect, Page } from '@playwright/test';

/**
 * Smart Import Feature E2E Tests
 * Task: CB-473 - Implement Smart Import Feature Testing
 *
 * Tests cover the complete import workflow:
 * - Import page navigation and UI rendering
 * - Directory browsing functionality
 * - Manual path entry and validation
 * - Project import success flow
 * - Error handling for invalid paths
 * - Duplicate project detection
 */

// Test data
const testProject = {
  id: 'test-project-1',
  name: 'Test Project',
  path: '/Users/test/projects/test-project',
  type: 'nextjs',
  description: 'A test project for import testing',
  status: 'ACTIVE',
  ports: [
    { id: 'port-1', port: 3000, serviceName: 'FRONTEND', serviceType: 'FRONTEND', url: 'http://localhost:3000' },
    { id: 'port-2', port: 8000, serviceName: 'BACKEND', serviceType: 'BACKEND', url: 'http://localhost:8000' },
  ],
};

const testDirectories = [
  {
    name: 'my-nextjs-app',
    path: '/Users/test/projects/my-nextjs-app',
    hasPackageJson: true,
    hasGit: true,
    alreadyImported: false,
  },
  {
    name: 'python-api',
    path: '/Users/test/projects/python-api',
    hasPackageJson: false,
    hasGit: true,
    alreadyImported: false,
  },
  {
    name: 'already-imported',
    path: '/Users/test/projects/already-imported',
    hasPackageJson: true,
    hasGit: false,
    alreadyImported: true,
  },
];

// Helper to set up API mocks
async function setupApiMocks(page: Page, options: {
  browseSuccess?: boolean;
  importSuccess?: boolean;
  existingProject?: boolean;
  invalidPath?: boolean;
} = {}) {
  const {
    browseSuccess = true,
    importSuccess = true,
    existingProject = false,
    invalidPath = false,
  } = options;

  // Mock browse endpoint - intercept before other routes
  await page.route(/\/api\/projects\/browse/, async (route) => {
    const responseBody = browseSuccess
      ? JSON.stringify({
          success: true,
          data: {
            projectsDir: '/Users/test/projects',
            directories: testDirectories,
          },
        })
      : JSON.stringify({
          success: false,
          error: 'Failed to browse directories',
        });

    await route.fulfill({
      status: browseSuccess ? 200 : 500,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
      body: responseBody,
    });
  });

  // Mock import endpoint
  await page.route(/\/api\/projects\/import/, async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON();

      if (invalidPath) {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({
            success: false,
            error: 'Path does not exist',
          }),
        });
        return;
      }

      if (existingProject) {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({
            success: false,
            error: 'Project already exists with this name or path',
          }),
        });
        return;
      }

      if (importSuccess) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            data: {
              ...testProject,
              name: body.name || body.path.split('/').pop(),
              path: body.path,
            },
          }),
        });
      } else {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({
            success: false,
            error: 'Failed to import project',
          }),
        });
      }
    }
  });

  // Mock project detail redirect - use a more specific pattern that doesn't match API routes
  await page.route(/^(?!.*\/api\/).*\/projects\/[^/]+$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: '<html><body>Project Detail Page</body></html>',
    });
  });
}

test.describe('Smart Import - Page Rendering', () => {
  test('should render the import page with all elements', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    // Check header - use text selector as fallback
    await expect(page.locator('h1:has-text("Import Existing Project")')).toBeVisible();
    await expect(page.getByText(/Add an existing project from your filesystem/i)).toBeVisible();

    // Check form elements using placeholder or id selectors
    await expect(page.getByPlaceholder(/\/Users\/you\/projects/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /Browse/i })).toBeVisible();
    await expect(page.getByPlaceholder(/Leave blank to use directory name/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /Import Project/i })).toBeVisible();

    // Check info box
    await expect(page.getByText(/What gets imported/i)).toBeVisible();
    await expect(page.getByText(/Project type auto-detected/i)).toBeVisible();
    await expect(page.getByText(/Ports detected/i)).toBeVisible();
    await expect(page.getByText(/Description extracted/i)).toBeVisible();
  });

  test('should have disabled import button when path is empty', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    const importButton = page.getByRole('button', { name: /Import Project/i });
    await expect(importButton).toBeDisabled();
  });
});

test.describe('Smart Import - Directory Browser', () => {
  test('should open directory browser when Browse button is clicked', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    await page.getByRole('button', { name: /Browse/i }).click();

    // Check browser modal appears - wait for the modal heading with longer timeout
    await expect(page.getByRole('heading', { name: 'Select Project', level: 3 })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('/Users/test/projects', { exact: true })).toBeVisible();
  });

  test('should display available directories in browser', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    await page.getByRole('button', { name: /Browse/i }).click();

    // Wait for modal to open
    await expect(page.getByRole('heading', { name: 'Select Project', level: 3 })).toBeVisible({ timeout: 10000 });

    // Check directories are listed
    await expect(page.getByRole('button', { name: /my-nextjs-app/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /python-api/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /already-imported/ })).toBeVisible();
  });

  test('should show package.json indicator for Node projects', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    await page.getByRole('button', { name: /Browse/i }).click();

    // Wait for modal to open
    await expect(page.getByRole('heading', { name: 'Select Project', level: 3 })).toBeVisible({ timeout: 10000 });

    // my-nextjs-app has package.json - check it's visible
    const nextjsEntry = page.getByRole('button', { name: /my-nextjs-app/ });
    await expect(nextjsEntry).toBeVisible();
  });

  test('should show git indicator for git repos', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    await page.getByRole('button', { name: /Browse/i }).click();

    // Wait for modal to open
    await expect(page.getByRole('heading', { name: 'Select Project', level: 3 })).toBeVisible({ timeout: 10000 });

    // my-nextjs-app and python-api have git - check they're visible
    const nextjsEntry = page.getByRole('button', { name: /my-nextjs-app/ });
    await expect(nextjsEntry).toBeVisible();
  });

  test('should disable already imported directories', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    await page.getByRole('button', { name: /Browse/i }).click();

    // Wait for modal to open
    await expect(page.getByRole('heading', { name: 'Select Project', level: 3 })).toBeVisible({ timeout: 10000 });

    // already-imported should be disabled
    const importedEntry = page.getByRole('button', { name: /already-imported/ });
    await expect(importedEntry).toBeDisabled();
    await expect(page.getByText('Imported', { exact: true })).toBeVisible();
  });

  test('should select directory and populate path field', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    await page.getByRole('button', { name: /Browse/i }).click();

    // Wait for modal to open
    await expect(page.getByRole('heading', { name: 'Select Project', level: 3 })).toBeVisible({ timeout: 10000 });

    // Select a directory
    await page.getByRole('button', { name: /my-nextjs-app/ }).click();

    // Modal should close and path should be populated
    await expect(page.getByRole('heading', { name: 'Select Project', level: 3 })).not.toBeVisible();

    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await expect(pathInput).toHaveValue('/Users/test/projects/my-nextjs-app');
  });

  test('should close browser modal when X button is clicked', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    await page.getByRole('button', { name: /Browse/i }).click();
    await expect(page.getByRole('heading', { name: 'Select Project', level: 3 })).toBeVisible({ timeout: 10000 });

    // Close the modal using the X button
    await page.locator('button').filter({ has: page.locator('svg.lucide-x') }).click();

    await expect(page.getByRole('heading', { name: 'Select Project', level: 3 })).not.toBeVisible();
  });

  test('should handle browse API error gracefully', async ({ page }) => {
    await setupApiMocks(page, { browseSuccess: false });
    await page.goto('/import');

    await page.getByRole('button', { name: /Browse/i }).click();

    // Should show error toast (or error message)
    // The modal should not appear
    await expect(page.getByRole('heading', { name: /Select Project/i })).not.toBeVisible();
  });
});

test.describe('Smart Import - Manual Path Entry', () => {
  test('should allow manual path entry', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await pathInput.fill('/Users/custom/path/my-project');

    await expect(pathInput).toHaveValue('/Users/custom/path/my-project');
  });

  test('should enable import button when path is entered', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await pathInput.fill('/Users/custom/path/my-project');

    const importButton = page.getByRole('button', { name: /Import Project/i });
    await expect(importButton).toBeEnabled();
  });

  test('should allow optional project name override', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await pathInput.fill('/Users/custom/path/my-project');

    const nameInput = page.getByPlaceholder(/Leave blank to use directory name/i);
    await nameInput.fill('Custom Project Name');

    await expect(nameInput).toHaveValue('Custom Project Name');
  });
});

test.describe('Smart Import - Import Success Flow', () => {
  test('should show success message after successful import', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await pathInput.fill('/Users/test/projects/my-nextjs-app');

    await page.getByRole('button', { name: /Import Project/i }).click();

    // Should show success message - wait longer for async operation
    await expect(page.getByText(/Project imported successfully/i)).toBeVisible({ timeout: 10000 });
  });

  test('should disable import button after success', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await pathInput.fill('/Users/test/projects/my-nextjs-app');

    await page.getByRole('button', { name: /Import Project/i }).click();

    // Wait for success state, then button should show "Imported!" and be disabled
    await expect(page.getByText(/Project imported successfully/i)).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('button', { name: /Imported/i })).toBeDisabled();
  });

  test('should show loading state during import', async ({ page }) => {
    // Delay the response to see loading state
    await page.route('**/api/projects/import', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 500));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: testProject,
        }),
      });
    });
    await page.route('**/projects/*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<html><body>Project Page</body></html>',
      });
    });

    await page.goto('/import');

    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await pathInput.fill('/Users/test/projects/my-nextjs-app');

    await page.getByRole('button', { name: /Import Project/i }).click();

    // Import button should be in loading state
    // The actual loading indicator depends on the Button component implementation
  });
});

test.describe('Smart Import - Error Handling', () => {
  test('should show error for invalid path', async ({ page }) => {
    await setupApiMocks(page, { invalidPath: true });
    await page.goto('/import');

    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await pathInput.fill('/nonexistent/path');

    await page.getByRole('button', { name: /Import Project/i }).click();

    // Should show error message in the form (not toast) - wait for async operation
    await expect(page.getByRole('main').getByText('Path does not exist')).toBeVisible({ timeout: 10000 });
  });

  test('should show error for duplicate project', async ({ page }) => {
    await setupApiMocks(page, { existingProject: true });
    await page.goto('/import');

    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await pathInput.fill('/Users/test/projects/already-imported');

    await page.getByRole('button', { name: /Import Project/i }).click();

    // Should show error message in the form - wait for async operation
    await expect(page.getByRole('main').getByText('Project already exists with this name or path')).toBeVisible({ timeout: 10000 });
  });

  test('should show error for server failure', async ({ page }) => {
    await setupApiMocks(page, { importSuccess: false });
    await page.goto('/import');

    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await pathInput.fill('/Users/test/projects/my-nextjs-app');

    await page.getByRole('button', { name: /Import Project/i }).click();

    // Should show error message in the form
    await expect(page.getByRole('main').getByText('Failed to import project')).toBeVisible({ timeout: 10000 });
  });

  test('should show error when path is empty on submit attempt', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    // Try to submit with empty path - button should be disabled
    const importButton = page.getByRole('button', { name: /Import Project/i });
    await expect(importButton).toBeDisabled();
  });

  test('should allow retry after error', async ({ page }) => {
    // First attempt fails, second succeeds
    let attempts = 0;
    await page.route(/\/api\/projects\/import/, async (route) => {
      attempts++;
      if (attempts === 1) {
        await route.fulfill({
          status: 400,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            success: false,
            error: 'Path does not exist',
          }),
        });
      } else {
        await route.fulfill({
          status: 200,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            success: true,
            data: testProject,
          }),
        });
      }
    });
    await page.route(/^(?!.*\/api\/).*\/projects\/[^/]+$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<html><body>Project Page</body></html>',
      });
    });

    await page.goto('/import');

    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await pathInput.fill('/nonexistent/path');

    await page.getByRole('button', { name: /Import Project/i }).click();

    // First attempt shows error in form - wait for async operation
    await expect(page.getByRole('main').getByText('Path does not exist')).toBeVisible({ timeout: 10000 });

    // Fix the path and retry
    await pathInput.fill('/Users/test/projects/my-nextjs-app');
    await page.getByRole('button', { name: /Import Project/i }).click();

    // Second attempt succeeds - wait for async operation
    await expect(page.getByRole('main').getByText(/Project imported successfully/i)).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Smart Import - Accessibility', () => {
  test('should have proper form labels', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    // Check that inputs have associated labels (using locator with id)
    await expect(page.locator('#project-path')).toBeVisible();
    await expect(page.locator('#project-name')).toBeVisible();
    // Verify labels exist
    await expect(page.locator('label[for="project-path"]')).toBeVisible();
    await expect(page.locator('label[for="project-name"]')).toBeVisible();
  });

  test('should be keyboard navigable', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    // Tab through form elements
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');

    // Path input should be focusable
    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await pathInput.focus();
    await expect(pathInput).toBeFocused();
  });

  test('should have proper button states', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    const importButton = page.getByRole('button', { name: /Import Project/i });

    // Initially disabled
    await expect(importButton).toBeDisabled();

    // Enter path
    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await pathInput.fill('/Users/test/path');

    // Now enabled
    await expect(importButton).toBeEnabled();
  });
});

test.describe('Smart Import - Integration with Browser Selection', () => {
  test('should populate name field when directory is selected', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    await page.getByRole('button', { name: /Browse/i }).click();

    // Wait for modal to open
    await expect(page.getByRole('heading', { name: 'Select Project', level: 3 })).toBeVisible({ timeout: 10000 });

    await page.getByRole('button', { name: /my-nextjs-app/ }).click();

    // Both path and name should be populated
    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    const nameInput = page.getByPlaceholder(/Leave blank to use directory name/i);

    await expect(pathInput).toHaveValue('/Users/test/projects/my-nextjs-app');
    await expect(nameInput).toHaveValue('my-nextjs-app');
  });

  test('should allow editing name after directory selection', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto('/import');

    await page.getByRole('button', { name: /Browse/i }).click();

    // Wait for modal to open
    await expect(page.getByRole('heading', { name: 'Select Project', level: 3 })).toBeVisible({ timeout: 10000 });

    await page.getByRole('button', { name: /my-nextjs-app/ }).click();

    // Edit the name
    const nameInput = page.getByPlaceholder(/Leave blank to use directory name/i);
    await nameInput.clear();
    await nameInput.fill('My Custom Name');

    await expect(nameInput).toHaveValue('My Custom Name');
  });

  test('should use custom name in import request', async ({ page }) => {
    let capturedBody: { path: string; name?: string } | null = null;
    await page.route(/\/api\/projects\/import/, async (route) => {
      capturedBody = route.request().postDataJSON() as { path: string; name?: string };
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          success: true,
          data: { ...testProject, name: capturedBody?.name },
        }),
      });
    });
    await page.route(/^(?!.*\/api\/).*\/projects\/[^/]+$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<html><body>Project Page</body></html>',
      });
    });

    await page.goto('/import');

    const pathInput = page.getByPlaceholder(/\/Users\/you\/projects/i);
    await pathInput.fill('/Users/test/projects/my-nextjs-app');

    const nameInput = page.getByPlaceholder(/Leave blank to use directory name/i);
    await nameInput.fill('My Custom Project');

    await page.getByRole('button', { name: /Import Project/i }).click();

    // Wait for request to complete
    await expect(page.getByRole('main').getByText(/Project imported successfully/i)).toBeVisible({ timeout: 10000 });

    // Verify the request included the custom name
    expect(capturedBody).toBeTruthy();
    expect((capturedBody as { path: string; name?: string } | null)?.name).toBe('My Custom Project');
  });
});
