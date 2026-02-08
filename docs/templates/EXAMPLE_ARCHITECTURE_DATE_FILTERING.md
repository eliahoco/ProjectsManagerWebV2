# Architecture Notes: Date-Based Filtering & Sorting for Issues

**Reference:** CB-1125
**Related Story/Epic:** CB-1112: User can Filter Results by Date Range
**Author:** Team
**Date:** 2026-02-08
**Status:** Approved

---

## 1. Context

### Current State

The CodeBoard issue list supports filtering by type, status, priority, and labels. Sorting is limited to priority and title. All filtering happens via query parameters passed to `GET /api/projects/{id}/issues`, with the frontend `FilterBar` component providing the UI controls.

### Problem Statement

Users cannot sort or filter issues by date fields (created, updated, due date). For projects with hundreds of issues, finding recently updated or overdue items requires manual scanning. The system needs date-aware sorting and range-based filtering without degrading query performance.

---

## 2. Decision

> **We will** add date-field sorting to the existing FilterBar and introduce a DateRangePicker component for calendar-based range selection **because** this leverages the existing filter infrastructure while providing an intuitive date selection UI that covers both common presets and custom ranges.

---

## 3. Architecture

### 3.1 System Overview

The change extends all three layers with minimal new surface area:

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│    Frontend      │     │     Backend      │     │    Database      │
│                  │     │                  │     │                  │
│  FilterBar       │────▶│  issues.py       │────▶│  Issue model     │
│   + date sort    │     │   + sort params  │     │   + date indexes │
│                  │     │   + date range   │     │                  │
│  DateRangePicker │     │     params       │     │                  │
│   (new)          │     │                  │     │                  │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### 3.2 Component Interactions

| From | To | Interaction | Protocol |
|------|----|-------------|----------|
| FilterBar | useIssues hook | Passes sort field + direction | React state |
| DateRangePicker | FilterBar | Emits selected date range | Callback prop |
| useIssues hook | Backend API | Query params: `sort`, `order`, `dateFrom`, `dateTo` | REST GET |
| Backend API | Database | SQLAlchemy order_by + where clause on date columns | SQL |

### 3.3 Data Flow

```
1. User selects "Created Date" in FilterBar sort dropdown
2. FilterBar updates sortBy state → triggers useIssues refetch
3. useIssues sends GET /api/projects/{id}/issues?sort=createdAt&order=desc
4. Backend orders query by Issue.createdAt DESC using indexed column
5. Response returns sorted issue list → UI re-renders
```

---

## 4. Alternatives Considered

### Option A: Extend FilterBar with date sort options (Selected)

- **Description:** Add date fields to the existing sort dropdown in FilterBar, reusing the current sort infrastructure.
- **Pros:** Minimal new code, consistent UX with existing sort controls, backend already supports order_by.
- **Cons:** Requires separate DateRangePicker component for range filtering.

### Option B: Dedicated date filter panel

- **Description:** A standalone filter panel specifically for date-based queries, separate from the FilterBar.
- **Pros:** Could support complex date logic (between, before, after, relative).
- **Cons:** Fragments the filtering UX, adds a second filter location, more code to maintain.
- **Why rejected:** Overengineered for current needs; users expect date sorting alongside other sort options.

### Option C: Server-side virtual scrolling with date cursors

- **Description:** Replace pagination with cursor-based scrolling keyed on date fields.
- **Pros:** Efficient for very large datasets, natural date ordering.
- **Cons:** Major refactor of pagination, breaks existing offset-based API contract.
- **Why rejected:** Current dataset sizes don't justify the complexity.

---

## 5. Technical Details

### 5.1 Affected Layers

| Layer | Impact | Files/Components |
|-------|--------|-----------------|
| Frontend | Modified | `FilterBar.tsx`, `useCodeBoard.ts`, `codeboard.ts` (types) |
| Frontend | New | `date-range-picker.tsx` |
| Backend | Modified | `backend/api/issues.py` |
| Database | Modified | `frontend/prisma/schema.prisma` (new indexes) |

### 5.2 API Contracts

```
GET /api/projects/{id}/issues?sort=createdAt&order=desc&dateField=createdAt&dateFrom=2026-01-01&dateTo=2026-02-01

Response:
{
  "items": [Issue],
  "total": number,
  "page": number,
  "pageSize": number
}
```

New query parameters:
- `sort`: Extended to accept `createdAt`, `updatedAt`, `dueDate`
- `order`: `asc` | `desc`
- `dateField`: Which date column to filter on
- `dateFrom`: ISO date string, inclusive lower bound
- `dateTo`: ISO date string, inclusive upper bound

### 5.3 Schema Changes

```prisma
model Issue {
  // Existing date fields (no column changes)
  dueDate     DateTime?
  startedAt   DateTime?
  completedAt DateTime?
  createdAt   DateTime  @default(now())
  updatedAt   DateTime  @updatedAt

  // New performance indexes
  @@index([createdAt], name: "Issue_createdAt_idx")
  @@index([updatedAt], name: "Issue_updatedAt_idx")
  @@index([dueDate], name: "Issue_dueDate_idx")
  @@index([projectId, createdAt], name: "Issue_projectId_createdAt_idx")
  @@index([projectId, updatedAt], name: "Issue_projectId_updatedAt_idx")
}
```

### 5.4 Performance Considerations

| Concern | Approach | Expected Impact |
|---------|----------|-----------------|
| Sort query performance | Single-column B-tree indexes on date fields | O(log n) lookup + sequential scan |
| Per-project date queries | Composite indexes `(projectId, date)` | Avoids full table scan when filtering by project |
| Frontend re-renders | Sort state managed in useIssues hook, only re-fetches on change | No unnecessary renders |

---

## 6. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|------------|
| Null dates cause inconsistent sort order | Medium | Low | Null values sort to end (NULLS LAST) |
| Index bloat on write-heavy tables | Low | Low | Only 5 indexes added; Issue table has moderate write frequency |
| DateRangePicker timezone mismatches | Medium | Medium | All dates stored as UTC, converted to local in UI |

---

## 7. Dependencies

### Internal Dependencies

- Existing `FilterBar` component sort infrastructure
- `useIssues` hook query parameter handling
- Issue model date fields already present in schema

### External Dependencies

- `react-day-picker` (or equivalent) for calendar UI
- `date-fns` for date manipulation and formatting

---

## 8. Consequences

### Positive

- Users can quickly find recent, overdue, or time-scoped issues
- Database queries for date-sorted results are index-backed
- DateRangePicker is reusable across other features (QA board, reports)

### Negative

- 5 new database indexes increase storage slightly and slow writes marginally
- DateRangePicker adds a new UI component to maintain

### Neutral

- Sort dropdown now has more options (may need grouping if more sort fields are added later)

---

## 9. Validation

| Validation Method | Description | Status |
|------------------|-------------|--------|
| Unit tests | DateRangePicker rendering, presets, date selection | PASS |
| Unit tests | FilterBar sort controls and date options | PASS |
| E2E tests | Sort by date fields, toggle direction, combined filters | PASS |
| Performance benchmarks | Query time with indexes vs without on 1K+ issues | PASS |
| Code review | Index strategy, null handling, timezone consistency | DONE |

---

## 10. References

- [CB-1112: User can Filter Results by Date Range](../CB-1112-date-range-filter.md)
- [Feature Documentation: Date Range Filter](EXAMPLE_FEATURE_DATE_RANGE_FILTER.md)
- [Epic Documentation: Polish & Testing](EXAMPLE_EPIC_POLISH_AND_TESTING.md)
