"""
CB-1978 — focused cycle-detection tests for the relations API.

This module is a sibling of `test_relations_post.py` that drills specifically
into the cycle-detection helper (`api.relations._has_cycle`) and the
transitive-vs-symmetric contract that decides which link types run the cycle
check at all.

Coverage matrix:

  Helper (unit, no HTTP)
    * `_has_cycle` returns None on disjoint subgraphs.
    * `_has_cycle` returns the closed canonical cycle for length-2/3 cycles.
    * `_has_cycle` BFS is family-scoped — a CAUSES chain cannot pollute a
      BLOCKS-family check.
    * `_has_cycle` BFS is project-scoped — a cross-project edge in the same
      family is invisible.
    * `_canonical_edge` flips the direction for IS_BLOCKED_BY / CAUSED_BY
      (companion-stored families) and preserves it for BLOCKS / CAUSES.

  Endpoint (HTTP)
    * Self-link (A→A) is rejected on every link type, transitive or not.
    * A→B→C cycle for every transitive family separately:
        - BLOCKS, IS_BLOCKED_BY (BLOCKS family)
        - CAUSES, CAUSED_BY (CAUSES family)
    * Same DB state ((from, to) pair already covered by an A→B BLOCKS edge):
        - re-posting the inverse direction as BLOCKS → 409 CYCLE_DETECTED
        - re-posting as RELATES_TO → 201 (symmetric, skips cycle check)
        - re-posting as DUPLICATES → 201 (non-transitive, skips cycle check)
        - re-posting as IS_DUPLICATED_BY → 201 (non-transitive, skips cycle
          check) — IS_DUPLICATED_BY isn't in `_TRANSITIVE_FAMILIES` so the
          create endpoint never even calls `_has_cycle`.

The transitive-vs-symmetric comparison is the load-bearing addition over
`test_relations_post.py`: it pins down that the *only* difference between a
cycling and non-cycling POST in the same DB state is whether the requested
link type lives in `_TRANSITIVE_FAMILIES`.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
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


from api.relations import (  # noqa: E402
    _TRANSITIVE_FAMILIES,
    _canonical_edge,
    _has_cycle,
)
from api.relations import router as relations_router  # noqa: E402
from app.errors import setup_exception_handlers  # noqa: E402
from models.database import Base, get_db  # noqa: E402
from models.issue import Issue, IssueLink, Project  # noqa: E402


# ---------- fixtures -------------------------------------------------------


@pytest_asyncio.fixture
async def test_app_and_db():
    """On-disk SQLite mirrors the test_relations_post.py fixture pattern.

    Per-test temp dir keeps the tests isolated and means a stray failure
    can't pollute the next run via a shared file.
    """
    tmp_dir = tempfile.mkdtemp(prefix="relations-cycle-test-")
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


async def _seed_issues(factory, ids_keys: list[tuple[str, str]],
                       project_id: str = "proj-1") -> None:
    """Seed a project + the requested (id, key) issues in one transaction."""
    async with factory() as db:
        # The fixture creates a fresh DB per test, so the project does not
        # exist yet — add it before the issues.
        db.add(_make_project(project_id))
        await db.flush()
        for issue_id, key in ids_keys:
            db.add(_make_issue(issue_id, key, project_id=project_id))
        await db.commit()


# ---------- _canonical_edge unit tests -------------------------------------


def test_canonical_edge_preserves_direction_for_blocks_and_causes():
    """BLOCKS / CAUSES are stored canonically, so the edge stays from→to."""
    assert _canonical_edge("a", "b", "BLOCKS") == ("a", "b", "BLOCKS")
    assert _canonical_edge("a", "b", "CAUSES") == ("a", "b", "CAUSES")


def test_canonical_edge_flips_direction_for_inverse_types():
    """IS_BLOCKED_BY / CAUSED_BY ride the *companion* row, so the edge
    that lands in the canonical-family graph is the flipped (to → from)."""
    assert _canonical_edge("a", "b", "IS_BLOCKED_BY") == ("b", "a", "BLOCKS")
    assert _canonical_edge("a", "b", "CAUSED_BY") == ("b", "a", "CAUSES")


# ---------- _has_cycle unit tests ------------------------------------------


@pytest.mark.asyncio
async def test_has_cycle_returns_none_on_empty_graph(factory):
    """No rows in the family graph → no cycle, helper returns None."""
    await _seed_issues(factory, [("i1", "CB-1"), ("i2", "CB-2")])
    async with factory() as db:
        result = await _has_cycle(db, "i1", "i2", "BLOCKS", "proj-1")
    assert result is None


@pytest.mark.asyncio
async def test_has_cycle_returns_none_when_target_unreachable(factory):
    """Disjoint subgraph: i1 BLOCKS i2 in the DB, then check i3→i4 — the
    BFS from i4 cannot reach i3, so the helper must return None."""
    await _seed_issues(
        factory,
        [("i1", "CB-1"), ("i2", "CB-2"), ("i3", "CB-3"), ("i4", "CB-4")],
    )
    async with factory() as db:
        # Direct write — we deliberately bypass the endpoint to keep the
        # unit test focused on the helper's BFS, not the endpoint pipeline.
        db.add(IssueLink(
            id="link-1", fromIssueId="i1", toIssueId="i2", linkType="BLOCKS",
        ))
        await db.commit()

        result = await _has_cycle(db, "i3", "i4", "BLOCKS", "proj-1")
    assert result is None


@pytest.mark.asyncio
async def test_has_cycle_detects_two_cycle(factory):
    """Length-2: i1→i2 in the BLOCKS graph; would-be i2→i1 closes a 2-cycle.
    Helper must return the closed canonical path [i2, i1, i2]."""
    await _seed_issues(factory, [("i1", "CB-1"), ("i2", "CB-2")])
    async with factory() as db:
        db.add(IssueLink(
            id="link-1", fromIssueId="i1", toIssueId="i2", linkType="BLOCKS",
        ))
        await db.commit()

        result = await _has_cycle(db, "i2", "i1", "BLOCKS", "proj-1")
    assert result == ["i2", "i1", "i2"]


@pytest.mark.asyncio
async def test_has_cycle_detects_three_cycle(factory):
    """Length-3: i1→i2→i3 chain; would-be i3→i1 closes a 3-cycle.
    Helper must return the closed cycle [i3, i1, i2, i3].

    Pins the LIFO traversal order matching `test_relations_post.py`'s
    existing 3-cycle assertions — `_has_cycle`'s docstring notes both
    FIFO and LIFO are valid, so if the helper's traversal ever flips the
    sibling tests in test_relations_post.py and this assertion update
    together.
    """
    await _seed_issues(
        factory, [("i1", "CB-1"), ("i2", "CB-2"), ("i3", "CB-3")],
    )
    async with factory() as db:
        db.add(IssueLink(
            id="l1", fromIssueId="i1", toIssueId="i2", linkType="BLOCKS",
        ))
        db.add(IssueLink(
            id="l2", fromIssueId="i2", toIssueId="i3", linkType="BLOCKS",
        ))
        await db.commit()

        result = await _has_cycle(db, "i3", "i1", "BLOCKS", "proj-1")
    # Closed canonical cycle: src=i3, dst=i1, path back i1→i2→i3.
    assert result == ["i3", "i1", "i2", "i3"]


@pytest.mark.asyncio
async def test_has_cycle_is_family_scoped(factory):
    """A CAUSES chain in the DB must NOT close a BLOCKS-family cycle.

    Plants i1→i2 in CAUSES, then asks the helper whether adding i2→i1 in
    the BLOCKS family would cycle. Without family scoping the BFS would
    walk the CAUSES edge and falsely report a cycle.
    """
    await _seed_issues(factory, [("i1", "CB-1"), ("i2", "CB-2")])
    async with factory() as db:
        db.add(IssueLink(
            id="l1", fromIssueId="i1", toIssueId="i2", linkType="CAUSES",
        ))
        await db.commit()

        result = await _has_cycle(db, "i2", "i1", "BLOCKS", "proj-1")
    assert result is None


@pytest.mark.asyncio
async def test_has_cycle_skips_cross_project_edges(factory):
    """A BLOCKS row connecting issues in *different* projects must be
    invisible to the BFS — defense in depth against legacy data leaking
    cross-project IDs into the response path (CB-1977 audit fix).

    Setup: proj-1 has i1, i2; proj-2 has i3. Direct-write a cross-project
    BLOCKS row i2→i3 (the create path normally rejects this). The BFS for
    a proj-1 cycle check must not traverse i2→i3.
    """
    async with factory() as db:
        db.add(_make_project("proj-1"))
        db.add(_make_project("proj-2"))
        await db.flush()
        db.add(_make_issue("i1", "CB-1", project_id="proj-1"))
        db.add(_make_issue("i2", "CB-2", project_id="proj-1"))
        db.add(_make_issue("i3", "CB-3", project_id="proj-2"))
        await db.flush()
        # Cross-project BLOCKS row that the endpoint would never write.
        db.add(IssueLink(
            id="cross", fromIssueId="i2", toIssueId="i3", linkType="BLOCKS",
        ))
        # In-project i1→i2 BLOCKS so the BFS has somewhere legitimate to walk.
        db.add(IssueLink(
            id="in-proj", fromIssueId="i1", toIssueId="i2",
            linkType="BLOCKS",
        ))
        await db.commit()

        # Asking "would i3→i1 cycle in BLOCKS, project=proj-1?" — i3 is
        # in proj-2 so the BFS root has no proj-1 outgoing edges; helper
        # returns None despite the existing i2→i3 row in the table.
        result = await _has_cycle(db, "i3", "i1", "BLOCKS", "proj-1")
    assert result is None


# ---------- A→A self-link (rule-23 spec scenario) --------------------------


@pytest.mark.parametrize(
    "link_type",
    [
        "BLOCKS", "IS_BLOCKED_BY",
        "CAUSES", "CAUSED_BY",
        "RELATES_TO",
        "DUPLICATES", "IS_DUPLICATED_BY",
    ],
)
@pytest.mark.asyncio
async def test_self_link_rejected_for_every_link_type(
    client: AsyncClient, factory, link_type: str,
):
    """A→A is a self-link, rejected with 400 VALIDATION_ERROR before the
    cycle check runs. Parametrized across every LinkType to confirm the
    self-link guard fires regardless of family — there is no link type
    where linking an issue to itself is meaningful.
    """
    await _seed_issues(factory, [("i1", "CB-1")])

    resp = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i1", "linkType": link_type},
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "itself" in body["message"].lower()

    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    assert rows == []


# ---------- A→B→C cycles per transitive family -----------------------------


@pytest.mark.asyncio
async def test_caused_by_three_cycle_rejected(client: AsyncClient, factory):
    """CAUSED_BY chain closing a 3-cycle in the CAUSES family.

    `i1 CAUSED_BY i2` writes canonical edge i2→i1; `i2 CAUSED_BY i3`
    writes i3→i2. Adding `i3 CAUSED_BY i1` would write i1→i3 and close
    the 3-cycle i1→i3→i2→i1.

    `test_relations_post.py` covers CAUSES the canonical direction; this
    test pins the inverse-companion direction so both halves of the
    CAUSES family are exercised by the suite.
    """
    await _seed_issues(
        factory, [("i1", "CB-1"), ("i2", "CB-2"), ("i3", "CB-3")],
    )

    r1 = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "CAUSED_BY"},
    )
    assert r1.status_code == 201, r1.text
    r2 = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i3", "linkType": "CAUSED_BY"},
    )
    assert r2.status_code == 201, r2.text

    cyc = await client.post(
        "/api/issues/i3/relations",
        json={"toIssueId": "i1", "linkType": "CAUSED_BY"},
    )
    assert cyc.status_code == 409
    body = cyc.json()
    assert body["code"] == "CYCLE_DETECTED"
    # Canonical edge for "i3 CAUSED_BY i1" flips to i1→i3 in the CAUSES
    # family. Existing canonical edges are i2→i1 and i3→i2.
    assert body["details"]["path"] == ["i1", "i3", "i2", "i1"]


# ---------- A→B same DB state, transitive vs symmetric --------------------


@pytest.mark.asyncio
async def test_blocks_then_blocks_inverse_rejects_as_cycle(
    client: AsyncClient, factory,
):
    """Baseline for the symmetric-bypass tests below:
    A BLOCKS B then B BLOCKS A → 409 CYCLE_DETECTED. Same DB state used
    by the four sibling tests, the only changing variable is the second
    POST's linkType.
    """
    await _seed_issues(factory, [("i1", "CB-1"), ("i2", "CB-2")])

    first = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i1", "linkType": "BLOCKS"},
    )
    assert second.status_code == 409
    body = second.json()
    assert body["code"] == "CYCLE_DETECTED"
    assert body["details"]["path"] == ["i2", "i1", "i2"]


@pytest.mark.asyncio
async def test_blocks_then_relates_to_inverse_succeeds(
    client: AsyncClient, factory,
):
    """A BLOCKS B then B RELATES_TO A → 201.

    RELATES_TO is symmetric and non-transitive — it lives outside
    `_TRANSITIVE_FAMILIES`, so the create endpoint never invokes
    `_has_cycle`. The presence of the BLOCKS edge i1→i2 in the DB is
    irrelevant to the RELATES_TO insert.
    """
    await _seed_issues(factory, [("i1", "CB-1"), ("i2", "CB-2")])

    first = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert first.status_code == 201, first.text

    # Same (from, to) pair as the cycle case above, only the type changes.
    second = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i1", "linkType": "RELATES_TO"},
    )
    assert second.status_code == 201, second.text

    # Confirm both edges coexist: the original BLOCKS pair plus the
    # symmetric RELATES_TO pair (RELATES_TO is its own inverse, so the
    # companion is (i1, i2, RELATES_TO)).
    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    pairs = sorted((r.fromIssueId, r.toIssueId, r.linkType) for r in rows)
    assert pairs == [
        ("i1", "i2", "BLOCKS"),
        ("i1", "i2", "RELATES_TO"),
        ("i2", "i1", "IS_BLOCKED_BY"),
        ("i2", "i1", "RELATES_TO"),
    ]


@pytest.mark.asyncio
async def test_blocks_then_duplicates_inverse_succeeds(
    client: AsyncClient, factory,
):
    """A BLOCKS B then B DUPLICATES A → 201.

    DUPLICATES isn't in `_TRANSITIVE_FAMILIES`, so the cycle-check branch
    is skipped even though the BLOCKS edge i1→i2 sits in the DB.
    """
    await _seed_issues(factory, [("i1", "CB-1"), ("i2", "CB-2")])

    first = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i1", "linkType": "DUPLICATES"},
    )
    assert second.status_code == 201, second.text

    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    pairs = sorted((r.fromIssueId, r.toIssueId, r.linkType) for r in rows)
    assert pairs == [
        ("i1", "i2", "BLOCKS"),
        ("i1", "i2", "IS_DUPLICATED_BY"),
        ("i2", "i1", "DUPLICATES"),
        ("i2", "i1", "IS_BLOCKED_BY"),
    ]


@pytest.mark.asyncio
async def test_blocks_then_is_duplicated_by_inverse_succeeds(
    client: AsyncClient, factory,
):
    """A BLOCKS B then B IS_DUPLICATED_BY A → 201.

    IS_DUPLICATED_BY is the inverse companion of DUPLICATES — also outside
    `_TRANSITIVE_FAMILIES`, so it skips the cycle check.
    """
    await _seed_issues(factory, [("i1", "CB-1"), ("i2", "CB-2")])

    first = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i1", "linkType": "IS_DUPLICATED_BY"},
    )
    assert second.status_code == 201, second.text

    # Mirror sibling tests above: assert the final pair set so a
    # regression that drops the companion or writes the wrong inverse
    # surfaces here, not in a downstream consumer.
    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    pairs = sorted((r.fromIssueId, r.toIssueId, r.linkType) for r in rows)
    assert pairs == [
        ("i1", "i2", "BLOCKS"),
        ("i1", "i2", "DUPLICATES"),
        ("i2", "i1", "IS_BLOCKED_BY"),
        ("i2", "i1", "IS_DUPLICATED_BY"),
    ]


# ---------- DUPLICATES family transitive-chain skip ------------------------


@pytest.mark.asyncio
async def test_duplicates_three_chain_does_not_cycle(
    client: AsyncClient, factory,
):
    """DUPLICATES is non-transitive — A DUP B, B DUP C, C DUP A all 201.

    The third post would be a cycle in a transitive family but DUPLICATES
    skips the cycle check. Mirror of `test_relates_to_skips_cycle_check`
    in test_relations_post.py for the second non-transitive type so both
    skip-paths are exercised end-to-end.
    """
    await _seed_issues(
        factory, [("i1", "CB-1"), ("i2", "CB-2"), ("i3", "CB-3")],
    )

    for src, dst in (("i1", "i2"), ("i2", "i3"), ("i3", "i1")):
        r = await client.post(
            f"/api/issues/{src}/relations",
            json={"toIssueId": dst, "linkType": "DUPLICATES"},
        )
        assert r.status_code == 201, r.text

    # 3 user-facing inserts × (primary + companion) = 6 rows. Asserting
    # the full pair set catches any regression that silently drops one
    # leg of the pair when DUPLICATES is in play.
    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    pairs = sorted((r.fromIssueId, r.toIssueId, r.linkType) for r in rows)
    assert pairs == [
        ("i1", "i2", "DUPLICATES"),
        ("i1", "i3", "IS_DUPLICATED_BY"),
        ("i2", "i1", "IS_DUPLICATED_BY"),
        ("i2", "i3", "DUPLICATES"),
        ("i3", "i1", "DUPLICATES"),
        ("i3", "i2", "IS_DUPLICATED_BY"),
    ]


# ---------- _TRANSITIVE_FAMILIES contract ----------------------------------


def test_only_blocks_and_causes_families_run_cycle_check():
    """Lock down which link types trigger the cycle BFS.

    `_TRANSITIVE_FAMILIES` is the single source of truth the create endpoint
    consults to decide whether to call `_has_cycle`. RELATES_TO, DUPLICATES,
    and IS_DUPLICATED_BY MUST be absent — that absence is exactly what the
    "skip cycle check" tests above rely on. If a future change moves one of
    these into the dict, this assertion fires and the test author is forced
    to revisit the symmetric-bypass contract.
    """
    assert set(_TRANSITIVE_FAMILIES) == {
        "BLOCKS", "IS_BLOCKED_BY",
        "CAUSES", "CAUSED_BY",
    }
    # Per-key family mapping pins the canonical-family routing too.
    assert _TRANSITIVE_FAMILIES["BLOCKS"] == "BLOCKS"
    assert _TRANSITIVE_FAMILIES["IS_BLOCKED_BY"] == "BLOCKS"
    assert _TRANSITIVE_FAMILIES["CAUSES"] == "CAUSES"
    assert _TRANSITIVE_FAMILIES["CAUSED_BY"] == "CAUSES"
