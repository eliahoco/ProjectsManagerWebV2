# CodeBoard Backlog Audit — 2026-05-19

Prepared by Jonny (VP R&D) at Eli's request. Plain-language picture of everything
unfinished on the board, plus data-integrity problems found along the way.

## The numbers (database truth vs what the UI shows)

| | CodeBoard UI header | Actual database |
|---|---|---|
| Total issues | ~500 | **2,512** |
| Backlog | ~325 | **802** |
| In progress | 3 | 4 |

**The UI is badly under-reporting.** The database has 2,512 issues; the board header
shows ~500. This is the discrepancy Eli sensed. → needs a bug ticket.

Full status breakdown (database): 1,521 waiting-QA · 802 backlog · 106 done ·
75 cancelled · 4 todo · 4 in-progress.

3 features hold **58% of the entire backlog**: Studio (276), Intelligent Docs (96),
Stack Stabilization (93). It is not 802 random things — it is a few big blocks.

## Unfinished work — the real list (nothing completed shown)

### A. Never started (untouched)

| Key | Feature | Pri | Tasks | What it is |
|-----|---------|-----|-------|------------|
| CB-2384 | **AI Project Workspace — Studio** | CRITICAL | 276 | New workspace layer above CodeBoard: a chat-based **Studio** for planning features with Claude, a **Backlog** staging board before CodeBoard, and a **Crew Map** graph of how issues connect. The biggest single unbuilt thing. |
| CB-1734 | **Stack Stabilization & Security Hardening** | CRITICAL | 93 | 33 days of small stability bugs piled up (dead watchdog, leftover CLI processes, etc.). This feature is the systematic cleanup. |
| CB-1203 | Intelligent Documentation System | HIGH | 96 | Auto-capture implementation knowledge as work happens and reuse it across the project lifecycle. |
| CB-1667 | Backend-Driven AutoPilot Queue | HIGH | 32 | Move AutoPilot's run loop from the browser into the backend. **Likely mostly obsolete** — CB-1951/2746/2793 already did much of this. Needs a relevance review before any work. |
| CB-1950 | AutoPilot follows Jonny's bible | HIGH | 0 | Make AutoPilot's sub-sessions obey the discipline rules (file tickets, run audits). Not broken down yet. |
| CB-2121 | Backend auth + project scoping | MEDIUM | 0 | Real per-project authorization on all API endpoints. **This is the proper fix** for the IDOR weakness left open by today's CB-2802 work. Not broken down yet. |
| CB-2381 | AI Execution Cost Optimization | HIGH | 0 | Cut token spend. **Intentionally parked by Eli on 2026-05-07** — full plan already written in `docs/plans/2026-05-07-ai-execution-cost-optimization.md`. |

### B. Started, work still open

| Key | Feature | Pri | Tasks left | What is still open |
|-----|---------|-----|-----------|--------------------|
| CB-1955 | Issue Correlation & Grouping | HIGH | 8 | Link related issues (duplicates, blocks…) + named issue groups. Nearly closed. |
| CB-2746 | **Bulletproof AutoPilot** | CRITICAL | 11 | Make AutoPilot survive any crash/kill/reboot and still finish. The active AutoPilot-hardening line. |
| CB-1406 | Service Watchdog | HIGH | 23 | Auto-restart services that crash. |
| CB-1271 | Port Validation & Registry | HIGH | 84 | Stop projects grabbing each other's ports on launch. |

### C. Loose todo tasks (no feature context)

| Key | Status | What it is |
|-----|--------|------------|
| CB-1690 | TODO | Test AutoPilot queue lifecycle (create, run, complete) |
| CB-1691 | TODO | Test AutoPilot control commands (pause, resume, skip, abort) |
| CB-1693 | TODO | Security review of AutoPilot queue API endpoints |

## Data-integrity problems found

1. **UI count wrong** — board shows ~500, database has 2,512.
2. **176 orphan issues** — tasks/stories/bugs with no resolvable parent (136 in backlog). They float free of any feature.
3. **Duplicate features** — "Port Validation & Registry" exists 3× (CB-1269, CB-1270, CB-1271 — only 1271 is real). "Issue Correlation & Grouping" exists 2× (CB-1955 real + IN_PROGRESS, CB-2128 mostly cancelled).
4. **Stale parent status** — CB-1700 children all done, parent still BACKLOG.
5. **Test/junk features on the board** — CB-2767 "QA Test Feature", CB-2349 "cascade-test STORY" are sitting IN_PROGRESS as if real work.

## Recommended order (Jonny's call — Eli decides)

1. **Clean the board first** (½ day) — kill duplicates (CB-1269/1270/2128), remove test junk (CB-2767/2349), re-home or close the 176 orphans, fix CB-1700's stale status, file a bug for the UI count. Without this, any plan is built on noise.
2. **Finish the near-done** — CB-1955 (8 left) and CB-2746 (11 left). Quick wins, real value.
3. **CB-1734 Stack Stabilization** (CRITICAL) — stop the daily stability pain before building anything new.
4. **Decide on CB-2384 Studio** — the 276-task flagship. Needs its own planning session; do not start blind.
5. Defer: CB-1203 (Docs), CB-1271 (Ports), CB-1406 (Watchdog), CB-2381 (already parked), CB-1667 (review for obsolescence first).
