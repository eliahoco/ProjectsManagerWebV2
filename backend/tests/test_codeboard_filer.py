"""Unit tests for CodeBoardFiler — CB-2914 E7."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.codeboard_filer import (
    CodeBoardFiler,
    PlanNode,
    _clean,
)


def _node(title, type_, *, children=None, priority="MEDIUM"):
    return PlanNode(title=title, type=type_, priority=priority,
                    description=f"desc for {title}", labels="sie-test",
                    children=children or [])


@pytest.mark.asyncio
class TestCodeBoardFiler:
    async def test_top_down_walk_creates_all_nodes(self):
        plan = _node("F", "FEATURE", children=[
            _node("E1", "EPIC", children=[
                _node("S1.1", "STORY", children=[
                    _node("T1.1.1", "TASK"),
                ]),
            ]),
            _node("E2", "EPIC"),
        ])

        created_ids = iter(["uuid-F", "uuid-E1", "uuid-E2", "uuid-S1.1", "uuid-T1.1.1"])
        created_keys = iter(["CB-100", "CB-101", "CB-102", "CB-103", "CB-104"])
        seen_parents: list[str | None] = []

        async def fake_post(self, project_id, node, parent_id, batch_id):
            seen_parents.append(parent_id)
            return {"id": next(created_ids), "key": next(created_keys)}

        with patch.object(CodeBoardFiler, "_snapshot_existing_titles", new=AsyncMock(return_value=set())), \
             patch.object(CodeBoardFiler, "_post_issue", new=fake_post):
            filer = CodeBoardFiler()
            report = await filer.file_plan("project-A", plan)

        # BFS order: F → E1 → E2 → S1.1 → T1.1.1
        assert [r["title"] for r in report.created] == ["F", "E1", "E2", "S1.1", "T1.1.1"]
        assert seen_parents == [None, "uuid-F", "uuid-F", "uuid-E1", "uuid-S1.1"]
        assert report.skipped == []
        assert report.errors == []

    async def test_duplicate_titles_skipped(self):
        plan = _node("F", "FEATURE", children=[
            _node("E1", "EPIC"),
        ])

        async def fake_post(self, project_id, node, parent_id, batch_id):
            return {"id": f"id-{node.title}", "key": f"CB-{node.title}"}

        # Pre-seed an existing root with same title.
        existing = {(None, "f")}

        with patch.object(CodeBoardFiler, "_post_issue", new=fake_post):
            filer = CodeBoardFiler()
            report = await filer.file_plan(
                "project-A", plan, existing_titles=existing,
            )

        # Root skipped → no parent_id for children → children skipped too.
        assert report.skipped[0]["title"] == "F"
        assert report.created == []

    async def test_per_node_error_does_not_abort_run(self):
        plan = _node("F", "FEATURE", children=[
            _node("E1", "EPIC"),
            _node("E2", "EPIC"),
        ])

        async def fake_post(self, project_id, node, parent_id, batch_id):
            if node.title == "E1":
                raise RuntimeError("HTTP 500: boom")
            return {"id": f"id-{node.title}", "key": f"CB-{node.title}"}

        with patch.object(CodeBoardFiler, "_snapshot_existing_titles", new=AsyncMock(return_value=set())), \
             patch.object(CodeBoardFiler, "_post_issue", new=fake_post):
            filer = CodeBoardFiler()
            report = await filer.file_plan("project-A", plan)

        # F + E2 created, E1 errored, run did NOT abort.
        assert [r["title"] for r in report.created] == ["F", "E2"]
        assert report.errors[0]["title"] == "E1"

    async def test_invalid_type_rejected(self):
        bad = PlanNode(title="weird", type="HAT", priority="MEDIUM")
        with patch.object(CodeBoardFiler, "_snapshot_existing_titles", new=AsyncMock(return_value=set())):
            filer = CodeBoardFiler()
            with pytest.raises(ValueError):
                await filer.file_plan("project-A", bad)


class TestCleanRedaction:
    """sec-audit MED-1: filer uses canonical `redact_secrets` (utils/exhaustion_detector)
    instead of its own subset. Replacement marker is `***REDACTED***`."""

    def test_clean_strips_bearer(self):
        out = _clean("token: Bearer abc.def.ghi")
        assert "Bearer" in out
        assert "abc.def.ghi" not in out
        assert "REDACTED" in out

    def test_clean_strips_password(self):
        out = _clean("password=hunter2 in title")
        assert "hunter2" not in out
        assert "REDACTED" in out

    def test_clean_strips_authorization_basic(self):
        out = _clean("Authorization: Basic dXNlcjpwYXNz")
        assert "dXNlcjpwYXNz" not in out
        assert "REDACTED" in out

    def test_clean_empty(self):
        assert _clean("") == ""
        assert _clean(None) == ""
