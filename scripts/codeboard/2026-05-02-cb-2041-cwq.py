"""Mark CB-2041 (chromadb container up + heartbeat) COMPLETED_WAITING_QA.

Per Bible Rule 22: code complete -> COMPLETED_WAITING_QA, never DONE.
Per Bible Rule 29: per-project per-session script path (not /tmp/).
"""
import json
import urllib.request

API = "http://localhost:8401/api"
ISSUE_ID = "55170881-3cb5-4cf4-ab3e-f4685f958673"  # CB-2041

payload = json.dumps({
    "status": "COMPLETED_WAITING_QA",
    "implementationSummary": (
        "Restored chromadb container availability. Colima docker socket "
        "had gone stale; `colima restart` brought the daemon back, and "
        "the chromadb container auto-started via its `restart: "
        "unless-stopped` policy (image chromadb/chroma:0.6.3, container "
        "name projectsmanagerwebv2production-chromadb-1). Verified the "
        "service end-to-end: `curl http://localhost:8402/api/v2/"
        "heartbeat` returns HTTP 200 with body "
        "`{\"nanosecond heartbeat\":1777751663389999091}`. Backend env "
        "(backend/.env, backend/app/config.py) already targets "
        "localhost:8402, and the lifespan path in backend/app/main.py "
        "(lines 256-269) calls rag._init_client_blocking() first - which "
        "does a 5s TCP probe and a heartbeat() call - and only falls "
        "back to PersistentClient on exception. Both the probe and the "
        "heartbeat now succeed, so any subsequent backend boot lands in "
        "HTTP mode."
    ),
    "technicalApproach": (
        "No code changes - operational verification only. Steps run: "
        "(1) `colima status` -> running; (2) `docker ps` -> daemon "
        "unreachable (stale socket at /Users/elic/.colima/default/"
        "docker.sock); (3) `colima restart` -> daemon back, chromadb "
        "container auto-started; (4) `curl localhost:8402/api/v2/"
        "heartbeat` -> HTTP 200; (5) reviewed backend/services/"
        "rag_service.py (HttpClient init at line 81, fallback at "
        "line 95) and backend/app/main.py lifespan (line 256-269). "
        "Caveat for QA: the currently running backend (PID 47371, "
        "started ~18:35 IDT, before chromadb came back up) is still "
        "in PersistentClient fallback mode from its boot. Did NOT "
        "restart it because it was hosting the active execution "
        "session for THIS task (CB-2041) and a kill would have torn "
        "down the work in flight. Sibling task CB-2042 (migrate "
        "backend/data/chroma/* to chroma_data volume) requires a "
        "backend restart anyway and will pick up HTTP mode at that "
        "boot. Sibling CB-2043 (startup log line surfacing RAG mode) "
        "will lock in observability so this kind of silent fallback "
        "is impossible going forward. Audit gates: code-reviewer / "
        "security-auditor NA (no code diff); functional verification "
        "= the heartbeat curl + lifespan code review captured above; "
        "Chrome UI verification NA (no UI surface)."
    ),
}).encode()

req = urllib.request.Request(
    f"{API}/issues/{ISSUE_ID}",
    data=payload,
    method="PATCH",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as r:
    body = r.read().decode()
    print(f"HTTP {r.status}")
    print(body[:600])
