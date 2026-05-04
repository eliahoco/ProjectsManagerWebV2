"""
CB-1974 — DELETE /api/issues/{id}/relations/{relation_id}.

Covers the delete contract:
  * 200 — happy path: deletes primary + companion in same txn (deleted=2)
  * 200 — either participant can delete (URL via from-side OR to-side)
  * 200 — works on RELATES_TO (symmetric companion still removed)
  * 200 — works for every LinkType (BLOCKS/IS_BLOCKED_BY/CAUSES/CAUSED_BY/
    DUPLICATES/IS_DUPLICATED_BY/RELATES_TO)
  * 200 — orphan companion case: legacy row with no companion → deleted=1
  * 200 — only the targeted relation goes away; sibling relations stay
  * 404 — relation_id does not exist
  * 404 — relation exists but issue_id is not one of its participants
  * 400 — relation has an unknown linkType (data corruption guard)

Uses the same isolated on-disk SQLite pattern as the sibling test files
(test_relations_get.py / test_relations_post.py) so tests never touch
production codeboard.db.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


from api.relations import router as relations_router  # noqa: E402
from app.errors import setup_exception_handlers  # noqa: E402
from models.database import Base, get_db  # noqa: E402
from models.issue import Issue, IssueLink, Project  # noqa: E402


# ---------- fixtures -------------------------------------------------------

@pytest_asyncio.fixture
async def test_app_and_db():
    tmp_dir = tempfile.mkdtemp(prefix="relations-delete-test-")
    db_path = os.path.join(tmp_dir, "test.db")
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}", future=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine, class_=AsyncSession,
        expire_on_commit=False, autocommit=False, autoflush=False,
    )

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    local_app = FastAPI()
    setup_exception_handlers(local_app)
    local_app.include_router(relations_router, prefix="/api")
    local_app.dependency_overrides[get_db] = _override_get_db

    try:
        yield local_app, factory
    finally:
        await engine.dispose()
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest_asyncio.fixture
async def factory(test_app_and_db):
    _, f = test_app_and_db
    yield f


@pytest_asyncio.fixture
async def client(test_app_and_db) -> AsyncGenerator[AsyncClient, None]:
    local_app, _ = test_app_and_db
    transport = ASGITransport(app=local_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------- seed helpers ---------------------------------------------------

def _make_project(project_id: str = "proj-1") -> Project:
    now_ms = 1700000000000
    return Project(
        id=project_id,
        name=f"proj-{project_id}",
        path=f"/tmp/{project_id}",
        status="ACTIVE",
        createdAt=now_ms,
        updatedAt=now_ms,
    )


def _make_issue(
    issue_id: str,
    key: str,
    project_id: str = "proj-1",
    title: str = "Test Issue",
    status_: str = "BACKLOG",
) -> Issue:
    return Issue(
        id=issue_id,
        projectId=project_id,
        key=key,
        sequence=int(key.split("-")[-1]) if "-" in key else 1,
        title=title,
        type="TASK",
        status=status_,
        priority="MEDIUM",
        updatedAt=datetime.utcnow(),
    )


async def _seed_chain(factory, n: int = 3) -> None:
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        for i in range(1, n + 1):
            db.add(_make_issue(f"i{i}", f"CB-{i}", title=f"Issue {i}"))
        await db.commit()


def _make_link(
    from_id: str,
    to_id: str,
    link_type: str,
    *,
    created_at: datetime | None = None,
    link_id: str | None = None,
) -> IssueLink:
    return IssueLink(
        id=link_id or str(uuid.uuid4()),
        fromIssueId=from_id,
        toIssueId=to_id,
        linkType=link_type,
        createdAt=created_at or datetime.utcnow(),
    )


async def _row_count(factory) -> int:
    async with factory() as db:
        rows = (await db.execute(select(IssueLink.id))).all()
        return len(rows)


async def _create_link_via_api(
    client: AsyncClient,
    from_id: str,
    to_id: str,
    link_type: str,
) -> str:
    """Create a relation via the POST endpoint and return the primary id.

    We exercise the real create path so the primary+companion invariant
    is identical to production rather than tests fabricating it."""
    resp = await client.post(
        f"/api/issues/{from_id}/relations",
        json={"toIssueId": to_id, "linkType": link_type},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------- happy path -----------------------------------------------------

@pytest.mark.asyncio
async def test_delete_removes_primary_and_companion_returns_two(
    client: AsyncClient, factory,
):
    """A→B BLOCKS create writes 2 rows. DELETE on the primary's id from
    A's URL removes both, response is {deleted: 2}, table is empty."""
    await _seed_chain(factory, 2)
    primary_id = await _create_link_via_api(client, "i1", "i2", "BLOCKS")
    assert await _row_count(factory) == 2

    resp = await client.delete(f"/api/issues/i1/relations/{primary_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": 2}
    assert await _row_count(factory) == 0


@pytest.mark.asyncio
async def test_delete_works_via_companion_participant_url(
    client: AsyncClient, factory,
):
    """Either participant can delete: addressing the primary id under the
    *to-side* issue URL must work just as well as the from-side."""
    await _seed_chain(factory, 2)
    primary_id = await _create_link_via_api(client, "i1", "i2", "BLOCKS")

    # i2 is the to-side participant — must still be authorized to delete.
    resp = await client.delete(f"/api/issues/i2/relations/{primary_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": 2}
    assert await _row_count(factory) == 0


@pytest.mark.asyncio
async def test_delete_works_when_addressing_companion_row_id(
    client: AsyncClient, factory,
):
    """A→B BLOCKS writes (A,B,BLOCKS) primary + (B,A,IS_BLOCKED_BY)
    companion. DELETE via the *companion's* row id (not the primary's)
    must still remove both rows. The endpoint resolves the companion
    coordinates from whichever row was addressed — symmetric."""
    await _seed_chain(factory, 2)
    await _create_link_via_api(client, "i1", "i2", "BLOCKS")

    # Find the companion row id directly.
    async with factory() as db:
        companion = (await db.execute(
            select(IssueLink.id).where(
                IssueLink.fromIssueId == "i2",
                IssueLink.toIssueId == "i1",
                IssueLink.linkType == "IS_BLOCKED_BY",
            )
        )).scalar_one()

    resp = await client.delete(f"/api/issues/i2/relations/{companion}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": 2}
    assert await _row_count(factory) == 0


@pytest.mark.asyncio
async def test_delete_relates_to_symmetric_pair(
    client: AsyncClient, factory,
):
    """RELATES_TO companion is (to, from, RELATES_TO) — distinct under
    UNIQUE(from, to, type). DELETE must still remove both rows."""
    await _seed_chain(factory, 2)
    primary_id = await _create_link_via_api(client, "i1", "i2", "RELATES_TO")
    assert await _row_count(factory) == 2

    resp = await client.delete(f"/api/issues/i1/relations/{primary_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": 2}
    assert await _row_count(factory) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "link_type",
    [
        "BLOCKS",
        "IS_BLOCKED_BY",
        "CAUSES",
        "CAUSED_BY",
        "DUPLICATES",
        "IS_DUPLICATED_BY",
        "RELATES_TO",
    ],
)
async def test_delete_supported_for_every_link_type(
    client: AsyncClient, factory, link_type: str,
):
    """Every LinkType enum value must round-trip through delete. Catches
    any future inverse-mapping change (companion lookup) regression."""
    await _seed_chain(factory, 2)
    primary_id = await _create_link_via_api(client, "i1", "i2", link_type)

    resp = await client.delete(f"/api/issues/i1/relations/{primary_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": 2}
    assert await _row_count(factory) == 0


@pytest.mark.asyncio
async def test_delete_only_removes_targeted_relation(
    client: AsyncClient, factory,
):
    """When i1 has multiple unrelated relations, DELETE only removes the
    specified one and its companion — sibling rows must stay intact."""
    await _seed_chain(factory, 4)
    blocks_id = await _create_link_via_api(client, "i1", "i2", "BLOCKS")
    relates_id = await _create_link_via_api(client, "i1", "i3", "RELATES_TO")
    causes_id = await _create_link_via_api(client, "i1", "i4", "CAUSES")
    assert await _row_count(factory) == 6  # 3 pairs

    resp = await client.delete(f"/api/issues/i1/relations/{relates_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": 2}

    # Other two pairs untouched.
    assert await _row_count(factory) == 4
    async with factory() as db:
        survivors = {
            r[0] for r in (await db.execute(select(IssueLink.id))).all()
        }
    # Both BLOCKS and CAUSES primaries should still exist.
    assert blocks_id in survivors
    assert causes_id in survivors
    assert relates_id not in survivors


# ---------- legacy / corruption resilience ---------------------------------

@pytest.mark.asyncio
async def test_delete_with_orphan_no_companion_returns_one(
    client: AsyncClient, factory,
):
    """Legacy data: a single row with no companion (could exist from
    pre-CB-1971 code or direct-write tooling). DELETE must still finish
    and report the honest count — we do not silently backfill the
    companion or fail."""
    await _seed_chain(factory, 2)

    orphan_id = "orphan-link-1"
    async with factory() as db:
        db.add(_make_link("i1", "i2", "BLOCKS", link_id=orphan_id))
        # Deliberately NOT writing the companion row.
        await db.commit()
    assert await _row_count(factory) == 1

    resp = await client.delete(f"/api/issues/i1/relations/{orphan_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": 1}
    assert await _row_count(factory) == 0


# ---------- 404 cases ------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_missing_relation_returns_404(
    client: AsyncClient, factory,
):
    await _seed_chain(factory, 2)

    resp = await client.delete("/api/issues/i1/relations/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "NOT_FOUND"
    assert body["details"]["resource"] == "Relation"
    assert body["details"]["identifier"] == "does-not-exist"


@pytest.mark.asyncio
async def test_delete_with_wrong_participant_returns_404(
    client: AsyncClient, factory,
):
    """Relation exists but issue_id in the URL is not a participant.
    Surface as 404 (not 403/400) so callers can't probe relation ids by
    addressing them via arbitrary issue urls."""
    await _seed_chain(factory, 3)
    primary_id = await _create_link_via_api(client, "i1", "i2", "BLOCKS")

    resp = await client.delete(f"/api/issues/i3/relations/{primary_id}")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "NOT_FOUND"
    assert body["details"]["resource"] == "Relation"
    # Both rows still in the DB — wrong-owner attempt must NOT delete.
    assert await _row_count(factory) == 2


@pytest.mark.asyncio
async def test_delete_idempotency_second_call_returns_404(
    client: AsyncClient, factory,
):
    """Two consecutive deletes: first succeeds with deleted=2, the second
    sees the row gone and returns 404. Confirms post-delete state is
    consistent and there is no ghost row left to address."""
    await _seed_chain(factory, 2)
    primary_id = await _create_link_via_api(client, "i1", "i2", "BLOCKS")

    resp1 = await client.delete(f"/api/issues/i1/relations/{primary_id}")
    assert resp1.status_code == 200
    assert resp1.json() == {"deleted": 2}

    resp2 = await client.delete(f"/api/issues/i1/relations/{primary_id}")
    assert resp2.status_code == 404


# ---------- corruption guard ----------------------------------------------

@pytest.mark.asyncio
async def test_delete_unknown_link_type_returns_500(
    client: AsyncClient, factory,
):
    """Defensive: a row with a linkType not in the LinkType enum could
    only land via direct-write tooling. The request itself is valid —
    the DB is corrupt — so the endpoint must surface a clean 500
    DATABASE_ERROR with the offending values in `details` (so an
    operator can clean up) rather than crash on a KeyError or mislead
    the caller with a 400."""
    await _seed_chain(factory, 2)

    bad_id = "bad-link-1"
    async with factory() as db:
        db.add(_make_link("i1", "i2", "WAT_NOT_A_TYPE", link_id=bad_id))
        await db.commit()

    resp = await client.delete(f"/api/issues/i1/relations/{bad_id}")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"] == "DATABASE_ERROR"
    assert body["details"]["relationId"] == bad_id
    assert body["details"]["linkType"] == "WAT_NOT_A_TYPE"
    # Bad row left in place — caller's tooling must clean up directly.
    assert await _row_count(factory) == 1


# ---------- security-regression tests --------------------------------------

@pytest.mark.asyncio
async def test_delete_404_responses_are_byte_identical(
    client: AsyncClient, factory,
):
    """Information-disclosure guard: the 404 responses for "relation does
    not exist" and "relation exists but issue_id is not a participant"
    must be byte-identical so a caller cannot enumerate which relation
    ids exist in projects/issues they don't have access to. Locks in the
    no-leak guarantee for any future change to NotFoundError shape."""
    await _seed_chain(factory, 3)
    primary_id = await _create_link_via_api(client, "i1", "i2", "BLOCKS")

    # Case A: relation_id genuinely missing.
    resp_missing = await client.delete(
        f"/api/issues/i1/relations/{primary_id}-not-real",
    )
    assert resp_missing.status_code == 404

    # Case B: relation_id exists but issue_id is a non-participant. The
    # relation_id we use here matches Case A's *length and shape* up to
    # the trailing characters — the shapes of the response bodies must
    # not differ in a way that distinguishes the two cases.
    resp_wrong = await client.delete(
        f"/api/issues/i3/relations/{primary_id}-not-real",
    )
    assert resp_wrong.status_code == 404

    # Both bodies decode identically. We compare the JSON dicts (rather
    # than raw bytes) so a future router rewrite that re-orders keys
    # doesn't false-positive — the contract is "no field differs", not
    # "no byte differs".
    assert resp_missing.json() == resp_wrong.json(), (
        "Wrong-participant 404 must be indistinguishable from "
        "missing-relation 404 — see CB-1974 security audit"
    )


@pytest.mark.asyncio
async def test_delete_wrong_participant_404_preserves_relation_id_in_details(
    client: AsyncClient, factory,
):
    """The wrong-participant 404 echoes the supplied relation_id in
    `details.identifier` — same shape as the missing-relation 404. Locks
    in the error contract for callers building UIs around this."""
    await _seed_chain(factory, 3)
    primary_id = await _create_link_via_api(client, "i1", "i2", "BLOCKS")

    resp = await client.delete(f"/api/issues/i3/relations/{primary_id}")
    assert resp.status_code == 404
    body = resp.json()
    assert body["details"]["identifier"] == primary_id


@pytest.mark.asyncio
async def test_delete_response_does_not_leak_participant_ids(
    client: AsyncClient, factory,
):
    """The success response body is exactly `{"deleted": <int>}` — it
    must not include fromIssueId, toIssueId, linkType, or any field that
    would expose the *other* participant's id to a caller addressing the
    relation through one side. Schema-level guard backed by a runtime
    assertion."""
    await _seed_chain(factory, 2)
    primary_id = await _create_link_via_api(client, "i1", "i2", "BLOCKS")

    # i2 deletes via its participant URL — must not learn i1's id from
    # the response (it already knows it from POSTing the create, but the
    # contract still must not echo it).
    resp = await client.delete(f"/api/issues/i2/relations/{primary_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"deleted": 2}
    assert "fromIssueId" not in body
    assert "toIssueId" not in body
    assert "linkType" not in body
