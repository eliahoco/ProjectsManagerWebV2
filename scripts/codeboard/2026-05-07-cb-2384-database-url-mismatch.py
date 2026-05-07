"""
CB-2384 — File BUG: GitHub Settings Test fails because frontend/.env DATABASE_URL
points to non-existent file:./dev.db; actual DB is at file:./prisma/dev.db.
Parent: CB-639 (Auto Pilot Execution feature) — adjacent infra issue.
"""
import json, urllib.request, sys

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"

TITLE = (
    "GitHub Settings 'Test' button fails 500 — DATABASE_URL in frontend/.env "
    "points to non-existent ./dev.db (actual DB is ./prisma/dev.db)"
)

DESCRIPTION = """## Bug

`/api/github/test` returns HTTP 500 with generic `"Failed to test GitHub
configuration"`. Same applies to `GET /api/github/test`. Settings page
"Test" button therefore never succeeds — user cannot configure GitHub
auth from the UI.

## Real error (from next-server stdout)

```
PrismaClientInitializationError:
Invalid `prisma.setting.upsert()` invocation
  error: Error validating datasource `db`: the URL must start with the protocol `file:`.
    -->  schema.prisma:10
       | url = env("DATABASE_URL")
```

## Root cause

`frontend/.env` line 4:
```
DATABASE_URL="file:./dev.db"
```

The actual database file is at `frontend/prisma/dev.db`. The reference
file `frontend/.env.example` has the correct value:
```
DATABASE_URL="file:./prisma/dev.db"
```

Most Prisma calls work because the singleton client was instantiated
once at server startup with whatever env was in scope then. The
`/api/github/test` route triggers a fresh Prisma codegen evaluation
under turbopack route-isolation, which re-reads `env("DATABASE_URL")`
and gets the bad path.

## Reproduction

1. Open Settings page → GitHub Configuration section.
2. Fill in any username + email.
3. Click `Test`.
4. Observe failure toast / no-op.

Or via curl:
```
curl -s -X POST http://localhost:3601/api/github/test \\
  -H 'Content-Type: application/json' \\
  -d '{"username":"x","email":"y@z"}'
# {"success":false,"error":"Failed to test GitHub configuration"}
```

## Fix

Single-line `.env` change:
```diff
- DATABASE_URL="file:./dev.db"
+ DATABASE_URL="file:./prisma/dev.db"
```

Then restart `next-server`.

## Acceptance criteria

- [ ] `frontend/.env` `DATABASE_URL` matches `.env.example` and points to
      the actual DB file.
- [ ] `POST /api/github/test` with valid username/email returns
      `{"success": true, ...}`.
- [ ] `GET /api/github/test` returns `success: true` with
      `gitInstalled`, `globalConfig.username`, `globalConfig.email`,
      `savedConfig.hasToken`.
- [ ] Settings page Test button shows success state.
- [ ] No regression: other Prisma-backed endpoints (`/api/projects`,
      `/api/codeboard/projects/{id}/issues`) continue to return 200
      after restart.

## Out of scope

The route's catch block swallows the underlying Prisma error and
returns generic `"Failed to test GitHub configuration"`. That's a UX
bug — but separate from the env fix. Track as follow-up if needed.

## Related

- `frontend/.env`, `frontend/.env.example`
- `frontend/lib/db.ts` (Prisma singleton)
- `frontend/prisma/schema.prisma` (datasource)
- `frontend/app/api/github/test/route.ts` (the failing handler)
"""


def call(method, path, body=None):
    headers = {"Content-Type": "application/json"} if body else {}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def main():
    body = {
        "title": TITLE,
        "description": DESCRIPTION,
        "type": "BUG",
        "priority": "HIGH",
        "labels": "infra,settings,prisma,env-config",
        "assignee": "debugger",
        "reporter": "AI",
    }
    issue = call("POST", f"/projects/{PROJECT_ID}/issues", body)
    print(f"Created {issue['key']} (id={issue['id']})")
    call("PATCH", f"/issues/{issue['id']}", {"status": "IN_PROGRESS"})
    print("  → status=IN_PROGRESS")
    return issue["key"], issue["id"]


if __name__ == "__main__":
    try:
        key, _id = main()
        print(f"\nDONE — file: {key}")
        print(f"id: {_id}")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        sys.exit(1)
