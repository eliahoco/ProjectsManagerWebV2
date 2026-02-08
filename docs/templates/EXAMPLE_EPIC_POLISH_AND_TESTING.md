# Epic: Polish & Testing

**Epic Key:** CB-1100
**Feature:** CB-1000: CodeBoard Issue Tracker
**Author:** Team
**Date:** 2026-02-07
**Status:** In Progress

---

## 1. Overview

Harden the CodeBoard issue tracker with improved filtering, date-based sorting, comprehensive test coverage, and documentation templates. This epic ensures the feature set is production-ready with reliable test infrastructure and consistent documentation practices.

**Business Value:** Users get more powerful filtering tools and the team gains confidence through test coverage and standardized documentation.

**Estimated Duration:** 3 weeks

---

## 2. Scope

### Goals

- Add date range filtering and sorting to the issue list
- Establish reusable documentation templates for features and epics
- Achieve comprehensive unit and E2E test coverage for filter components
- Add security testing for API endpoints

### Non-Goals

- Full-text search across issue content
- Saved/named filter presets
- Export of filtered results

---

## 3. Stories

| Story Key | Title | Story Points | Status |
|-----------|-------|:------------:|--------|
| CB-1112 | User can Filter Results by Date Range | 8 | IN_PROGRESS |
| CB-1130 | CodeBoard has comprehensive test coverage | 5 | TODO |

### Story Dependency Graph

```
CB-1112 (Filter by Date Range)
  └─→ CB-1130 (Test Coverage, depends on filter implementation)
```

---

## 4. Architecture Impact

### 4.1 System Changes

| Layer | Impact | Description |
|-------|--------|-------------|
| Frontend | Modified | New DateRangePicker component, FilterBar sort options |
| Backend | Modified | Sort parameter support on issues API |
| Database | Modified | Added performance indexes on date fields |
| Infrastructure | None | No infrastructure changes |

### 4.2 New Models / Schema Changes

```prisma
model Issue {
  // Date fields with new performance indexes
  dueDate     DateTime?
  startedAt   DateTime?
  completedAt DateTime?
  createdAt   DateTime  @default(now())
  updatedAt   DateTime  @updatedAt

  @@index([createdAt], name: "Issue_createdAt_idx")
  @@index([updatedAt], name: "Issue_updatedAt_idx")
  @@index([dueDate], name: "Issue_dueDate_idx")
  @@index([projectId, createdAt], name: "Issue_projectId_createdAt_idx")
  @@index([projectId, updatedAt], name: "Issue_projectId_updatedAt_idx")
}
```

### 4.3 New API Endpoints

| Method | Endpoint | Story | Description |
|--------|----------|-------|-------------|
| GET | `/api/projects/{id}/issues?sort=createdAt&order=desc` | CB-1112 | Sort issues by date field |

### 4.4 New UI Components

| Component | Location | Story | Purpose |
|-----------|----------|-------|---------|
| `DateRangePicker` | `frontend/components/ui/date-range-picker.tsx` | CB-1112 | Calendar-based date range selection with presets |
| `FeatureSearchBar` | `frontend/components/codeboard/FeatureSearchBar.tsx` | CB-1112 | Search bar for filtering features |

---

## 5. Technical Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|------------|
| Date sorting performance on large datasets | Low | Medium | Composite indexes on (projectId, dateField) |
| Calendar component accessibility gaps | Medium | Medium | Unit tests include keyboard navigation and ARIA attributes |

---

## 6. Testing Strategy

### 6.1 Test Coverage Summary

| Story | Unit Tests | E2E Tests | Status |
|-------|:----------:|:---------:|--------|
| CB-1112 | 2 suites | 1 suite | Passing |

### 6.2 QA Tasks

| QA Task | Linked Story | Description | Status |
|---------|-------------|-------------|--------|
| QA-1112 | CB-1112 | Validate date sort on all date fields | PASS |
| QA-1113 | CB-1112 | Validate DateRangePicker presets and custom ranges | PASS |

### 6.3 Acceptance Testing Checklist

- [x] All stories meet their acceptance criteria
- [x] No regressions in existing functionality
- [ ] Performance benchmarks met (if applicable)
- [x] Accessibility requirements satisfied

---

## 7. Progress & Metrics

### Completion Tracking

| Metric | Count |
|--------|:-----:|
| Total Stories | 2 |
| Completed Stories | 0 |
| Total Tasks | 10 |
| Completed Tasks | 7 |
| Total Story Points | 13 |
| Completed Story Points | 0 |

### Timeline

| Milestone | Target Date | Actual Date | Status |
|-----------|:-----------:|:-----------:|--------|
| Epic approved | 2026-01-20 | 2026-01-20 | Done |
| First story completed | 2026-02-07 | — | Pending |
| All stories completed | 2026-02-14 | — | Pending |
| QA sign-off | 2026-02-14 | — | Pending |

---

## 8. Notes

### Design Decisions

1. **Sort-first approach:** Prioritized date sorting over full date-range API filtering to deliver value incrementally.
2. **Composite indexes:** Added `(projectId, createdAt)` and `(projectId, updatedAt)` for performant per-project date queries.
3. **Reusable DateRangePicker:** Built as a standalone UI component for reuse in QA Board and other views.

### Dependencies

- Existing FilterBar component infrastructure
- Issue model date fields (`createdAt`, `updatedAt`, `dueDate`)

### Known Limitations

- DateRangePicker is built but not yet wired into FilterBar's filter panel (sort options are active, range filtering is pending)

### Future Considerations

- Wire DateRangePicker into FilterBar for full date-range filtering
- Add `dateFrom` / `dateTo` query parameters to the issues API
- Support date range filtering on QA Board tasks
- Saved filter presets per user
