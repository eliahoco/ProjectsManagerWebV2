# CB-2077 — [QA] E2-6: Last-indexed timestamp updates after regenerate

**Date:** 2026-05-07
**QA by:** Jonny (VP R&D)
**Hierarchy:** FEATURE CB-2038 → EPIC CB-2054 → STORY CB-2067 → TASK CB-2077
**Verdict:** PASS (data layer). UI bug filed as separate ticket.

---

## Acceptance criterion

> Manual: note timestamp → regenerate → timestamp newer.

## Subject under test

FEATURE issue **CB-2038** (id `94aff46e-715b-49cf-8f69-7112be5bd211`) — already had a populated `FeatureDocumentation` row generated 2026-05-06 22:14 UTC.

## Procedure

1. `GET /api/features/94aff46e-…/documentation` → captured initial `lastIndexedAt`.
2. `POST /api/features/94aff46e-…/documentation/generate` (synchronous endpoint, took ~33 s while it re-aggregated descendants + re-embedded into ChromaDB).
3. `GET /api/features/94aff46e-…/documentation` → captured post-regenerate `lastIndexedAt`.

## Evidence — data layer (PASS)

| Field          | Before                       | After                        | Result    |
| -------------- | ---------------------------- | ---------------------------- | --------- |
| `lastIndexedAt`| `2026-05-06T22:14:06.024676` | `2026-05-06T22:46:59.675402` | NEWER ✓   |
| `updatedAt`    | `2026-05-06T22:14:06.024961` | `2026-05-06T22:46:59.675536` | NEWER ✓   |
| `embeddingId`  | `f6e011d460598184e3d8951747516f13` | `f6e011d460598184e3d8951747516f13` | UNCHANGED (deterministic id → upsert, no dup — corroborates sibling CB-2075) |
| `createdAt`    | `2026-05-01T21:11:18.156751` | `2026-05-01T21:11:18.156751` | unchanged ✓ |

Delta: ~32 min 53 s. Acceptance for CB-2077 satisfied at the API/data level.

Backend write-site: `backend/services/documentation_generator.py:1725` — `row.lastIndexedAt = datetime.utcnow()` is set inside the ChromaDB-indexing block guarded by the embed-success condition. The new value only persists when `RAGService.embed_feature_documentation` returns truthy. RAG status during this run: `RAG HTTP, 3,526 docs` (visible bottom-left of screenshot) — Chroma container healthy.

## Evidence — UI surface (PASS-with-bug)

Screenshot: `docs/research/cb-2077-doc-page-after-regenerate.png` (full page).

The Documentation tab renders both the **Indexed** chip and **Last updated** label. The `<time>` elements carry the correct `datetime` ISO string (verified in DOM):

```
datetime="2026-05-06T22:46:59.675402"   (Indexed)
datetime="2026-05-06T22:46:59.675536"   (Last updated)
```

These match the new DB values exactly. Tooltip (`title` attr) also resolves to the correct local-time string `5/6/2026, 10:46:59 PM`. So the **machine-readable surface is correct** — assistive tech and any consumer that reads `datetime` gets the right answer.

## Bug found (filed as separate ticket)

The visible relative-time text reads **"3h ago"** when the regenerate happened seconds before the page render.

Root cause (verified via `page.evaluate` inside the running browser):

```
iso          = "2026-05-06T22:46:59.675402"          // backend output, no Z suffix
new Date(iso).toISOString() = "2026-05-06T19:46:59.675Z"   // parsed as LOCAL
Date.now() ISO              = "2026-05-06T22:48:17.106Z"   // actual UTC
diff_sec                    = 10877  → "3h ago"
browser TZ                  = "Asia/Jerusalem"  (UTC+3 IDT)
```

The backend serializes `datetime.utcnow()` (a *naive* `datetime`) through Pydantic, which emits the ISO with no timezone designator. JavaScript's `new Date(iso)` then interprets a missing tz as **local** time per ECMA-262 §21.4.3.2, so the value is shifted by the browser's UTC offset before being compared to `Date.now()`. In Jerusalem in May (IDT, UTC+3), every fresh `lastIndexedAt` will appear ~3h in the past for the entire 3-hour offset window.

Filed as CodeBoard BUG (link in CB-2077 update). Fix candidates:
- **Backend (preferred):** make `lastIndexedAt` (and friends) tz-aware UTC at the column / serializer level so the JSON includes the `Z` suffix. One-line change at `documentation_generator.py:1725` (`datetime.now(timezone.utc)`) plus matching read paths.
- **Frontend:** in `formatIndexedAt`, append `Z` if the ISO string lacks tz info before passing to `new Date`.
- **Both** (defense in depth).

This bug does **not** invalidate CB-2077's acceptance — the test only requires the timestamp to be newer after regenerate, which is true at the data layer and at the `datetime` attribute on the UI.

## Conclusion

CB-2077 → **COMPLETED_WAITING_QA**. Eli's manual QA promotes to DONE per Bible Rule 22.

Companion bug (UI relative-time off by browser TZ offset) filed as a child BUG under STORY CB-2067 so the audit trail stays in the same epic.
