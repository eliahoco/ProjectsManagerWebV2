"""Regression tests for RAGService.search_execution_docs (CB-1595)."""

import pytest
from unittest.mock import MagicMock

from services.rag_service import RAGService


@pytest.fixture
def rag_service_with_collection():
    """RAGService whose get_collection returns a controllable mock."""
    rag = RAGService()
    mock_collection = MagicMock()
    rag.get_collection = MagicMock(return_value=mock_collection)
    return rag, mock_collection


@pytest.mark.asyncio
async def test_search_execution_docs_filters_by_content_type(
    rag_service_with_collection,
):
    rag, collection = rag_service_with_collection
    collection.query.return_value = {
        "ids": [["doc-id-1"]],
        "documents": [["[CB-1595] Implementation Summary:\nadded search method"]],
        "metadatas": [[{
            "issue_id": "issue-1",
            "key": "CB-1595",
            "content_type": "execution_summary",
        }]],
        "distances": [[0.25]],
    }

    results = await rag.search_execution_docs(
        project_id="proj-1", query="search method", n_results=3
    )

    collection.query.assert_called_once()
    call_kwargs = collection.query.call_args.kwargs
    assert call_kwargs["query_texts"] == ["search method"]
    assert call_kwargs["n_results"] == 3
    assert call_kwargs["where"] == {"content_type": "execution_summary"}
    assert "documents" in call_kwargs["include"]
    assert "metadatas" in call_kwargs["include"]
    assert "distances" in call_kwargs["include"]

    assert len(results) == 1
    hit = results[0]
    assert hit["issue_id"] == "issue-1"
    assert hit["key"] == "CB-1595"
    assert hit["content_type"] == "execution_summary"
    assert hit["distance"] == 0.25
    assert hit["score"] == pytest.approx(0.75)
    assert "search method" in hit["document"]


@pytest.mark.asyncio
async def test_search_execution_docs_empty_results(rag_service_with_collection):
    rag, collection = rag_service_with_collection
    collection.query.return_value = {
        "ids": [[]],
        "documents": [[]],
        "metadatas": [[]],
        "distances": [[]],
    }

    results = await rag.search_execution_docs(
        project_id="proj-1", query="nothing matches", n_results=5
    )

    assert results == []


@pytest.mark.asyncio
async def test_search_execution_docs_handles_chroma_failure(
    rag_service_with_collection,
):
    rag, collection = rag_service_with_collection
    collection.query.side_effect = RuntimeError("chroma exploded")

    results = await rag.search_execution_docs(
        project_id="proj-1", query="anything", n_results=5
    )

    assert results == []


@pytest.mark.asyncio
async def test_search_execution_docs_handles_missing_metadata_row(
    rag_service_with_collection,
):
    rag, collection = rag_service_with_collection
    collection.query.return_value = {
        "ids": [["doc-id-1"]],
        "documents": [["partial doc"]],
        "metadatas": [[None]],
        "distances": [[0.5]],
    }

    results = await rag.search_execution_docs(
        project_id="proj-1", query="x", n_results=1
    )

    assert len(results) == 1
    assert results[0]["issue_id"] is None
    assert results[0]["key"] is None
    assert results[0]["content_type"] is None
    assert results[0]["distance"] == 0.5
    assert results[0]["score"] == pytest.approx(0.5)
