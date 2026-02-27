"""
Services for ProjectsManagerWebV2 Backend
"""

from services.rag_service import rag_service, RAGService
from services.ai_service import ai_service, AIService
from services.ai_engine import ai_engine, AIEngine
from services.git_service import (
    git_service,
    GitService,
    COMMIT_PATTERNS,
    get_status_from_commit,
)
from services.qa_service import qa_service, QAService
from services.dependency_analyzer import dependency_analyzer, DependencyAnalyzer
from services.autopilot_service import autopilot_service, AutoPilotService

__all__ = [
    'rag_service', 'RAGService',
    'ai_service', 'AIService',
    'ai_engine', 'AIEngine',
    'git_service', 'GitService',
    'COMMIT_PATTERNS', 'get_status_from_commit',
    'qa_service', 'QAService',
    'dependency_analyzer', 'DependencyAnalyzer',
    'autopilot_service', 'AutoPilotService',
]
