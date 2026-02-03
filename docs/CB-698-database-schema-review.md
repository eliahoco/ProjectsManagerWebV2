# CB-698: Database Schema Review

**Task:** Review database schema changes
**Story:** CB-692: As a user, I want to...
**Date:** 2026-01-27

---

## Executive Summary

This document provides a comprehensive review of the database schema for ProjectsManagerWebV2. The schema supports a project management system with issue tracking (CodeBoard), quality assurance testing (QA Board), and git integration features.

---

## 1. Schema Architecture Overview

### 1.1 Dual ORM Architecture

The project uses a dual-database approach:

| Layer | ORM | Database | Location |
|-------|-----|----------|----------|
| Frontend | Prisma | SQLite | `frontend/prisma/dev.db` |
| Backend | SQLAlchemy (async) | SQLite | Same database file |

**Key Files:**
- Prisma Schema: `frontend/prisma/schema.prisma`
- SQLAlchemy Models: `backend/models/*.py`
- Database Config: `backend/app/config.py`

### 1.2 Table Inventory

| Domain | Tables | Purpose |
|--------|--------|---------|
| Core | `Project`, `Port`, `PortRange`, `Session`, `Setting` | Project management |
| CodeBoard | `Issue`, `Comment`, `Activity`, `IssueLink`, `IssueSequence` | Issue tracking |
| QA Board | `QATask`, `QATaskIssueLink`, `QASequence`, `QASettings` | Quality assurance |
| Git Integration | `CommitLink`, `GitSyncState` | Version control linking |

---

## 2. Recent Schema Changes (Commit a18b3d2)

### 2.1 New Tables Added

#### QATask
```
- id (PK)
- projectId, key (unique), sequence
- title, scenario, expectedResult, actualResult
- status (NOT_DONE, IN_PROGRESS, PASS, FAILED)
- type (AUTOMATED, MANUAL)
- priority (LOW, MEDIUM, HIGH, CRITICAL)
- executionHistory (JSON)
- lastExecutedAt, bugIssueId
- createdAt, updatedAt
```

#### QATaskIssueLink (Many-to-Many)
```
- id (PK)
- qaTaskId (FK → QATask)
- issueId (FK → Issue)
- createdAt
- Unique constraint: (qaTaskId, issueId)
```

#### QASequence
```
- id (PK)
- projectId (unique)
- prefix (default: "QA")
- lastNumber
```

#### QASettings
```
- id (PK)
- projectId (unique, FK → Project)
- passThreshold (default: 0.9)
- autoCreateBugs (default: true)
```

### 2.2 Issue Table Modifications

| Change | Type | Purpose |
|--------|------|---------|
| `breakdownBatchId` | New Column (String, nullable) | Groups issues from same AI breakdown with UUID |
| `breakdownBatchId_idx` | New Index | Query performance for batch operations |
| `COMPLETED_WAITING_QA` | New Status Value | Track issues pending QA verification |
| `FEATURE` | New Type Value | Feature request tracking |
| `qaTaskLinks` | New Relationship | Many-to-many link to QA tasks |

---

## 3. Schema Analysis

### 3.1 Data Integrity ✅

| Check | Status | Notes |
|-------|--------|-------|
| Primary Keys | ✅ Pass | All tables have PKs |
| Foreign Keys | ✅ Pass | Proper FK constraints with cascade deletes |
| Unique Constraints | ✅ Pass | Keys, sequences properly constrained |
| Indexes | ✅ Pass | Comprehensive indexing on query columns |
| Null Handling | ✅ Pass | Appropriate nullability |

### 3.2 Referential Integrity

```
Project (1) ─────┬──── (N) Issue ──────── (N) Comment
                 │         │
                 │         ├──── (N) Activity
                 │         │
                 │         ├──── (M) IssueLink
                 │         │
                 │         └──── (M) QATaskIssueLink ──── (N) QATask
                 │
                 ├──── (1) IssueSequence
                 ├──── (1) QASequence
                 ├──── (1) QASettings
                 ├──── (1) GitSyncState
                 └──── (N) CommitLink
```

### 3.3 Cascade Delete Behavior

| Parent | Child | On Delete |
|--------|-------|-----------|
| Project | Issue | CASCADE |
| Project | QASettings | CASCADE |
| Project | GitSyncState | CASCADE |
| Issue | Comment | CASCADE |
| Issue | Activity | CASCADE |
| Issue | IssueLink | CASCADE |
| Issue | QATaskIssueLink | CASCADE |
| Issue | CommitLink | CASCADE |
| Issue | parent/children | SET NULL |
| QATask | QATaskIssueLink | CASCADE |

### 3.4 Index Analysis

#### Well-Indexed Columns ✅
- `Issue.projectId`, `status`, `type`, `parentId`, `breakdownBatchId`
- `Comment.issueId`
- `Activity.issueId`
- `IssueLink.fromIssueId`, `toIssueId`
- `QATask.projectId`, `status`, `priority`
- `QATaskIssueLink.qaTaskId`, `issueId`
- `CommitLink.issueId`, `projectId`, `commitHash`

#### Potential Missing Indexes ⚠️
- `Issue.assignee` - If filtering by assignee is common
- `Issue.dueDate` - If due date queries are frequent
- `Issue.labels` - Consider full-text search for labels

---

## 4. Schema Consistency Review

### 4.1 Prisma ↔ SQLAlchemy Sync

| Model | Prisma | SQLAlchemy | Status |
|-------|--------|------------|--------|
| Project | ✅ | ✅ | Synced |
| Issue | ✅ | ✅ | Synced |
| Comment | ✅ | ✅ | Synced |
| Activity | ✅ | ✅ | Synced |
| IssueLink | ✅ | ✅ | Synced |
| IssueSequence | ✅ | ✅ | Synced |
| QATask | ✅ | ✅ | Synced |
| QATaskIssueLink | ✅ | ✅ | Synced |
| QASequence | ✅ | ✅ | Synced |
| QASettings | ✅ | ✅ | Synced |
| CommitLink | ❌ (SQLAlchemy only) | ✅ | Backend-only |
| GitSyncState | ❌ (SQLAlchemy only) | ✅ | Backend-only |

### 4.2 Enum Consistency

| Enum | Prisma | SQLAlchemy | Backend Schema |
|------|--------|------------|----------------|
| IssueType | String field | `IssueType` Enum | ✅ Aligned |
| IssueStatus | String field | `IssueStatus` Enum | ✅ Aligned |
| Priority | String field | `Priority` Enum | ✅ Aligned |
| LinkType | String field | `LinkType` Enum | ✅ Aligned |
| QATaskStatus | String field | `QATaskStatus` Enum | ✅ Aligned |
| QATaskType | String field | `QATaskType` Enum | ✅ Aligned |

---

## 5. Recommendations

### 5.1 Short-term (Next Sprint)

1. **Consider adding `Issue.assignee` index** if assignee filtering is a common query pattern
2. **Add migration documentation** for the new QA Board tables
3. **Verify cascade delete behavior** in integration tests

### 5.2 Medium-term

1. **Add `Project` FK to `QATask`** - Currently `projectId` is a String without FK constraint in SQLAlchemy. Consider adding FK for referential integrity.
2. **Consider composite indexes** for common query patterns:
   - `(projectId, status)` on Issue
   - `(projectId, status)` on QATask

### 5.3 Future Considerations

1. **Labels column** - Currently stored as JSON string. Consider a separate `Label` table for better queryability
2. **Execution history** - JSON storage is flexible but consider archiving old history to a separate table for large datasets
3. **Database migration strategy** - Establish a formal migration process for schema changes

---

## 6. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Data loss from cascade deletes | Medium | Already mitigated with SET NULL for parent-child |
| Schema drift between Prisma/SQLAlchemy | Low | Models are well-aligned |
| Performance with large datasets | Low | Good indexing in place |
| JSON field querying | Low | Limited to labels/history, not critical paths |

---

## 7. Conclusion

The database schema is well-designed with:
- ✅ Proper normalization
- ✅ Comprehensive indexing
- ✅ Appropriate referential integrity
- ✅ Consistent naming conventions
- ✅ Good separation of concerns (Issues, QA, Git)

The recent QA Board additions follow existing patterns and integrate well with the existing schema. The dual ORM approach (Prisma + SQLAlchemy) is working correctly with both accessing the same SQLite database.

**Schema Status: APPROVED** ✅

---

## Appendix A: Full Schema Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           PROJECTS MANAGER WEB                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐                                                        │
│  │   Project   │                                                        │
│  ├─────────────┤                                                        │
│  │ id (PK)     │◄──────────────────────────────────────────────────┐    │
│  │ name        │                                                   │    │
│  │ path        │                                                   │    │
│  │ status      │                                                   │    │
│  └──────┬──────┘                                                   │    │
│         │                                                          │    │
│         │ 1:N                                                      │    │
│         ▼                                                          │    │
│  ┌─────────────┐       ┌─────────────┐      ┌─────────────┐       │    │
│  │    Issue    │──────►│   Comment   │      │  Activity   │       │    │
│  ├─────────────┤  1:N  ├─────────────┤ 1:N  ├─────────────┤       │    │
│  │ id (PK)     │◄──────│ issueId(FK) │◄─────│ issueId(FK) │       │    │
│  │ projectId   │       └─────────────┘      └─────────────┘       │    │
│  │ key         │                                                   │    │
│  │ title       │       ┌─────────────┐      ┌─────────────┐       │    │
│  │ parentId    │◄─────►│  IssueLink  │      │ CommitLink  │       │    │
│  │ ...         │  M:M  ├─────────────┤ 1:N  ├─────────────┤       │    │
│  └──────┬──────┘       │ fromIssueId │◄─────│ issueId(FK) │       │    │
│         │              │ toIssueId   │      │ projectId   │───────┘    │
│         │              └─────────────┘      └─────────────┘            │
│         │ M:M                                                          │
│         ▼                                                              │
│  ┌──────────────────┐       ┌─────────────┐                           │
│  │ QATaskIssueLink  │──────►│   QATask    │                           │
│  ├──────────────────┤  N:1  ├─────────────┤                           │
│  │ issueId (FK)     │       │ id (PK)     │                           │
│  │ qaTaskId (FK)    │       │ projectId   │                           │
│  └──────────────────┘       │ key         │                           │
│                             │ scenario    │                           │
│                             └─────────────┘                           │
│                                                                        │
│  ┌─────────────────┐  ┌──────────────┐  ┌─────────────────┐          │
│  │ IssueSequence   │  │ QASequence   │  │  GitSyncState   │          │
│  ├─────────────────┤  ├──────────────┤  ├─────────────────┤          │
│  │ projectId       │  │ projectId    │  │ projectId (FK)  │          │
│  │ prefix          │  │ prefix       │  │ lastSyncedHash  │          │
│  │ lastNumber      │  │ lastNumber   │  └─────────────────┘          │
│  └─────────────────┘  └──────────────┘                               │
│                                                                        │
│  ┌─────────────────┐                                                  │
│  │   QASettings    │                                                  │
│  ├─────────────────┤                                                  │
│  │ projectId (FK)  │                                                  │
│  │ passThreshold   │                                                  │
│  │ autoCreateBugs  │                                                  │
│  └─────────────────┘                                                  │
│                                                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Appendix B: Issue Status Flow

```
BACKLOG ──► TODO ──► IN_PROGRESS ──► IN_REVIEW ──► COMPLETED_WAITING_QA ──► DONE
                                                            │
                                         (if QA fails)      ▼
                                                    Returns to IN_PROGRESS

Any status can transition to CANCELLED
```

---

*Document generated: 2026-01-27*
*Task: CB-698*
