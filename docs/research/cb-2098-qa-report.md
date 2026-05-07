# CB-2098 QA Report — E3-5: Recent summaries list shows latest 20 ordered DESC

**Date:** 2026-05-07
**Tester:** Jonny (VP R&D)
**Result:** ✅ PASS

## Acceptance Criteria

- [x] Recent summaries list renders newest-first
- [x] Row count ≤ 20

## Code Audit

**Backend** — `backend/api/doc_settings.py:96-116`

```python
@router.get("/documentation/summaries", ...)
async def list_recent_summaries(
    limit: int = Query(default=20, ge=1, le=100, ...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ExecutionSummary, Issue.key)
        .outerjoin(Issue, ExecutionSummary.issueId == Issue.id)
        .order_by(ExecutionSummary.executedAt.desc())
        .limit(limit)
    )
```

- Default `limit=20`, Pydantic enforces `ge=1, le=100`
- ORDER BY `executedAt DESC` enforced server-side
- Single-tenant — no project filter needed

**Frontend hook** — `frontend/hooks/useCodeBoard.ts:1412`

```ts
export function useRecentExecutionSummaries(limit = 20) { ... }
```

**UI** — `frontend/app/settings/documentation/page.tsx:400`

```tsx
const { data: summaries } = useRecentExecutionSummaries(20);
```

Frontend passes `limit=20` and renders rows in API order without re-sort.

## Live Regression

| Test | Command | Result |
|------|---------|--------|
| Default count | `GET /api/documentation/summaries` | 20 rows |
| DESC ordering | timestamps strictly non-increasing across all 20 rows | ✅ |
| issueKey enriched | 20/20 rows have issueKey populated | ✅ |
| Custom limit | `GET ...?limit=5` | 5 rows |
| Over-cap | `GET ...?limit=200` | HTTP 422 (Pydantic rejects) |

Top 3 timestamps: `2026-05-06T23:28:59`, `2026-05-06T23:22:07`, `2026-05-06T23:14:12`
Bottom 3: `2026-05-06T14:40:47`, `2026-05-02T20:44:34`, `2026-05-02T20:36:54`

## Visual QA (Rule 24)

`docs/research/cb-2098-recent-summaries-list.png` — full-page screenshot.

- Header: "Recent Execution Summaries" — subtitle: "latest 20 across all issues"
- Table renders 20 rows
- Top row: `5/6/26, 11:28 PM — CB-2097`
- Bottom row: `5/2/26, 8:36 PM — CB-2048`
- Each row: timestamp · issue link · provider · exit · files · +/- lines · Re-run
- Empty-state, loading, and error branches all coded for

## Verdict

PASS. Backend ORDER + LIMIT correct; UI hook + render preserve them. Pydantic rejects out-of-range `limit`. Visual confirms 20 rows newest-first.
