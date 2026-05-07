"""CB-2050 regression probe — verifies embed_execution_summary writes to the
HTTP-mode chroma container (not the embedded SQLite fallback).

Usage:
    cd backend && python3 ../scripts/regression/2026-05-02-cb2050-embed-probe.py

Expects backend env to import (CHROMA_HOST/PORT must point at running container).
Writes one stable doc to project_test collection via the same code path AI
execution uses, then prints baseline + after counts so caller can diff.
"""
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from services.rag_service import RAGService  # noqa: E402


async def main():
    rag = RAGService()
    rag._init_client_blocking()
    print(f"mode={rag._mode} detail={rag._mode_detail}")
    assert rag._mode == "HTTP", f"expected HTTP mode, got {rag._mode}"

    project_id = "test"
    issue_key = "CB-2050"
    issue_id = "cb2050-regression-probe"

    col = rag.get_collection(project_id)
    before = col.count()
    print(f"project_test count BEFORE = {before}")

    fake = SimpleNamespace(
        summary="Regression probe for CB-2050: verify ExecutionSummary embed lands in chroma container volume, not the local SQLite fallback.",
        architectureNotes="Single-step probe; uses same RAGService.embed_execution_summary path as terminal_service.",
        technicalNotes="Bypasses Claude CLI subprocess to keep cost down; identical write surface.",
        componentsModified=None,
        filesTouched=None,
    )
    ok = await rag.embed_execution_summary(project_id, issue_id, issue_key, fake)
    print(f"embed_execution_summary -> {ok}")
    assert ok, "embed call returned False"

    after = col.count()
    print(f"project_test count AFTER  = {after}")
    print(f"delta = {after - before}")
    assert after > before, "collection count did not increase"
    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
