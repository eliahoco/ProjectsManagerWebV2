"""
File BUG: Sync UI Push handler returns false-negative on clean tree.
Parent: CB-639 (Auto Pilot Execution / git surface).
"""
import json, urllib.request, sys

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"

TITLE = (
    "GitHub Sync 'Push' button returns failure on clean tree — "
    "stderr-only check misses 'nothing to commit' (in stdout)"
)

DESCRIPTION = """## Bug

Pressing the **Push** button on the `/github` tab (or via direct
`POST /api/github/sync {action:'push'}`) returns
`{"success": false, "error": "On branch main\\nYour branch is up to date "
"with 'origin/main'.\\n\\nnothing to commit, working tree clean\\n"}`
even when the working tree is clean and the local branch is in sync
with origin.

Users see this as a failure. There is no actual failure — there is
nothing to push.

## Root cause

Two stale `stderr.includes('nothing to commit')` checks; git writes
that line to **stdout**, not stderr.

`frontend/lib/shell.ts:811`:
```ts
if (commitResult.exitCode === 0 || commitResult.stderr.includes('nothing to commit')) {
  return execCommand('git push', ...);
}
return commitResult;  // ← falls through here on clean tree
```

`frontend/app/api/github/sync/route.ts:122`:
```ts
const isSuccess = result.exitCode === 0 || result.stderr.includes('nothing to commit');
```

Real `git commit -m ...` output on a clean tree:
- exitCode: `1`
- stdout: `On branch main\\nYour branch is up to date with 'origin/main'.\\n\\nnothing to commit, working tree clean\\n`
- stderr: empty

Both checks fail → push is skipped → handler reports failure.

## Reproduction

```bash
curl -s -X POST http://localhost:3601/api/github/sync \\
  -H 'Content-Type: application/json' \\
  -d '{"projectId":"1511e54f71dccd3fa79f67fe","action":"push"}'
# {"success":false,"error":"... nothing to commit, working tree clean ..."}
```

Pre-condition: working tree clean + local branch up to date with origin.

## Suggested fix

### 1. `frontend/lib/shell.ts:800-816`
Change the gate to scan **stdout + stderr** for `'nothing to commit'`:
```ts
const combined = (commitResult.stdout || '') + '\\n' + (commitResult.stderr || '');
if (commitResult.exitCode === 0 || combined.includes('nothing to commit')) {
  return execCommand('git push', { cwd: projectPath, timeout: 60000 });
}
```

### 2. `frontend/app/api/github/sync/route.ts:105-144`
Short-circuit on the empty case **before** running `syncToGitHub`:
```ts
// Already in sync — nothing to do
const ahead = await execCommand('git rev-list --count @{u}..HEAD', {
  cwd: project.path,
});
if (!gitStatus.isDirty && ahead.stdout.trim() === '0') {
  return NextResponse.json({
    success: true,
    data: { output: 'Nothing to push — branch up to date.', exitCode: 0, gitStatus },
  });
}
```

Also fix `isSuccess` to scan stdout:
```ts
const combined = (result.stdout || '') + '\\n' + (result.stderr || '');
const isSuccess = result.exitCode === 0 || combined.includes('nothing to commit');
```

## Acceptance criteria

- [ ] Push on a clean tree (no dirty files, ahead=0) returns
      `{"success": true, "data": {"output": "Nothing to push — branch up to date." ...}}`
      and does not invoke `syncToGitHub`.
- [ ] Push with dirty files but no remote-side changes still works
      (commits + pushes).
- [ ] Push when branch is ahead but tree clean — pushes the existing
      commits (not blocked by the "nothing to commit" detection).
- [ ] No regression on Pull.

## Out of scope (file separately)

The deeper UX issue — Push button **auto-commits all dirty files**
with a generic `Update <name> - YYYY-MM-DD` message. Users expect
"push" to push existing commits, not auto-commit. This is a separate
STORY (split Commit and Push, or remove auto-commit entirely).

## Related

- `frontend/lib/shell.ts:syncToGitHub` (line ~800)
- `frontend/app/api/github/sync/route.ts:POST` handler (line ~53)
- `frontend/app/github/page.tsx` (Pull/Push buttons)
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
        "priority": "MEDIUM",
        "labels": "github-sync,frontend,false-negative,push-handler",
        "assignee": "typescript-pro",
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
