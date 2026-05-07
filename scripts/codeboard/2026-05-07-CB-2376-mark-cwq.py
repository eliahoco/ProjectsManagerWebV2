"""Mark CB-2376 COMPLETED_WAITING_QA + append implementation summary.

CB-2376: useGenerateFeatureDocumentation now invalidates on both success and
error via `onSettled`. Two Vitest cases added (success + 504 error path).
Code review + security audit clean.
"""
import json
import urllib.request

ISSUE_ID = "ece846c8-3b9a-4cd1-a169-4b333caaee98"
URL = f"http://localhost:8401/api/issues/{ISSUE_ID}"

summary = (
    "Added defence-in-depth cache invalidation to useGenerateFeatureDocumentation. "
    "Replaced onSuccess-only invalidation with onSettled so the "
    "['feature-documentation', issueId, projectId] query invalidates regardless "
    "of HTTP outcome — fixes the stale-UI symptom that surfaces when the "
    "Next.js proxy returns 504 (CB-2375) but the backend has already persisted "
    "the documentation row.\n\n"
    "Files changed:\n"
    "- frontend/hooks/useCodeBoard.ts (useGenerateFeatureDocumentation: onSuccess → onSettled)\n"
    "- frontend/tests/hooks/useCodeBoard.test.ts (added describe block: success-path + 504-error-path)\n\n"
    "Audits:\n"
    "- code-reviewer: no CRITICAL/HIGH/MEDIUM. LOW: suggested onSettled consolidation — applied.\n"
    "- security-auditor: SECURITY-NEUTRAL — pure client-side cache invalidation, no new attack surface.\n\n"
    "Tests: 44/44 green (tests/hooks + FeatureDocumentationView). tsc --noEmit clean on changed files."
)

payload = json.dumps({
    "status": "COMPLETED_WAITING_QA",
    "implementationSummary": summary,
}).encode("utf-8")

req = urllib.request.Request(
    URL,
    data=payload,
    method="PATCH",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    body = resp.read().decode("utf-8")
    data = json.loads(body)
    print(f"OK {data['key']} -> {data['status']}")
