"""CB-2217 follow-up tickets — file findings discovered by the
security-auditor pass on the CB-2217 fix that are out of scope for the
CB-2217 redaction itself.

The CB-2217 fix (omit `collections[].name` from /api/system/rag/status)
is tight inside its scope, but the security-auditor found four broader
threat-model surfaces that re-disclose equivalent data via different
endpoints. Per Bible Rule 23 these become their own CodeBoard tickets
under STORY CB-2047 (S1.3: E1 audit + regression) — the same audit
slot CB-2049 used for the original security pass.

Tickets filed:
  H-1: /api/projects enumerates full project CUID + path + name
       (defeats CB-2217's CUID-prefix redaction).
  H-2: /api/search/{project_id}/stats discloses per-project doc count
       (defeats anonymous `count` array via one extra hop).
  M-1: FastAPI default /docs /redoc /openapi.json enabled — publishes
       the full route map to any local Origin-less caller.
  L-2: describe_mode() startup INFO log emits PERSISTENT abspath —
       partial CB-2216 surface; logs persisted to disk re-disclose the
       path CB-2216 redacted from the HTTP payload.

Per Bible Rule 29 this script lives under
`scripts/codeboard/<date>-<slug>.py` so a parallel Claude session in
another project can't overwrite it via /tmp/.
"""

import json
import urllib.request

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
PARENT_ID = "c5f70d1e-9043-417a-b204-f2c653e9d743"  # STORY CB-2047


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def create(
    title: str,
    description: str,
    type_: str,
    priority: str,
    parent_id: str | None = None,
    **kwargs,
) -> dict:
    body = {
        "title": title,
        "description": description,
        "type": type_,
        "priority": priority,
        "reporter": "AI",
        **kwargs,
    }
    if parent_id:
        body["parentId"] = parent_id
    return post(f"/projects/{PROJECT_ID}/issues", body)


def main() -> None:
    findings = [
        {
            "title": (
                "[CB-2217 sec follow-up H-1] HIGH: /api/projects enumerates "
                "full project CUID + path + name (defeats CB-2217 redaction)"
            ),
            "description": (
                "**Severity:** HIGH (re-disclosure of the data CB-2217 just "
                "redacted, via a sibling endpoint; same threat model)\n\n"
                "**Location:** `backend/api/projects.py:16-39`\n\n"
                "**Problem**\n\n"
                "`GET /api/projects` returns the full project list to any "
                "local Origin-less caller (the validate_origin middleware in "
                "`backend/app/main.py` lets server-to-server requests "
                "through by design). Each row contains:\n"
                "- `id` — the FULL CUID (CB-2217 just redacted the 8-char "
                "  prefix from /api/system/rag/status)\n"
                "- `path` — the absolute filesystem path of the project "
                "  directory (worse than the CB-2216 PERSISTENT-mode abspath "
                "  leak that just shipped)\n"
                "- `name`, `description`, `type`, `version`\n\n"
                "An attacker with any local foothold can `curl /api/projects` "
                "and recover the full pre-CB-2217 picture in one request — "
                "the CB-2217 redaction of `collections[].name` is rendered "
                "moot.\n\n"
                "**Found in:** security-auditor pass on CB-2217 fix "
                "(2026-05-08).\n\n"
                "**Fix options**\n\n"
                "- Apply consistent perimeter discipline: gate read endpoints "
                "  behind a loopback-token / shared-secret check when "
                "  `ALLOW_LAN=true`, OR\n"
                "- Accept that `/api/system/rag/status` was never the weakest "
                "  link and re-evaluate whether CB-2217's redaction is the "
                "  right priority vs auth-perimeter work.\n\n"
                "**Reproduction**\n\n"
                "```bash\n"
                "curl http://localhost:8401/api/projects | jq '.[0]'\n"
                "# returns: {\"id\":\"<full-cuid>\",\"path\":\"/abs/path\",...}\n"
                "```"
            ),
            "type_": "BUG",
            "priority": "HIGH",
            "labels": "security,cb-2217-followup,documentation-surface",
        },
        {
            "title": (
                "[CB-2217 sec follow-up H-2] HIGH: /api/search/{project_id}/"
                "stats discloses per-project doc count (defeats anonymous "
                "collections[] via one hop)"
            ),
            "description": (
                "**Severity:** HIGH (re-binds the anonymous `count` array "
                "from CB-2217 to specific project_ids in one extra request)\n\n"
                "**Location:** `backend/api/search.py:190-212`\n\n"
                "**Problem**\n\n"
                "`GET /api/search/{project_id}/stats` returns "
                "`{project_id, indexed_count, ...}` for any caller-supplied "
                "project_id. Combined with H-1 (full project enumeration via "
                "/api/projects) an attacker can:\n\n"
                "1. `GET /api/projects` → list of all project_ids\n"
                "2. For each project_id: `GET /api/search/{id}/stats` → "
                "   per-project indexed doc count bound to a real project_id\n\n"
                "This defeats the entire point of CB-2217's anonymization — "
                "the `count` distribution that CB-2217 tried to make "
                "non-attributable becomes attributable in one extra hop.\n\n"
                "**Found in:** security-auditor pass on CB-2217 fix "
                "(2026-05-08).\n\n"
                "**Fix options**\n\n"
                "- Same authn perimeter as H-1 — these endpoints share the "
                "  threat model.\n"
                "- OR collapse `indexed_count` into the same redaction "
                "  discipline as CB-2217 (return only aggregate, never "
                "  per-project).\n"
            ),
            "type_": "BUG",
            "priority": "HIGH",
            "labels": "security,cb-2217-followup,documentation-surface",
        },
        {
            "title": (
                "[CB-2217 sec follow-up M-1] MEDIUM: FastAPI /docs + "
                "/openapi.json publish full route map to any local caller"
            ),
            "description": (
                "**Severity:** MEDIUM (reconnaissance — publishes every "
                "route, schema, and parameter shape to any Origin-less "
                "local caller)\n\n"
                "**Location:** `backend/app/main.py:339-344` "
                "(FastAPI() constructed without docs_url=None / "
                "redoc_url=None / openapi_url=None)\n\n"
                "**Problem**\n\n"
                "`/docs`, `/redoc`, and `/openapi.json` are enabled by "
                "default. An attacker who finds /api/projects or "
                "/api/system/rag/status via H-1/H-2 can also fetch "
                "/openapi.json to enumerate every route, every project_id "
                "path param, every request/response schema — substantial "
                "reconnaissance arbitrage on top of the explicit data leaks.\n\n"
                "Note: the CURRENT /openapi.json schema correctly drops "
                "`name` from RagCollectionStatus (CB-2217 is reflected). "
                "This ticket is about the surface map, not schema "
                "re-disclosure.\n\n"
                "**Found in:** security-auditor pass on CB-2217 fix "
                "(2026-05-08).\n\n"
                "**Fix**\n\n"
                "- Disable in non-dev: `FastAPI(docs_url=None, "
                "  redoc_url=None, openapi_url=None)` when "
                "  settings.ENVIRONMENT != 'dev'.\n"
                "- OR gate behind same loopback-token / shared-secret as "
                "  H-1/H-2 if/when that lands.\n"
            ),
            "type_": "BUG",
            "priority": "MEDIUM",
            "labels": "security,cb-2217-followup,documentation-surface",
        },
        {
            "title": (
                "[CB-2217 sec follow-up L-2] LOW: describe_mode() startup "
                "INFO log emits PERSISTENT abspath (re-disclosure of the "
                "CB-2216 redaction via log file)"
            ),
            "description": (
                "**Severity:** LOW (off-band re-disclosure of the abspath "
                "CB-2216 just redacted from the HTTP payload)\n\n"
                "**Location:** `backend/services/rag_service.py:188-190` "
                "(describe_mode emits `path={self._endpoint}`), "
                "`backend/app/main.py:275` (lifespan logs it at INFO via "
                "`[startup] %s`)\n\n"
                "**Problem**\n\n"
                "CB-2216 redacted the PERSISTENT-mode abspath from "
                "/api/system/rag/status's HTTP payload because the endpoint "
                "is reachable by any local Origin-less caller. But the boot "
                "log line still contains the abspath at INFO level — any "
                "attacker with read access to `logs/backend.log`, journald, "
                "or a captured stdout pipe recovers exactly what CB-2216 "
                "redacted.\n\n"
                "Same finding applies (less severely) to the CB-2217 "
                "diagnostic log: `count() failed for collection %s` at "
                "`rag_service.py:322-325` keeps the redacted-from-payload "
                "name in DEBUG-level logs (which are gated by INFO default — "
                "but a future operator flipping to DEBUG restores the leak).\n\n"
                "**Found in:** security-auditor pass on CB-2217 fix "
                "(2026-05-08), L-1 + L-2.\n\n"
                "**Fix options**\n\n"
                "- describe_mode(): log a stable hash of the abspath "
                "  (`hashlib.blake2s(path, digest_size=4).hexdigest()`) "
                "  instead of the literal path.\n"
                "- count() failed log: switch from `name` to collection "
                "  index (`#%d`).\n"
                "- Belt+suspenders: file rotation + restrictive log "
                "  permissions on `logs/backend.log`.\n"
            ),
            "type_": "BUG",
            "priority": "LOW",
            "labels": "security,cb-2217-followup,cb-2216-followup,documentation-surface",
        },
    ]

    created = []
    for finding in findings:
        result = create(parent_id=PARENT_ID, **finding)
        created.append((result["key"], finding["priority"], finding["title"]))
        print(f"  {result['key']} ({finding['priority']}): {finding['title']}")

    print(f"\n  Created {len(created)} follow-up tickets under STORY CB-2047.")


if __name__ == "__main__":
    main()
