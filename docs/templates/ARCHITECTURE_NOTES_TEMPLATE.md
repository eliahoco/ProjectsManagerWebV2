# Architecture Notes: [Title]

**Reference:** CB-XXXX
**Related Story/Epic:** CB-XXXX: [Story or Epic Title]
**Author:** [Name]
**Date:** YYYY-MM-DD
**Status:** Draft | In Review | Approved | Superseded

---

## 1. Context

Describe the problem or need that prompted this architectural decision. What existing behavior or limitation is being addressed?

### Current State

Briefly describe the system's current architecture relevant to this change.

### Problem Statement

What specific problem does this architecture change solve? Why is the current approach insufficient?

---

## 2. Decision

State the architectural decision clearly in 1-2 sentences.

> **We will** [decision statement] **because** [primary justification].

---

## 3. Architecture

### 3.1 System Overview

Describe how the change fits into the overall system architecture.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────▶│   Backend    │────▶│   Database   │
│              │     │              │     │              │
│  [affected   │     │  [affected   │     │  [affected   │
│   components]│     │   services]  │     │   models]    │
└──────────────┘     └──────────────┘     └──────────────┘
```

### 3.2 Component Interactions

Describe how components communicate and depend on each other.

| From | To | Interaction | Protocol |
|------|----|-------------|----------|
| [Component A] | [Component B] | [Description] | [REST / WebSocket / Direct] |

### 3.3 Data Flow

Describe the data flow for the primary use case this architecture supports.

```
1. User action → [Frontend Component]
2. [Frontend Component] → API call → [Backend Endpoint]
3. [Backend Endpoint] → [Service Layer] → [Database Query]
4. Response flows back through the same path
```

---

## 4. Alternatives Considered

Document the alternatives that were evaluated before reaching this decision.

### Option A: [Name] (Selected)

- **Description:** [How it works]
- **Pros:** [Advantages]
- **Cons:** [Disadvantages]

### Option B: [Name]

- **Description:** [How it works]
- **Pros:** [Advantages]
- **Cons:** [Disadvantages]
- **Why rejected:** [Reason]

### Option C: [Name]

- **Description:** [How it works]
- **Pros:** [Advantages]
- **Cons:** [Disadvantages]
- **Why rejected:** [Reason]

---

## 5. Technical Details

### 5.1 Affected Layers

| Layer | Impact | Files/Components |
|-------|--------|-----------------|
| Frontend | [New / Modified / None] | [File paths or component names] |
| Backend | [New / Modified / None] | [File paths or service names] |
| Database | [New / Modified / None] | [Model/table names] |
| Infrastructure | [New / Modified / None] | [Config or deployment changes] |

### 5.2 API Contracts

Document any new or changed API contracts relevant to this architecture.

```
[METHOD] /api/[endpoint]

Request:
{
  "field": "type — description"
}

Response:
{
  "field": "type — description"
}
```

### 5.3 Schema Changes

Document any database schema changes.

```prisma
model Example {
  id        String   @id @default(cuid())
  // fields...
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
```

### 5.4 Performance Considerations

| Concern | Approach | Expected Impact |
|---------|----------|-----------------|
| [e.g., Query performance] | [e.g., Added composite index] | [e.g., O(log n) lookup] |
| [e.g., Render performance] | [e.g., Memoization] | [e.g., Reduced re-renders by ~50%] |

---

## 6. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|------------|
| [Risk description] | Low / Medium / High | Low / Medium / High | [Mitigation strategy] |

---

## 7. Dependencies

### Internal Dependencies

- [Dependency on existing component/service]
- [Dependency on another in-progress feature]

### External Dependencies

- [Third-party library or service]
- [Infrastructure requirement]

---

## 8. Consequences

### Positive

- [Benefit this architecture provides]
- [Improvement to developer experience, performance, maintainability, etc.]

### Negative

- [Trade-off accepted with this approach]
- [Technical debt introduced, if any]

### Neutral

- [Side effects that are neither positive nor negative]

---

## 9. Validation

How will we verify this architecture decision is correct?

| Validation Method | Description | Status |
|------------------|-------------|--------|
| Unit tests | [What the tests verify] | TODO / PASS |
| E2E tests | [User flow being validated] | TODO / PASS |
| Performance benchmarks | [Metrics being measured] | TODO / PASS |
| Code review | [Aspects to focus on] | TODO / DONE |

---

## 10. References

- [Link to related documentation, ADRs, or design docs]
- [Link to relevant PRs or issues]
- [Link to external resources that informed this decision]
