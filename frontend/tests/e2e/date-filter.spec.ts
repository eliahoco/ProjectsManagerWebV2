import { test, expect } from '@playwright/test';

/**
 * End-to-End Tests for Date Range Filtering
 * Task: CB-1116 - Testing framework for frontend UI
 * Part of STORY CB-1112: User can Filter Results by Date Range
 *
 * Tests cover:
 * - Date-related sort options in the filter bar
 * - FilterBar rendering and interaction
 * - Search and filter workflows
 */

test.describe('Date Range Filtering', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/codeboard');
    await page.waitForSelector('h1:has-text("CodeBoard")');
  });

  test.describe('Filter Bar', () => {
    test('should display the search input', async ({ page }) => {
      const searchInput = page.locator('input[placeholder*="Search issues"]');
      await expect(searchInput).toBeVisible();
    });

    test('should display the Filters toggle button', async ({ page }) => {
      const filterButton = page.locator('button:has-text("Filters")');
      await expect(filterButton).toBeVisible();
    });

    test('should display sort controls', async ({ page }) => {
      const sortSelect = page.locator('select').filter({ hasText: 'Manual Order' });
      await expect(sortSelect).toBeVisible();
    });
  });

  test.describe('Sort by Date Fields', () => {
    test('should allow sorting by Created Date', async ({ page }) => {
      // Find the sort field dropdown (not the first select which is project selector)
      const sortSelect = page.locator('select').filter({ hasText: 'Manual Order' });
      await sortSelect.selectOption('createdAt');
      await expect(sortSelect).toHaveValue('createdAt');
    });

    test('should allow sorting by Updated Date', async ({ page }) => {
      const sortSelect = page.locator('select').filter({ hasText: 'Manual Order' });
      await sortSelect.selectOption('updatedAt');
      await expect(sortSelect).toHaveValue('updatedAt');
    });

    test('should allow sorting by Due Date', async ({ page }) => {
      const sortSelect = page.locator('select').filter({ hasText: 'Manual Order' });
      await sortSelect.selectOption('dueDate');
      await expect(sortSelect).toHaveValue('dueDate');
    });

    test('should toggle sort direction', async ({ page }) => {
      // Click the sort direction button
      const sortDirButton = page.locator('button[title*="click to change"]');
      await expect(sortDirButton).toBeVisible();

      // Get initial title
      const initialTitle = await sortDirButton.getAttribute('title');

      await sortDirButton.click();

      // Title should change after click
      const newTitle = await sortDirButton.getAttribute('title');
      expect(newTitle).not.toBe(initialTitle);
    });
  });

  test.describe('Filter Dropdowns', () => {
    test('should show type and priority filters when Filters button is clicked', async ({ page }) => {
      const filterButton = page.locator('button:has-text("Filters")');
      await filterButton.click();

      // Type filter dropdown should appear
      const typeSelect = page.locator('select').filter({ hasText: 'All Types' });
      await expect(typeSelect).toBeVisible();

      // Priority filter dropdown should appear
      const prioritySelect = page.locator('select').filter({ hasText: 'All Priorities' });
      await expect(prioritySelect).toBeVisible();
    });

    test('should hide filters when Filters button is clicked again', async ({ page }) => {
      const filterButton = page.locator('button:has-text("Filters")');

      // Open
      await filterButton.click();
      const typeSelect = page.locator('select').filter({ hasText: 'All Types' });
      await expect(typeSelect).toBeVisible();

      // Close
      await filterButton.click();
      await expect(typeSelect).not.toBeVisible();
    });

    test('should filter by type', async ({ page }) => {
      const filterButton = page.locator('button:has-text("Filters")');
      await filterButton.click();

      const typeSelect = page.locator('select').filter({ hasText: 'All Types' });
      await typeSelect.selectOption('BUG');

      // Clear button should appear when filter is active
      await expect(page.locator('button:has-text("Clear")')).toBeVisible();
    });

    test('should filter by priority', async ({ page }) => {
      const filterButton = page.locator('button:has-text("Filters")');
      await filterButton.click();

      const prioritySelect = page.locator('select').filter({ hasText: 'All Priorities' });
      await prioritySelect.selectOption('HIGH');

      await expect(page.locator('button:has-text("Clear")')).toBeVisible();
    });
  });

  test.describe('Search Functionality', () => {
    test('should accept text input in search field', async ({ page }) => {
      const searchInput = page.locator('input[placeholder*="Search issues"]');
      await searchInput.fill('test search query');
      await expect(searchInput).toHaveValue('test search query');
    });

    test('should show Clear button when search has value', async ({ page }) => {
      const searchInput = page.locator('input[placeholder*="Search issues"]');
      await searchInput.fill('test');

      await expect(page.locator('button:has-text("Clear")')).toBeVisible();
    });

    test('should clear search when Clear button is clicked', async ({ page }) => {
      const searchInput = page.locator('input[placeholder*="Search issues"]');
      await searchInput.fill('test');

      const clearButton = page.locator('button:has-text("Clear")');
      await clearButton.click();

      await expect(searchInput).toHaveValue('');
    });
  });

  test.describe('Date Range Filter', () => {
    test('should show date field selector when Filters is opened', async ({ page }) => {
      const filterButton = page.locator('button:has-text("Filters")');
      await filterButton.click();

      const dateFieldSelect = page.locator('select').filter({ hasText: 'Date Field' });
      await expect(dateFieldSelect).toBeVisible();
    });

    test('should show DateRangePicker when a date field is selected', async ({ page }) => {
      const filterButton = page.locator('button:has-text("Filters")');
      await filterButton.click();

      const dateFieldSelect = page.locator('select').filter({ hasText: 'Date Field' });
      await dateFieldSelect.selectOption('createdAt');

      // DateRangePicker should appear with placeholder
      const picker = page.locator('text=Select range...');
      await expect(picker).toBeVisible();
    });

    test('should allow selecting different date fields', async ({ page }) => {
      const filterButton = page.locator('button:has-text("Filters")');
      await filterButton.click();

      const dateFieldSelect = page.locator('select').filter({ hasText: 'Date Field' });

      // Select Created Date
      await dateFieldSelect.selectOption('createdAt');
      await expect(dateFieldSelect).toHaveValue('createdAt');

      // Switch to Due Date
      await dateFieldSelect.selectOption('dueDate');
      await expect(dateFieldSelect).toHaveValue('dueDate');
    });
  });

  test.describe('Combined Filtering Workflow', () => {
    test('should support combining search with sort by date', async ({ page }) => {
      // Type a search query
      const searchInput = page.locator('input[placeholder*="Search issues"]');
      await searchInput.fill('test');

      // Change sort to Created Date
      const sortSelect = page.locator('select').filter({ hasText: 'Manual Order' });
      await sortSelect.selectOption('createdAt');

      // Both should be applied
      await expect(searchInput).toHaveValue('test');
      await expect(sortSelect).toHaveValue('createdAt');
    });

    test('should support combining type filter with date sort', async ({ page }) => {
      // Open filters
      const filterButton = page.locator('button:has-text("Filters")');
      await filterButton.click();

      // Select type
      const typeSelect = page.locator('select').filter({ hasText: 'All Types' });
      await typeSelect.selectOption('TASK');

      // Change sort to Due Date
      const sortSelect = page.locator('select').filter({ hasText: 'Manual Order' });
      await sortSelect.selectOption('dueDate');

      // Both should be applied
      await expect(sortSelect).toHaveValue('dueDate');
      await expect(page.locator('button:has-text("Clear")')).toBeVisible();
    });

    test('should support combining date range filter with type filter', async ({ page }) => {
      // Open filters
      const filterButton = page.locator('button:has-text("Filters")');
      await filterButton.click();

      // Select type
      const typeSelect = page.locator('select').filter({ hasText: 'All Types' });
      await typeSelect.selectOption('TASK');

      // Select date field
      const dateFieldSelect = page.locator('select').filter({ hasText: 'Date Field' });
      await dateFieldSelect.selectOption('createdAt');

      // Both filters should be active - Clear button visible
      await expect(page.locator('button:has-text("Clear")')).toBeVisible();
    });

    test('should clear all filters while preserving sort', async ({ page }) => {
      // Set up search
      const searchInput = page.locator('input[placeholder*="Search issues"]');
      await searchInput.fill('test');

      // Change sort
      const sortSelect = page.locator('select').filter({ hasText: 'Manual Order' });
      await sortSelect.selectOption('createdAt');

      // Clear filters
      const clearButton = page.locator('button:has-text("Clear")');
      await clearButton.click();

      // Search should be cleared
      await expect(searchInput).toHaveValue('');

      // Sort should remain unchanged (clear only clears search/type/priority/label/date)
      await expect(sortSelect).toHaveValue('createdAt');
    });
  });
});
