# CB-2038 Documentation Surface — Session Resume

**Last session:** 2026-05-04 pre-reboot
**Status:** ~50/76 tickets CWQ. 26 commits on local `main` (unpushed). Code on disk, not yet running live.

---

## Restart sequence (when PC comes back)

```bash
cd /Volumes/Seagate/Claude/ProjectsManagerWebV2Production

# 1. Bring up colima + docker
colima start
docker compose up -d chromadb     # 8402
curl http://localhost:8402/api/v2/heartbeat   # expect 200

# 2. Launch backend + frontend
./launch.sh                       # backend 8401, frontend 3601, chroma 8402

# 3. Verify backend loaded new code
tail -f logs/backend.log | head -50
# Expect: "[startup] RAG mode=HTTP host=chromadb port=8000 collections=N"
# Expect: "Started background task for doc retention"

# 4. Smoke check new endpoints
curl http://localhost:8401/api/documentation/settings
# expect 200 with {key:"global",autoGenerate:true,retentionDays:90,maxPerIssue:20}

curl http://localhost:8401/api/documentation/summaries?limit=5
# expect 200 with array

curl http://localhost:8401/api/system/rag/status
# expect 200 with {mode:"HTTP", collections:[...]}
```

---

## What landed (committed on main)

| Slice | Commit | Tickets |
|---|---|---|
| Backend doc generator | `2cbc0a0` | CB-2107 (T4.2.1) |
| QA + RAG + terminal hooks + completion atomicity (F1) | `ce6c7dc` | CB-2108 (T4.2.2), CB-2116 |
| ImplementationTab UI + hooks | `c4e8560` | CB-2109 (T4.2.3) |
| Cleanup + plan scripts to scripts/ | `60f7461` | CB-2110 (T4.2.4) |
| E3 backend (DocSettings + retention + autoGenerate gate) | `eb149e4` | CB-2079..2083 |
| E2 frontend (FeatureDocumentation page + view + button + tab) | `655ff46` | CB-2055..2066 |
| H1+H2 retention fixes | `4749b9b` | CB-2122, CB-2124 |
| E3 frontend settings page + H3 PATCH fix | `d0dfcb5` + `6c9f683` | CB-2084..2088, CB-2125 |

Plus: AutoPilot did entire E1 epic (chroma container restoration + RAG status endpoint + Service Monitor card). CB-2039..2050 mostly CWQ.

---

## Audit findings — all CRITICAL+HIGH fixed

| BUG | Severity | Status | Fix |
|---|---|---|---|
| CB-2116 F1 | CRITICAL | ✅ CWQ | per-session txn in `process_pending_completions` |
| CB-2117 F2 | HIGH | DEFERRED → CB-2121 follow-up | needs auth layer |
| CB-2118 F3 | HIGH | ✅ CWQ | per-item caps + URL-scheme rejection on `references` |
| CB-2119 F4 | HIGH | ✅ CWQ | `validate_project_path` in `_capture_git_changes` |
| CB-2120 F5 | HIGH | ✅ CWQ | `cmd[0]=='git'` shape check |
| CB-2122 M1 | MEDIUM | ✅ CWQ | retention boundary-timestamp delete (no NOT IN list) |
| CB-2123 M2 | MEDIUM | OPEN | retention batching — operational scale only, deferred |
| CB-2124 H1 | HIGH | ✅ CWQ | retention 60s first-pass delay |
| CB-2125 H3 | HIGH | ✅ CWQ | drop manual `updatedAt` mutation |

Follow-up filed: **CB-2121** = Add backend auth layer + project scoping (out of scope of CB-2038).

---

## Open work after reboot

### Mine (Jonny does)

1. **T4.1.4 regression (CB-2105)** — needs running backend + chroma. Trigger AI exec on test issue → verify ExecutionSummary → verify Chroma container volume has new entry → verify ImplementationTab renders. Mark CWQ.
2. **T3.3.3 Chrome QA on Settings page (CB-2092)** — needs backend live. Open `/settings/documentation`, screenshot, verify toggle persists.
3. **T3.3.4 E3 regression (CB-2093)** — toggle autoGenerate off → run exec → no summary. On → run exec → summary. retentionDays=0 + trigger purge → verify.
4. **Roll up parent stories/epics** in CodeBoard once children all CWQ.

### Yours (Eli — manual QA per Rule 22)

14 BACKLOG QA verification tickets need your manual run before promoting to DONE:

| Ticket | Test |
|---|---|
| CB-2051 | Chroma container UP, heartbeat passes, port 8402 |
| CB-2052 | `/api/system/rag/status` returns `mode=HTTP` after compose up |
| CB-2053 | Service Monitor card renders RAG mode + collection count |
| CB-2073 | FEATURE issue with no docs → empty state + Generate CTA |
| CB-2074 | Click Generate → 6 sections populate + metrics card |
| CB-2075 | Click Generate twice → only ONE FeatureDocumentation row |
| CB-2076 | techStack JSON `["FastAPI","Next.js"]` → 2 badges |
| CB-2077 | Regenerate → lastIndexedAt timestamp updates |
| CB-2094 | Settings: toggle autoGenerate off → reload → still off |
| CB-2095 | autoGenerate=false → exec → no new ExecutionSummary row |
| CB-2096 | Old ExecutionSummary (100d) + retentionDays=90 → row gone after retention pass |
| CB-2097 | maxPerIssue=20 → 25 summaries → only newest 20 remain |
| CB-2098 | Recent summaries list newest-first, ≤20 |
| CB-2099 | Re-trigger button → exec session in GlobalAgentStatusBar |
| CB-2111 | Issue with prior exec → Implementation tab renders all sections |
| CB-2112 | Add note → persists → reload → still there |
| CB-2113 | Delete note → 204 → list refreshes |

---

## Critical reminders

- **NEVER promote DONE** — only Eli does that (Bible Rule 22)
- **NEVER push to origin** without Eli explicit approval
- **CB-1958 / CB-1998 AutoPilot** — Eli's autonomous execution, do not interfere
- **Ollama investigation** — saved as separate memory `project_ollama_investigation.md`. Anthropic API hit 100% currently; Ollama down (port 11434).

---

## Blockers (none active after reboot)

Pre-reboot blockers (all resolved by restart):
- ❌ Backend old bytecode → fixed by relaunch
- ❌ Chroma container down → may need `docker compose up -d chromadb` after colima start
- ❌ Active AutoPilot sessions → reboot kills them

---

## Branch state

```
26 commits ahead of origin/main, branch=main, clean (post-reboot ignore .pyc/.next regenerated)
```

Last commit: `6c9f683 CB-2084..CB-2088 (cont): schemas + hooks + tests for E3 frontend`
