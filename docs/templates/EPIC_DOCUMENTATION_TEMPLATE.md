# Epic: [Epic Title]

**Epic Key:** CB-XXXX
**Feature:** CB-XXXX: [Parent Feature Title]
**Author:** [Name]
**Date:** YYYY-MM-DD
**Status:** Draft | In Review | Approved | In Progress | Completed

---

## 1. Overview

A concise summary of the epic, its business value, and the major capability it delivers. Keep this to 2-4 sentences.

**Business Value:** [Why this epic matters to users or the product]

**Estimated Duration:** [2-4 weeks]

---

## 2. Scope

### Goals

- [Primary goal this epic achieves]
- [Secondary goal]

### Non-Goals

- [What is explicitly out of scope for this epic]
- [Boundaries to prevent scope creep]

---

## 3. Stories

List all stories that compose this epic. Each story represents a user-facing capability.

| Story Key | Title | Story Points | Status |
|-----------|-------|:------------:|--------|
| CB-XXXX | [Story title] | [1-21] | BACKLOG / TODO / IN_PROGRESS / DONE |
| CB-XXXX | [Story title] | [1-21] | BACKLOG / TODO / IN_PROGRESS / DONE |

### Story Dependency Graph

Describe the order in which stories should be implemented and any dependencies between them.

```
CB-XXXX (Story 1)
  └─→ CB-XXXX (Story 2, depends on Story 1)
CB-XXXX (Story 3, independent)
```

---

## 4. Architecture Impact

### 4.1 System Changes

High-level view of how this epic affects the system architecture.

| Layer | Impact | Description |
|-------|--------|-------------|
| Frontend | New / Modified / None | [Brief description] |
| Backend | New / Modified / None | [Brief description] |
| Database | New / Modified / None | [Brief description] |
| Infrastructure | New / Modified / None | [Brief description] |

### 4.2 New Models / Schema Changes

Document any database schema changes introduced across this epic.

```prisma
// Example: New or modified models
model Example {
  id        String   @id @default(cuid())
  // fields...
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
```

### 4.3 New API Endpoints

Summary of all API endpoints introduced or modified across this epic.

| Method | Endpoint | Story | Description |
|--------|----------|-------|-------------|
| GET | `/api/example` | CB-XXXX | Description |
| POST | `/api/example` | CB-XXXX | Description |

### 4.4 New UI Components

Summary of all frontend components introduced or modified.

| Component | Location | Story | Purpose |
|-----------|----------|-------|---------|
| `ComponentName` | `frontend/components/...` | CB-XXXX | Description |

---

## 5. Technical Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|------------|
| [Risk description] | Low / Medium / High | Low / Medium / High | [Mitigation strategy] |

---

## 6. Testing Strategy

### 6.1 Test Coverage Summary

| Story | Unit Tests | E2E Tests | Status |
|-------|:----------:|:---------:|--------|
| CB-XXXX | [count] | [count] | Passing / Failing / TODO |
| CB-XXXX | [count] | [count] | Passing / Failing / TODO |

### 6.2 QA Tasks

| QA Task | Linked Story | Description | Status |
|---------|-------------|-------------|--------|
| QA-XXXX | CB-XXXX | [What is being validated] | TODO / PASS / FAIL |

### 6.3 Acceptance Testing Checklist

- [ ] All stories meet their acceptance criteria
- [ ] No regressions in existing functionality
- [ ] Performance benchmarks met (if applicable)
- [ ] Accessibility requirements satisfied

---

## 7. Progress & Metrics

### Completion Tracking

| Metric | Count |
|--------|:-----:|
| Total Stories | [n] |
| Completed Stories | [n] |
| Total Tasks | [n] |
| Completed Tasks | [n] |
| Total Story Points | [n] |
| Completed Story Points | [n] |

### Timeline

| Milestone | Target Date | Actual Date | Status |
|-----------|:-----------:|:-----------:|--------|
| Epic approved | YYYY-MM-DD | YYYY-MM-DD | Done / Pending |
| First story completed | YYYY-MM-DD | YYYY-MM-DD | Done / Pending |
| All stories completed | YYYY-MM-DD | YYYY-MM-DD | Done / Pending |
| QA sign-off | YYYY-MM-DD | YYYY-MM-DD | Done / Pending |

---

## 8. Notes

### Design Decisions

Document key architectural and design decisions made at the epic level.

1. **[Decision]:** [Rationale]

### Dependencies

- [External dependency: other epics, services, teams, etc.]

### Known Limitations

- [Limitation that applies across the epic]

### Future Considerations

- [Follow-up work or enhancements beyond this epic's scope]
