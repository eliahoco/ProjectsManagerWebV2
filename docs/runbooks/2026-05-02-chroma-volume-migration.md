# Chroma volume migration — CB-2042

**Date:** 2026-05-02
**Story:** CB-2040 — Bring chroma container back, verify connection
**Task:** CB-2042 — Migrate `backend/data/chroma/*` to container volume `chroma_data`

## Context

Backend's RAG pipeline historically wrote embeddings to the embedded
`PersistentClient` fallback path `backend/data/chroma/` because the
`chromadb` Docker container was not running. CB-2041 brought the
container back up against the empty `projectsmanagerwebv2production_chroma_data`
volume. This task migrates the existing 17 MB of embeddings into that
volume so RAG queries hit the same data going forward.

## Source state (before)

Path: `backend/data/chroma/`

Collections (from local `chroma.sqlite3`):

| Collection         | Embeddings |
|--------------------|-----------:|
| project_1511e54f   |       1833 |
| project_cmkims9r   |        796 |
| project_linkedin   |        718 |
| project_cmkg0ww0   |          0 |
| project_cm9t37lz   |          0 |
| project_test       |          0 |
| project_test-pro   |          0 |
| project_issues     |          0 |

Total: 8 collections, 17.3 MB sqlite + 8 UUID dirs.

(Task description estimated 7 UUID dirs — actual count is 8.)

## Destination state (before)

Volume: `projectsmanagerwebv2production_chroma_data` (mounted to
`/chroma/chroma` in `chromadb` container).

Verified empty: 0 collections, 168 KB freshly-initialised
`chroma.sqlite3` only.

## Why a tar-stdin pipe (not a bind mount)

Colima's default file-sharing mounts do not include `/Volumes/Seagate/`.
A `docker run -v /Volumes/Seagate/.../chroma:/src ...` invocation shows
an empty `/src` inside the container. Using a `tar -cf - | docker run -i
... tar xf -` pipe sidesteps this — host `tar` reads the real files,
the stream is piped into the container's stdin, and the container
extracts directly into the volume mount.

## Procedure (executed)

```bash
# 1. Stop chromadb so sqlite is not held open.
docker compose stop chromadb

# 2. Confirm volume is empty (no data to lose).
docker run --rm -v projectsmanagerwebv2production_chroma_data:/dest \
  alpine:3.20 sh -c 'apk add --no-cache sqlite >/dev/null;
    sqlite3 /dest/chroma.sqlite3 "SELECT COUNT(*) FROM collections;"'
# -> 0

# 3. Tar source on host, extract into volume (overwrite the empty init).
cd backend/data/chroma
tar -cf - . | docker run -i --rm \
  -v projectsmanagerwebv2production_chroma_data:/dest \
  alpine:3.20 sh -c 'cd /dest && rm -rf ./* ./.[!.]* 2>/dev/null;
    tar xf -'

# 4. Normalise ownership to root (chroma container runs as root).
docker run --rm -v projectsmanagerwebv2production_chroma_data:/dest \
  alpine:3.20 sh -c 'chown -R 0:0 /dest && chmod -R u+rwX /dest'

# 5. Restart chromadb.
docker compose up -d chromadb
```

## Verification (after)

Heartbeat:

```
curl http://127.0.0.1:8402/api/v2/heartbeat
# -> {"nanosecond heartbeat": ...}
```

Collection list (`/api/v2/tenants/default_tenant/databases/default_database/collections`)
returns the same 8 collection IDs as the local sqlite.

Per-collection counts via `/collections/{id}/count`:

| Collection         | Local | Volume |
|--------------------|------:|-------:|
| project_1511e54f   |  1833 |   1833 |
| project_cmkims9r   |   796 |    796 |
| project_linkedin   |   718 |    718 |
| project_cmkg0ww0   |     0 |      0 |
| project_cm9t37lz   |     0 |      0 |
| project_test       |     0 |      0 |
| project_test-pro   |     0 |      0 |
| project_issues     |     0 |      0 |

All counts match exactly.

Functional regression: `/collections/{id}/get` against
`project_1511e54f` returns real document text + metadata (sample id
`c08dfda7ce0f61a20fd3483b965df7ef`, doc length 123, metadata `{key:
CB-9, type: STORY, ...}`). Embeddings, documents, metadatas all
materialise.

Per-file byte parity (source vs volume), every file in every UUID dir
plus `chroma.sqlite3` (18 182 144 bytes both sides) matches exactly via
`stat -c %s` / `stat -f %z`. The earlier `du -sh` size mismatch
(source ~3.0M vs volume ~1.7M per HNSW dir) was filesystem block-size
reporting overhead — APFS on macOS reports `du` higher than ext4 in
the colima VM, the underlying file bytes are identical.

Tenant/database compatibility: `backend/services/rag_service.py:81`
constructs `chromadb.HttpClient(host=host, port=port)` with no tenant
or database argument, which defaults to
`default_tenant`/`default_database` — matches the namespace under
which the migrated collections live.

## Rollback

The original `backend/data/chroma/` is untouched — this was a copy, not
a move. To roll back:

1. `docker compose stop chromadb`
2. `docker volume rm projectsmanagerwebv2production_chroma_data` (or
   wipe its contents through the alpine helper).
3. Backend's RAG client will fall back to `PersistentClient` on the
   local path again.

The local fallback should remain in place until CB-2043 confirms the
new RAG-mode log line shows `HTTP` and CB-2039's observability surface
shows hits flowing through the container.

## Follow-ups (not part of this task)

- CB-2043: surface `RAG mode (HTTP vs PERSISTENT)` in startup logs.
- After CB-2039 closes and HTTP mode is confirmed in production, the
  local `backend/data/chroma/` fallback can be deleted or moved to a
  backup path (separate ticket — do not delete here).
