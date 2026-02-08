# Feature: Filter Results by Date Range

**Task:** CB-1117
**Story:** CB-1112: User can Filter Results by Date Range
**Epic:** E7: Polish & Testing
**Author:** Team
**Date:** 2026-02-07
**Status:** Implemented

---

## 1. Overview

Allow users to filter and sort CodeBoard issues by date fields (created, updated, due date). This includes a reusable DateRangePicker calendar component and integration with the FilterBar for date-based sorting across the issue list.

---

## 2. User Story

> As a user, I want to filter results by date range so that I can quickly find issues created, updated, or due within a specific time period.

### Acceptance Criteria

- [x] Users can sort issues by Created Date, Updated Date, and Due Date
- [x] Users can toggle sort direction (ascending/descending)
- [x] A DateRangePicker component provides calendar-based date range selection
- [x] Preset date ranges are available (Today, Yesterday, Last 7/30 days, This/Last month)
- [x] Date filters can be cleared independently of other filters

---

## 3. Technical Design

### 3.1 Architecture

| Layer | Components Affected | Changes |
|-------|-------------------|---------|
| Frontend | `DateRangePicker`, `FilterBar` | New calendar component, sort-by-date options in filter bar |
| Backend | `issues.py` API | Sort parameter support for date fields |
| Database | `Issue` model | Added indexes on `createdAt`, `updatedAt`, `dueDate` |

### 3.2 API Changes

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/api/projects/{id}/issues?sort=createdAt&order=desc` | Sort issues by date field | N/A | Issue list |

### 3.3 Database Changes

```prisma
model Issue {
  // Date fields
  dueDate     DateTime?
  startedAt   DateTime?
  completedAt DateTime?
  createdAt   DateTime  @default(now())
  updatedAt   DateTime  @updatedAt

  // Performance indexes for date filtering
  @@index([createdAt], name: "Issue_createdAt_idx")
  @@index([updatedAt], name: "Issue_updatedAt_idx")
  @@index([dueDate], name: "Issue_dueDate_idx")
  @@index([projectId, createdAt], name: "Issue_projectId_createdAt_idx")
  @@index([projectId, updatedAt], name: "Issue_projectId_updatedAt_idx")
}
```

### 3.4 UI Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `DateRangePicker` | `frontend/components/ui/date-range-picker.tsx` | Calendar-based date range selection with presets |
| `FilterBar` | `frontend/components/codeboard/FilterBar.tsx` | Integrates date sort options into issue list toolbar |

---

## 4. Implementation Plan

### Tasks

| Task | Description | Status |
|------|-------------|--------|
| CB-1113 | Create DateRangePicker component | DONE |
| CB-1114 | Add date sort options to FilterBar | DONE |
| CB-1115 | Add database indexes for date fields | DONE |
| CB-1116 | Write unit and E2E tests | DONE |
| CB-1117 | Create documentation template for features | DONE |

### Dependencies

- Existing FilterBar component (sort infrastructure)
- Issue model date fields (`createdAt`, `updatedAt`, `dueDate`)

---

## 5. Testing Strategy

### 5.1 Unit Tests

| Test | File | Description |
|------|------|-------------|
| DateRangePicker tests | `tests/components/DateRangePicker.test.tsx` | Rendering, presets, calendar navigation, date selection, accessibility |
| FilterBar tests | `tests/components/FilterBar.test.tsx` | Sort controls, filter dropdowns, date sort options, clear filters |

### 5.2 E2E Tests

| Test | File | Description |
|------|------|-------------|
| Date filter flows | `tests/e2e/date-filter.spec.ts` | Sort by date fields, toggle direction, combined filtering workflows |

### 5.3 Manual Testing Checklist

- [x] Open FilterBar and select "Created Date" sort — Expected: Issues reorder by creation date
- [x] Toggle sort direction — Expected: Order reverses
- [x] Open DateRangePicker and select a preset — Expected: Date range populates
- [x] Click clear on DateRangePicker — Expected: Selection resets
- [x] Apply date sort with type filter — Expected: Both filters active simultaneously

---

## 6. Edge Cases & Error Handling

| Scenario | Expected Behavior |
|----------|------------------|
| Issue has no `dueDate` set | Issue sorts to end when sorting by Due Date |
| User selects end date before start date | Dates auto-swap to correct order |
| Date range exceeds available data | Empty result set displayed with no errors |
| User clears filters while sort is active | Sort persists, only filters reset |

---

## 7. Notes

### Design Decisions

1. **Presets over free-form input:** Preset date ranges (Last 7 days, This month, etc.) reduce user friction for common queries.
2. **Sort-first approach:** Initial implementation prioritizes sorting by date fields; full date range filtering in the API can be added as a follow-up.
3. **Composite indexes:** Added `(projectId, createdAt)` and `(projectId, updatedAt)` composite indexes for performant per-project date queries.

### Known Limitations

- DateRangePicker component is built but not yet wired into the FilterBar's filter panel (sort options are active).

### Future Considerations

- Wire DateRangePicker into FilterBar for full date-range filtering (not just sorting)
- Add `dateFrom` / `dateTo` query parameters to the issues API
- Support date range filtering on QA Board tasks
