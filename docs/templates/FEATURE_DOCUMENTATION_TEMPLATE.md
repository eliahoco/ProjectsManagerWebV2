# Feature: [Feature Title]

**Task:** CB-XXXX
**Story:** CB-XXXX: [Story Title]
**Epic:** E#: [Epic Title]
**Author:** [Name]
**Date:** YYYY-MM-DD
**Status:** Draft | In Review | Approved | Implemented

---

## 1. Overview

A concise summary of the feature, its purpose, and the problem it solves. Keep this to 2-3 sentences.

---

## 2. User Story

> As a [type of user], I want [goal/desire] so that [benefit/value].

### Acceptance Criteria

- [ ] Criterion 1: [Specific, testable requirement]
- [ ] Criterion 2: [Specific, testable requirement]
- [ ] Criterion 3: [Specific, testable requirement]

---

## 3. Technical Design

### 3.1 Architecture

Describe the high-level architecture and how this feature fits into the existing system.

| Layer | Components Affected | Changes |
|-------|-------------------|---------|
| Frontend | [Component names] | [Brief description] |
| Backend | [API routes, services] | [Brief description] |
| Database | [Models, tables] | [Brief description] |

### 3.2 API Changes

List any new or modified API endpoints.

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/api/example` | Description | N/A | `{ ... }` |
| POST | `/api/example` | Description | `{ ... }` | `{ ... }` |

### 3.3 Database Changes

Document any schema modifications.

```prisma
// Example: New or modified models
model Example {
  id        String   @id @default(cuid())
  // fields...
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
```

### 3.4 UI Components

List new or modified frontend components.

| Component | Location | Purpose |
|-----------|----------|---------|
| `ComponentName` | `frontend/components/...` | Description |

---

## 4. Implementation Plan

### Tasks

| Task | Description | Status |
|------|-------------|--------|
| CB-XXXX | Task description | TODO / IN_PROGRESS / DONE |
| CB-XXXX | Task description | TODO / IN_PROGRESS / DONE |

### Dependencies

- [Dependency 1: other features, external services, etc.]
- [Dependency 2]

---

## 5. Testing Strategy

### 5.1 Unit Tests

| Test | File | Description |
|------|------|-------------|
| `test_example` | `tests/...` | What it validates |

### 5.2 E2E Tests

| Test | File | Description |
|------|------|-------------|
| `example.spec.ts` | `tests/e2e/...` | User flow being tested |

### 5.3 Manual Testing Checklist

- [ ] Step 1: [Action] — Expected: [Result]
- [ ] Step 2: [Action] — Expected: [Result]

---

## 6. Edge Cases & Error Handling

| Scenario | Expected Behavior |
|----------|------------------|
| [Edge case 1] | [How the system should respond] |
| [Edge case 2] | [How the system should respond] |

---

## 7. Notes

### Design Decisions

Document key decisions and their rationale.

1. **[Decision]:** [Rationale]

### Known Limitations

- [Limitation 1]

### Future Considerations

- [Enhancement or follow-up work]
