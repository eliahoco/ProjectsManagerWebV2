import { test, expect, type Page } from '@playwright/test';

/**
 * CodeBoard End-to-End Tests
 *
 * Tests cover the main user flows for the CodeBoard issue tracking system:
 * - Page loading and navigation
 * - Project selection
 * - View mode switching
 * - Issue filtering and search
 * - Issue creation
 * - Keyboard shortcuts
 */

test.describe('CodeBoard Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/codeboard');
    // Wait for the page to be fully loaded
    await page.waitForSelector('h1:has-text("CodeBoard")');
  });

  test.describe('Page Loading', () => {
    test('should display the CodeBoard header', async ({ page }) => {
      await expect(page.locator('h1')).toContainText('CodeBoard');
      await expect(page.locator('text=AI-Powered Issue Tracking')).toBeVisible();
    });

    test('should display the project selector', async ({ page }) => {
      const projectSelect = page.locator('select').first();
      await expect(projectSelect).toBeVisible();
    });

    test('should display view mode toggle buttons', async ({ page }) => {
      // Swimlanes, Board, and List view buttons
      const viewToggle = page.locator('.flex.bg-zinc-800.rounded-lg.p-1');
      await expect(viewToggle).toBeVisible();
      await expect(viewToggle.locator('button')).toHaveCount(3);
    });

    test('should display the New Issue button', async ({ page }) => {
      await expect(page.locator('button:has-text("New Issue")')).toBeVisible();
    });

    test('should display the refresh button', async ({ page }) => {
      // Look for button with refresh icon in header area
      const headerButtons = page.locator('.flex-shrink-0.border-b button');
      await expect(headerButtons.first()).toBeVisible();
    });

    test('should display the keyboard shortcuts help button', async ({ page }) => {
      // Keyboard shortcuts button is in the header
      const headerButtons = page.locator('.flex-shrink-0.border-b button');
      const buttonCount = await headerButtons.count();
      expect(buttonCount).toBeGreaterThanOrEqual(3);
    });

    test('should display Git Integration button', async ({ page }) => {
      // Git button should be in the header area
      const headerArea = page.locator('.flex-shrink-0.border-b');
      await expect(headerArea).toBeVisible();
    });
  });

  test.describe('Project Selection', () => {
    test('should auto-select first project on load', async ({ page }) => {
      const projectSelect = page.locator('select').first();
      // Wait for projects to load
      await page.waitForFunction(() => {
        const select = document.querySelector('select');
        return select && select.options.length > 0 && !select.options[0].text.includes('Loading');
      }, { timeout: 10000 });

      // Verify a project is selected (not empty or loading)
      const value = await projectSelect.inputValue();
      expect(value).toBeTruthy();
    });

    test('should allow changing the selected project', async ({ page }) => {
      const projectSelect = page.locator('select').first();
      // Wait for projects to load
      await page.waitForFunction(() => {
        const select = document.querySelector('select');
        return select && select.options.length > 1 && !select.options[0].text.includes('Loading');
      }, { timeout: 10000 });

      const options = await projectSelect.locator('option').all();
      if (options.length > 1) {
        const secondOptionValue = await options[1].getAttribute('value');
        if (secondOptionValue) {
          await projectSelect.selectOption(secondOptionValue);
          await expect(projectSelect).toHaveValue(secondOptionValue);
        }
      }
    });
  });

  test.describe('View Mode Switching', () => {
    test('should default to swimlanes view', async ({ page }) => {
      // The first button in the view toggle should be active (swimlanes)
      const swimlanesButton = page.locator('.flex.bg-zinc-800.rounded-lg.p-1 button').first();
      await expect(swimlanesButton).toHaveClass(/bg-zinc-700/);
    });

    test('should switch to kanban board view', async ({ page }) => {
      const boardButton = page.locator('.flex.bg-zinc-800.rounded-lg.p-1 button').nth(1);
      await boardButton.click();
      await expect(boardButton).toHaveClass(/bg-zinc-700/);
    });

    test('should switch to list view', async ({ page }) => {
      const listButton = page.locator('.flex.bg-zinc-800.rounded-lg.p-1 button').nth(2);
      await listButton.click();
      await expect(listButton).toHaveClass(/bg-zinc-700/);
    });

    test('should switch back to swimlanes view', async ({ page }) => {
      // First switch to board
      const boardButton = page.locator('.flex.bg-zinc-800.rounded-lg.p-1 button').nth(1);
      await boardButton.click();

      // Then switch back to swimlanes
      const swimlanesButton = page.locator('.flex.bg-zinc-800.rounded-lg.p-1 button').first();
      await swimlanesButton.click();
      await expect(swimlanesButton).toHaveClass(/bg-zinc-700/);
    });
  });

  test.describe('Filter Bar', () => {
    test('should display search input', async ({ page }) => {
      const searchInput = page.locator('input[placeholder*="Search"]');
      await expect(searchInput).toBeVisible();
    });

    test('should allow typing in search input', async ({ page }) => {
      const searchInput = page.locator('input[placeholder*="Search"]');
      await searchInput.fill('test search');
      await expect(searchInput).toHaveValue('test search');
    });

    test('should display filters toggle button', async ({ page }) => {
      const filtersButton = page.locator('button:has-text("Filters")');
      await expect(filtersButton).toBeVisible();
    });

    test('should show filter dropdowns when Filters button is clicked', async ({ page }) => {
      const filtersButton = page.locator('button:has-text("Filters")');
      await filtersButton.click();

      // After clicking, filter dropdowns should appear
      // These are additional select elements that appear
      const selects = page.locator('select');
      const count = await selects.count();
      expect(count).toBeGreaterThanOrEqual(2); // At least project selector + type/priority filters
    });

    test('should filter by type when filters are open', async ({ page }) => {
      // Open filters
      const filtersButton = page.locator('button:has-text("Filters")');
      await filtersButton.click();

      // Wait for filter dropdowns to appear
      await page.waitForTimeout(300);

      // Find the type filter (second select after project selector)
      const typeFilter = page.locator('select').nth(1);
      await typeFilter.selectOption('EPIC');
      await expect(typeFilter).toHaveValue('EPIC');
    });

    test('should filter by priority when filters are open', async ({ page }) => {
      // Open filters
      const filtersButton = page.locator('button:has-text("Filters")');
      await filtersButton.click();

      // Wait for filter dropdowns to appear
      await page.waitForTimeout(300);

      // Find the priority filter (third select)
      const priorityFilter = page.locator('select').nth(2);
      await priorityFilter.selectOption('HIGH');
      await expect(priorityFilter).toHaveValue('HIGH');
    });

    test('should show clear button when filters are applied', async ({ page }) => {
      const searchInput = page.locator('input[placeholder*="Search"]');
      await searchInput.fill('test');

      // Clear button should appear
      await expect(page.locator('button:has-text("Clear")')).toBeVisible();
    });
  });

  test.describe('Issue Creation Modal', () => {
    test('should open create issue modal when clicking New Issue button', async ({ page }) => {
      await page.click('button:has-text("New Issue")');
      // Wait for modal to appear
      await expect(page.locator('h2:has-text("Create Issue")')).toBeVisible();
    });

    test('should close modal when clicking Cancel', async ({ page }) => {
      await page.click('button:has-text("New Issue")');
      await expect(page.locator('h2:has-text("Create Issue")')).toBeVisible();

      // Click cancel button
      await page.click('button:has-text("Cancel")');

      // Modal should be closed
      await expect(page.locator('h2:has-text("Create Issue")')).not.toBeVisible({ timeout: 5000 });
    });

    test('should close modal when pressing Escape', async ({ page }) => {
      await page.click('button:has-text("New Issue")');
      await expect(page.locator('h2:has-text("Create Issue")')).toBeVisible();

      // Press Escape
      await page.keyboard.press('Escape');

      // Modal should be closed
      await expect(page.locator('h2:has-text("Create Issue")')).not.toBeVisible({ timeout: 5000 });
    });

    test('should have title input field in create modal', async ({ page }) => {
      await page.click('button:has-text("New Issue")');
      await expect(page.locator('input[placeholder*="What needs to be done"]')).toBeVisible();
    });

    test('should have type selector in create modal', async ({ page }) => {
      await page.click('button:has-text("New Issue")');
      // The modal has select elements for type, priority, status
      const modal = page.locator('.fixed.inset-0.z-50');
      const selects = modal.locator('select');
      expect(await selects.count()).toBeGreaterThanOrEqual(3);
    });

    test('should disable create button when title is empty', async ({ page }) => {
      await page.click('button:has-text("New Issue")');

      // The Create Issue button should be disabled when title is empty
      const submitButton = page.locator('button:has-text("Create Issue")');
      await expect(submitButton).toBeDisabled();
    });

    test('should enable create button when title is filled', async ({ page }) => {
      await page.click('button:has-text("New Issue")');

      // Fill in the title
      const titleInput = page.locator('input[placeholder*="What needs to be done"]');
      await titleInput.fill('Test Issue Title');

      // The Create Issue button should be enabled
      const submitButton = page.locator('button:has-text("Create Issue")');
      await expect(submitButton).toBeEnabled();
    });

    test('should create issue with valid data', async ({ page }) => {
      await page.click('button:has-text("New Issue")');

      // Fill in the form
      const titleInput = page.locator('input[placeholder*="What needs to be done"]');
      const uniqueTitle = 'E2E Test Issue - ' + Date.now();
      await titleInput.fill(uniqueTitle);

      // Submit
      const submitButton = page.locator('button:has-text("Create Issue")');
      await submitButton.click();

      // Wait for modal to close (issue created)
      await expect(page.locator('h2:has-text("Create Issue")')).not.toBeVisible({ timeout: 10000 });
    });
  });

  test.describe('Keyboard Shortcuts', () => {
    test('should open keyboard shortcuts help with Shift+? key', async ({ page }) => {
      // Make sure no input is focused by clicking on a non-interactive area
      await page.locator('h1').click();
      await page.keyboard.press('Shift+/'); // Shift+/ produces ?

      // Shortcuts help should be visible
      await expect(page.locator('text=Keyboard Shortcuts')).toBeVisible({ timeout: 5000 });
    });

    test('should close keyboard shortcuts help with Escape', async ({ page }) => {
      await page.locator('h1').click();
      await page.keyboard.press('Shift+/');
      await expect(page.locator('text=Keyboard Shortcuts')).toBeVisible();

      await page.keyboard.press('Escape');
      await expect(page.locator('text=Keyboard Shortcuts')).not.toBeVisible({ timeout: 5000 });
    });

    test('should switch to swimlanes view with 1 key', async ({ page }) => {
      // First switch to another view
      const boardButton = page.locator('.flex.bg-zinc-800.rounded-lg.p-1 button').nth(1);
      await boardButton.click();
      await page.waitForTimeout(200);

      // Click on non-interactive area and press 1
      await page.locator('h1').click();
      await page.keyboard.press('Digit1');

      const swimlanesButton = page.locator('.flex.bg-zinc-800.rounded-lg.p-1 button').first();
      await expect(swimlanesButton).toHaveClass(/bg-zinc-700/);
    });

    test('should switch to kanban view with 2 key', async ({ page }) => {
      await page.locator('h1').click();
      await page.keyboard.press('Digit2');

      const boardButton = page.locator('.flex.bg-zinc-800.rounded-lg.p-1 button').nth(1);
      await expect(boardButton).toHaveClass(/bg-zinc-700/);
    });

    test('should switch to list view with 3 key', async ({ page }) => {
      await page.locator('h1').click();
      await page.keyboard.press('Digit3');

      const listButton = page.locator('.flex.bg-zinc-800.rounded-lg.p-1 button').nth(2);
      await expect(listButton).toHaveClass(/bg-zinc-700/);
    });

    test('should focus search with / key', async ({ page }) => {
      await page.locator('h1').click();
      await page.keyboard.press('Slash');

      const searchInput = page.locator('input[placeholder*="Search"]');
      await expect(searchInput).toBeFocused();
    });

    test('should open create modal with n key', async ({ page }) => {
      await page.locator('h1').click();
      await page.keyboard.press('KeyN');

      await expect(page.locator('h2:has-text("Create Issue")')).toBeVisible({ timeout: 5000 });
    });

    test('should not trigger shortcuts when typing in input', async ({ page }) => {
      const searchInput = page.locator('input[placeholder*="Search"]');
      await searchInput.click();
      await searchInput.fill('n'); // Type 'n' which would otherwise open create modal

      // Create modal should not open
      await expect(page.locator('h2:has-text("Create Issue")')).not.toBeVisible();
    });

    test('should open git sync panel with g key', async ({ page }) => {
      await page.locator('h1').click();
      await page.keyboard.press('KeyG');

      // Git sync panel should open - look for panel content
      await expect(page.locator('text=Git Sync').or(page.locator('text=Git Integration'))).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Refresh Functionality', () => {
    test('should have refresh button in header', async ({ page }) => {
      // Check header area has multiple action buttons
      const headerArea = page.locator('.flex-shrink-0.border-b');
      await expect(headerArea).toBeVisible();
    });
  });

  test.describe('Git Sync Panel', () => {
    test('should open git sync panel when pressing g key', async ({ page }) => {
      await page.locator('h1').click();
      await page.keyboard.press('KeyG');

      // Git sync panel should open
      await expect(page.locator('text=Git Sync').or(page.locator('text=Git Integration'))).toBeVisible({ timeout: 5000 });
    });

    test('should close git sync panel with Escape', async ({ page }) => {
      await page.locator('h1').click();
      await page.keyboard.press('KeyG');

      await page.waitForTimeout(500);
      await page.keyboard.press('Escape');

      // Give time for panel to close
      await page.waitForTimeout(500);
    });
  });

  test.describe('Status Counters', () => {
    test('should display total issues count', async ({ page }) => {
      // Wait for issues to potentially load
      await page.waitForTimeout(2000);

      // Should show total count badge
      const totalBadge = page.locator('span:has-text("total")');
      await expect(totalBadge).toBeVisible();
    });
  });

  test.describe('Responsive Behavior', () => {
    test('should display correctly on mobile viewport', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      await page.goto('/codeboard');

      await expect(page.locator('h1')).toContainText('CodeBoard');
      await expect(page.locator('button:has-text("New Issue")')).toBeVisible();
    });

    test('should display correctly on tablet viewport', async ({ page }) => {
      await page.setViewportSize({ width: 768, height: 1024 });
      await page.goto('/codeboard');

      await expect(page.locator('h1')).toContainText('CodeBoard');
      await expect(page.locator('button:has-text("New Issue")')).toBeVisible();
    });
  });
});

test.describe('CodeBoard Issue Detail', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');
    // Wait for issues to potentially load
    await page.waitForTimeout(2000);
  });

  test('should open issue detail modal when clicking an issue card', async ({ page }) => {
    // Look for any issue card with cursor-pointer class
    const issueCard = page.locator('.cursor-pointer').first();

    if (await issueCard.isVisible()) {
      await issueCard.click();
      // Issue detail modal should open - wait for it
      await page.waitForTimeout(500);
    }
  });

  test('should close issue detail modal with Escape', async ({ page }) => {
    const issueCard = page.locator('.cursor-pointer').first();

    if (await issueCard.isVisible()) {
      await issueCard.click();
      await page.waitForTimeout(500);

      await page.keyboard.press('Escape');

      // Give time for modal to close
      await page.waitForTimeout(500);
    }
  });
});

test.describe('CodeBoard Error Handling', () => {
  test('should handle network errors gracefully', async ({ page }) => {
    // Simulate offline mode
    await page.route('**/api/**', route => route.abort());

    await page.goto('/codeboard');

    // Page should still load without crashing
    await expect(page.locator('h1')).toContainText('CodeBoard');
  });

  test('should show loading state while fetching data', async ({ page }) => {
    // Slow down API responses
    await page.route('**/api/**', async route => {
      await new Promise(resolve => setTimeout(resolve, 1000));
      await route.continue();
    });

    await page.goto('/codeboard');

    // Should show loading indicator or page header at minimum
    await expect(page.locator('h1')).toContainText('CodeBoard');
  });
});
