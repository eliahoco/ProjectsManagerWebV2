"""
Pipeline Executor Service - Orchestrates multi-stage AI execution pipelines.

Execution flow:
  1. IMPLEMENT -> Claude Code implements the task
  2. VERIFY    -> Chrome MCP checks the UI
  3. If VERIFY fails -> FIX -> RE_VERIFY (up to max_retries)

Design:
  - Composes terminal_service internally (does not replace it)
  - Each stage creates its own terminal session
  - Verification stage calls Chrome MCP tools (stubbed until CB-1243)
  - Fix stage includes verification error context in its prompt
  - All state persisted to database via PipelineExecution + PipelineStage models
"""

import asyncio
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums (canonical definitions -- mirrored in models/pipeline.py)
# We define them here so the executor can function even before the
# SQLAlchemy models land.  The model file should import these or
# define compatible values.
# ---------------------------------------------------------------------------

class PipelineStatus(str, Enum):
    """Top-level pipeline execution status."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StageType(str, Enum):
    """Types of pipeline stages."""
    IMPLEMENT = "IMPLEMENT"
    VERIFY = "VERIFY"
    FIX = "FIX"
    RE_VERIFY = "RE_VERIFY"


class StageStatus(str, Enum):
    """Status of an individual stage."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_MAX_FIX_RETRIES = 3
DEFAULT_VERIFY_TIMEOUT_SECONDS = 120
DEFAULT_IMPLEMENT_TIMEOUT_SECONDS = 1800  # 30 min (matches terminal_service)


# ---------------------------------------------------------------------------
# Verification result dataclass (returned by the verify stage)
# ---------------------------------------------------------------------------

class VerificationResult:
    """Result from a verification stage (Chrome MCP or stub)."""

    def __init__(
        self,
        passed: bool,
        evidence: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        screenshots: Optional[List[str]] = None,
    ):
        self.passed = passed
        self.evidence = evidence or {}
        self.error_message = error_message
        self.screenshots = screenshots or []

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "evidence": self.evidence,
            "error_message": self.error_message,
            "screenshots": self.screenshots,
        }


# ---------------------------------------------------------------------------
# Pipeline Executor
# ---------------------------------------------------------------------------

class PipelineExecutor:
    """Orchestrates multi-stage AI execution pipelines.

    Usage:
        execution = await pipeline_executor.start_pipeline(db, issue_id, project_id, project_path)
        # ... later, when a stage finishes ...
        execution = await pipeline_executor.advance_pipeline(db, execution_id)
    """

    def __init__(self):
        # In-memory tracking of running pipelines for fast lookup
        self._running: Dict[str, asyncio.Task] = {}  # execution_id -> asyncio.Task
        self._cancelled: set = set()  # execution IDs that have been cancelled

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_pipeline(
        self,
        db: AsyncSession,
        issue_id: str,
        project_id: str,
        project_path: str,
        agent_id: Optional[str] = None,
        max_retries: int = DEFAULT_MAX_FIX_RETRIES,
    ) -> Any:
        """Create a new pipeline execution with stages and kick off IMPLEMENT.

        Returns the PipelineExecution ORM object (or a dict if models are
        not yet available).
        """
        PipelineExecution, PipelineStage, PipelineConfig = _import_models()

        execution_id = str(uuid.uuid4())
        now = datetime.utcnow()

        # 1. Create PipelineExecution record
        execution = PipelineExecution(
            id=execution_id,
            issueId=issue_id,
            projectId=project_id,
            projectPath=project_path,
            agentId=agent_id,
            status=PipelineStatus.RUNNING.value,
            currentStageIndex=0,
            maxRetries=max_retries,
            retryCount=0,
            startedAt=now,
        )
        db.add(execution)

        # 2. Create initial stages: IMPLEMENT, VERIFY
        implement_stage = PipelineStage(
            id=str(uuid.uuid4()),
            executionId=execution_id,
            stageType=StageType.IMPLEMENT.value,
            stageIndex=0,
            status=StageStatus.PENDING.value,
        )
        db.add(implement_stage)

        verify_stage = PipelineStage(
            id=str(uuid.uuid4()),
            executionId=execution_id,
            stageType=StageType.VERIFY.value,
            stageIndex=1,
            status=StageStatus.PENDING.value,
        )
        db.add(verify_stage)

        await db.flush()  # assign IDs, keep in transaction

        logger.info(
            "Pipeline %s created for issue %s (stages: IMPLEMENT, VERIFY)",
            execution_id,
            issue_id,
        )

        # 3. Start the pipeline orchestration loop as a background task
        task = asyncio.create_task(
            self._run_pipeline(db, execution_id, issue_id, project_id, project_path, agent_id)
        )
        self._running[execution_id] = task

        await db.commit()

        return execution

    async def advance_pipeline(
        self,
        db: AsyncSession,
        execution_id: str,
    ) -> Any:
        """Advance the pipeline to its next stage.

        Called internally after each stage completes.  Can also be called
        externally to manually nudge a pipeline forward (e.g. after a
        manual verification).

        Returns the updated PipelineExecution.
        """
        PipelineExecution, PipelineStage, _ = _import_models()

        execution = await self._get_execution(db, execution_id)
        if not execution:
            raise ValueError(f"Pipeline execution {execution_id} not found")

        if execution.status != PipelineStatus.RUNNING.value:
            logger.warning(
                "advance_pipeline called on non-running pipeline %s (status=%s)",
                execution_id,
                execution.status,
            )
            return execution

        # Find the current stage
        current_stage = await self._get_stage_at_index(
            db, execution_id, execution.currentStageIndex
        )
        if not current_stage:
            logger.error("No stage found at index %d for pipeline %s", execution.currentStageIndex, execution_id)
            execution.status = PipelineStatus.FAILED.value
            execution.error = "Internal error: missing stage record"
            execution.completedAt = datetime.utcnow()
            await db.commit()
            return execution

        stage_type = current_stage.stageType
        stage_status = current_stage.status

        # ---- Decision tree based on what just finished ----

        if stage_type == StageType.IMPLEMENT.value:
            if stage_status == StageStatus.COMPLETED.value:
                # Move to VERIFY
                return await self._activate_next_stage(db, execution)
            else:
                # IMPLEMENT failed -- pipeline fails
                execution.status = PipelineStatus.FAILED.value
                execution.error = current_stage.error or "Implementation stage failed"
                execution.completedAt = datetime.utcnow()
                await db.commit()
                return execution

        elif stage_type in (StageType.VERIFY.value, StageType.RE_VERIFY.value):
            if stage_status == StageStatus.COMPLETED.value:
                # Check if verification passed (stored in stage result JSON)
                passed = self._stage_result_passed(current_stage)
                if passed:
                    # Pipeline success
                    execution.status = PipelineStatus.COMPLETED.value
                    execution.completedAt = datetime.utcnow()
                    logger.info("Pipeline %s COMPLETED (verification passed)", execution_id)
                    await db.commit()
                    return execution
                else:
                    # Verification failed -- check retry budget
                    if execution.retryCount < execution.maxRetries:
                        execution.retryCount += 1
                        # Create FIX + RE_VERIFY stages
                        next_index = execution.currentStageIndex + 1

                        fix_stage = PipelineStage(
                            id=str(uuid.uuid4()),
                            executionId=execution_id,
                            stageType=StageType.FIX.value,
                            stageIndex=next_index,
                            status=StageStatus.PENDING.value,
                            inputData=current_stage.resultData,  # pass verification error to fix
                        )
                        db.add(fix_stage)

                        reverify_stage = PipelineStage(
                            id=str(uuid.uuid4()),
                            executionId=execution_id,
                            stageType=StageType.RE_VERIFY.value,
                            stageIndex=next_index + 1,
                            status=StageStatus.PENDING.value,
                        )
                        db.add(reverify_stage)

                        await db.flush()
                        logger.info(
                            "Pipeline %s: verification failed, starting FIX retry %d/%d",
                            execution_id,
                            execution.retryCount,
                            execution.maxRetries,
                        )
                        return await self._activate_next_stage(db, execution)
                    else:
                        # Exhausted retries
                        execution.status = PipelineStatus.FAILED.value
                        execution.error = (
                            f"Verification failed after {execution.maxRetries} fix attempts"
                        )
                        execution.completedAt = datetime.utcnow()
                        logger.warning("Pipeline %s FAILED (retries exhausted)", execution_id)
                        await db.commit()
                        return execution
            else:
                # Verification stage itself errored (not a "fail" result)
                execution.status = PipelineStatus.FAILED.value
                execution.error = current_stage.error or "Verification stage error"
                execution.completedAt = datetime.utcnow()
                await db.commit()
                return execution

        elif stage_type == StageType.FIX.value:
            if stage_status == StageStatus.COMPLETED.value:
                # Move to RE_VERIFY
                return await self._activate_next_stage(db, execution)
            else:
                # Fix stage failed
                execution.status = PipelineStatus.FAILED.value
                execution.error = current_stage.error or "Fix stage failed"
                execution.completedAt = datetime.utcnow()
                await db.commit()
                return execution

        # Fallback -- shouldn't happen
        logger.error("Unhandled stage type %s in pipeline %s", stage_type, execution_id)
        execution.status = PipelineStatus.FAILED.value
        execution.error = f"Unhandled stage type: {stage_type}"
        execution.completedAt = datetime.utcnow()
        await db.commit()
        return execution

    async def execute_implement_stage(
        self,
        db: AsyncSession,
        stage: Any,
        issue: Any,
        project_path: str,
        agent_id: Optional[str] = None,
    ) -> None:
        """Run the implementation stage using terminal_service.

        Starts a Claude Code CLI session that implements the issue.
        Updates the stage record with session ID and result on completion.
        """
        from services.terminal_service import terminal_service, ExecutionProvider
        from services.context_builder import build_execution_context, get_parent_chain

        stage.status = StageStatus.RUNNING.value
        stage.startedAt = datetime.utcnow()
        await db.commit()

        try:
            # Build rich execution context
            rich_prompt = await build_execution_context(
                db=db,
                issue_id=issue.id,
                issue_key=issue.key,
                issue_title=issue.title,
                issue_type=issue.type,
                issue_description=issue.description or "",
            )

            # Resolve feature ID for cache preservation
            parent_chain = await get_parent_chain(db, issue.id)
            feature_id = None
            for ancestor in parent_chain:
                if ancestor["type"] == "FEATURE":
                    feature_id = ancestor["id"]
                    break

            # Start execution via terminal_service
            session = await terminal_service.start_execution(
                issue_id=issue.id,
                issue_key=issue.key,
                issue_title=issue.title,
                issue_description=issue.description or "",
                issue_type=issue.type,
                provider=ExecutionProvider.CLAUDE_CODE,
                project_path=project_path,
                project_id=issue.projectId,
                prompt_override=rich_prompt,
                feature_id=feature_id,
            )

            # Store session ID on the stage
            stage.sessionId = session.id
            await db.commit()

            # Wait for the session to finish (poll)
            result_status = await self._wait_for_session(session.id)

            if result_status == "completed":
                stage.status = StageStatus.COMPLETED.value
                stage.resultData = _json_dumps({
                    "session_id": session.id,
                    "exit_code": session.exit_code,
                    "output_lines": len(session.output),
                    "files_written": session.files_written,
                })
            else:
                stage.status = StageStatus.FAILED.value
                stage.error = session.error or f"Session ended with status: {result_status}"
                stage.resultData = _json_dumps({
                    "session_id": session.id,
                    "exit_code": session.exit_code,
                })

        except Exception as exc:
            logger.exception("IMPLEMENT stage error for pipeline stage %s", stage.id)
            stage.status = StageStatus.FAILED.value
            stage.error = str(exc)

        stage.completedAt = datetime.utcnow()
        await db.commit()

    async def execute_verify_stage(
        self,
        db: AsyncSession,
        stage: Any,
        issue: Any,
        project_path: str,
    ) -> VerificationResult:
        """Run Chrome MCP verification.

        NOTE: Full implementation deferred to CB-1243.  Currently returns a
        stub result that auto-passes so the pipeline can be tested end-to-end
        without Chrome MCP infrastructure.
        """
        stage.status = StageStatus.RUNNING.value
        stage.startedAt = datetime.utcnow()
        await db.commit()

        try:
            # ----- STUB: Replace with Chrome MCP call in CB-1243 -----
            result = await self._chrome_mcp_verify(issue, project_path)
            # ----------------------------------------------------------

            stage.resultData = _json_dumps(result.to_dict())

            if result.passed:
                stage.status = StageStatus.COMPLETED.value
            else:
                # Verification "failed" is still a COMPLETED stage (the stage
                # ran successfully; its *result* was a failure).  advance_pipeline
                # reads the resultData to decide what to do.
                stage.status = StageStatus.COMPLETED.value
                stage.error = result.error_message

        except Exception as exc:
            logger.exception("VERIFY stage error for pipeline stage %s", stage.id)
            stage.status = StageStatus.FAILED.value
            stage.error = str(exc)
            result = VerificationResult(passed=False, error_message=str(exc))

        stage.completedAt = datetime.utcnow()
        await db.commit()
        return result

    async def execute_fix_stage(
        self,
        db: AsyncSession,
        stage: Any,
        issue: Any,
        project_path: str,
        error_context: Dict[str, Any],
    ) -> None:
        """Run the fix stage -- sends error context back to Claude Code.

        Builds a prompt that includes what was implemented, what verification
        found wrong, screenshots/evidence from Chrome MCP, and specific fix
        instructions.
        """
        from services.terminal_service import terminal_service, ExecutionProvider

        stage.status = StageStatus.RUNNING.value
        stage.startedAt = datetime.utcnow()
        await db.commit()

        try:
            fix_prompt = self.format_fix_prompt(issue, error_context)

            session = await terminal_service.start_execution(
                issue_id=issue.id,
                issue_key=issue.key,
                issue_title=f"[FIX] {issue.title}",
                issue_description=issue.description or "",
                issue_type=issue.type,
                provider=ExecutionProvider.CLAUDE_CODE,
                project_path=project_path,
                project_id=issue.projectId,
                prompt_override=fix_prompt,
            )

            stage.sessionId = session.id
            await db.commit()

            result_status = await self._wait_for_session(session.id)

            if result_status == "completed":
                stage.status = StageStatus.COMPLETED.value
                stage.resultData = _json_dumps({
                    "session_id": session.id,
                    "exit_code": session.exit_code,
                    "output_lines": len(session.output),
                    "files_written": session.files_written,
                })
            else:
                stage.status = StageStatus.FAILED.value
                stage.error = session.error or f"Fix session ended with status: {result_status}"
                stage.resultData = _json_dumps({
                    "session_id": session.id,
                    "exit_code": session.exit_code,
                })

        except Exception as exc:
            logger.exception("FIX stage error for pipeline stage %s", stage.id)
            stage.status = StageStatus.FAILED.value
            stage.error = str(exc)

        stage.completedAt = datetime.utcnow()
        await db.commit()

    async def get_pipeline_status(
        self,
        db: AsyncSession,
        execution_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get full pipeline status including all stages."""
        PipelineExecution, PipelineStage, _ = _import_models()

        execution = await self._get_execution(db, execution_id)
        if not execution:
            return None

        # Get all stages ordered by index
        result = await db.execute(
            select(PipelineStage)
            .where(PipelineStage.executionId == execution_id)
            .order_by(PipelineStage.stageIndex)
        )
        stages = result.scalars().all()

        return {
            "id": execution.id,
            "issueId": execution.issueId,
            "projectId": execution.projectId,
            "status": execution.status,
            "currentStageIndex": execution.currentStageIndex,
            "retryCount": execution.retryCount,
            "maxRetries": execution.maxRetries,
            "error": execution.error,
            "startedAt": execution.startedAt.isoformat() if execution.startedAt else None,
            "completedAt": execution.completedAt.isoformat() if execution.completedAt else None,
            "stages": [
                {
                    "id": s.id,
                    "stageType": s.stageType,
                    "stageIndex": s.stageIndex,
                    "status": s.status,
                    "sessionId": getattr(s, "sessionId", None),
                    "error": s.error,
                    "resultData": s.resultData,
                    "startedAt": s.startedAt.isoformat() if s.startedAt else None,
                    "completedAt": s.completedAt.isoformat() if s.completedAt else None,
                }
                for s in stages
            ],
        }

    async def cancel_pipeline(
        self,
        db: AsyncSession,
        execution_id: str,
    ) -> bool:
        """Cancel a running pipeline.

        Marks the execution and any pending/running stages as CANCELLED.
        Attempts to stop any running terminal sessions.
        """
        PipelineExecution, PipelineStage, _ = _import_models()

        execution = await self._get_execution(db, execution_id)
        if not execution:
            return False

        if execution.status != PipelineStatus.RUNNING.value:
            logger.warning("Cannot cancel pipeline %s with status %s", execution_id, execution.status)
            return False

        self._cancelled.add(execution_id)

        # Cancel background task if it exists
        bg_task = self._running.pop(execution_id, None)
        if bg_task and not bg_task.done():
            bg_task.cancel()

        # Mark execution as cancelled
        execution.status = PipelineStatus.CANCELLED.value
        execution.completedAt = datetime.utcnow()

        # Cancel all pending/running stages
        result = await db.execute(
            select(PipelineStage)
            .where(
                PipelineStage.executionId == execution_id,
                PipelineStage.status.in_([StageStatus.PENDING.value, StageStatus.RUNNING.value]),
            )
        )
        stages = result.scalars().all()

        for stage in stages:
            stage.status = StageStatus.CANCELLED.value
            stage.completedAt = datetime.utcnow()

            # Try to stop any running terminal session
            session_id = getattr(stage, "sessionId", None)
            if session_id:
                try:
                    from services.terminal_service import terminal_service
                    await terminal_service.stop_execution(session_id)
                except Exception as e:
                    logger.warning("Failed to stop session %s during cancel: %s", session_id, e)

        await db.commit()
        logger.info("Pipeline %s cancelled", execution_id)
        return True

    def format_fix_prompt(
        self,
        issue: Any,
        error_context: Dict[str, Any],
    ) -> str:
        """Format verification error into a prompt for the fix stage.

        Includes:
          - What was originally implemented (issue details)
          - What verification found wrong
          - Screenshots/evidence from Chrome MCP
          - Specific fix instructions
        """
        verification_error = error_context.get("error_message", "Unknown verification failure")
        evidence = error_context.get("evidence", {})
        screenshots = error_context.get("screenshots", [])
        retry_number = error_context.get("retry_number", 1)
        max_retries = error_context.get("max_retries", DEFAULT_MAX_FIX_RETRIES)

        parts = []

        # Header
        parts.append(f"# FIX REQUIRED - Verification Failed (Attempt {retry_number}/{max_retries})")
        parts.append("")

        # Original task context
        parts.append("## Original Task")
        parts.append(f"**{getattr(issue, 'key', 'UNKNOWN')}: {getattr(issue, 'title', '')}**")
        parts.append("")
        if getattr(issue, "description", None):
            parts.append(getattr(issue, "description"))
            parts.append("")

        # What went wrong
        parts.append("## Verification Failure")
        parts.append(f"The automated UI verification found the following issue:")
        parts.append("")
        parts.append(f"**Error:** {verification_error}")
        parts.append("")

        # Evidence details
        if evidence:
            parts.append("## Evidence")
            for key, value in evidence.items():
                parts.append(f"- **{key}:** {value}")
            parts.append("")

        # Screenshot references
        if screenshots:
            parts.append("## Screenshots")
            parts.append("The following screenshots were captured during verification:")
            for i, screenshot in enumerate(screenshots, 1):
                parts.append(f"  {i}. {screenshot}")
            parts.append("")

        # Fix instructions
        parts.append("## Instructions")
        parts.append(
            "Please fix the issue described above. "
            "The implementation was completed but the automated verification "
            "detected a problem. Review the error details and evidence, then "
            "make the necessary corrections."
        )
        parts.append("")
        parts.append("Focus on:")
        parts.append("1. Understanding what the verification expected vs. what it found")
        parts.append("2. Making the minimal change needed to fix the issue")
        parts.append("3. Ensuring the fix does not break other functionality")
        parts.append("")
        parts.append("When you're done, summarize what you fixed.")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Internal: pipeline orchestration loop
    # ------------------------------------------------------------------

    async def _run_pipeline(
        self,
        db: AsyncSession,
        execution_id: str,
        issue_id: str,
        project_id: str,
        project_path: str,
        agent_id: Optional[str] = None,
    ) -> None:
        """Main pipeline loop -- runs stages sequentially until done.

        This runs as an asyncio background task. It fetches fresh state from
        the DB at each iteration so it picks up stages added by advance_pipeline.
        """
        from models.database import AsyncSessionLocal
        from models.issue import Issue

        try:
            while True:
                # Check cancellation
                if execution_id in self._cancelled:
                    logger.info("Pipeline %s: cancellation detected, stopping loop", execution_id)
                    break

                async with AsyncSessionLocal() as session_db:
                    execution = await self._get_execution(session_db, execution_id)
                    if not execution or execution.status != PipelineStatus.RUNNING.value:
                        break

                    # Get current stage
                    current_stage = await self._get_stage_at_index(
                        session_db, execution_id, execution.currentStageIndex
                    )
                    if not current_stage:
                        execution.status = PipelineStatus.FAILED.value
                        execution.error = "No stage found at current index"
                        execution.completedAt = datetime.utcnow()
                        await session_db.commit()
                        break

                    # Skip already completed stages
                    if current_stage.status in (
                        StageStatus.COMPLETED.value,
                        StageStatus.FAILED.value,
                        StageStatus.SKIPPED.value,
                        StageStatus.CANCELLED.value,
                    ):
                        # Advance
                        execution = await self.advance_pipeline(session_db, execution_id)
                        if execution.status != PipelineStatus.RUNNING.value:
                            break
                        continue

                    # Fetch the issue for stage execution
                    issue_result = await session_db.execute(
                        select(Issue).where(Issue.id == issue_id)
                    )
                    issue = issue_result.scalar_one_or_none()
                    if not issue:
                        execution.status = PipelineStatus.FAILED.value
                        execution.error = f"Issue {issue_id} not found"
                        execution.completedAt = datetime.utcnow()
                        await session_db.commit()
                        break

                    # Execute the stage
                    stage_type = current_stage.stageType

                    if stage_type == StageType.IMPLEMENT.value:
                        await self.execute_implement_stage(
                            session_db, current_stage, issue, project_path, agent_id
                        )
                    elif stage_type in (StageType.VERIFY.value, StageType.RE_VERIFY.value):
                        await self.execute_verify_stage(
                            session_db, current_stage, issue, project_path
                        )
                    elif stage_type == StageType.FIX.value:
                        # Build error context from inputData (set by advance_pipeline)
                        error_context = _json_loads(current_stage.inputData) if current_stage.inputData else {}
                        error_context["retry_number"] = execution.retryCount
                        error_context["max_retries"] = execution.maxRetries
                        await self.execute_fix_stage(
                            session_db, current_stage, issue, project_path, error_context
                        )
                    else:
                        logger.error("Unknown stage type: %s", stage_type)
                        current_stage.status = StageStatus.FAILED.value
                        current_stage.error = f"Unknown stage type: {stage_type}"
                        current_stage.completedAt = datetime.utcnow()
                        await session_db.commit()

                    # After stage execution, advance the pipeline
                    execution = await self.advance_pipeline(session_db, execution_id)
                    if execution.status != PipelineStatus.RUNNING.value:
                        break

        except asyncio.CancelledError:
            logger.info("Pipeline %s background task cancelled", execution_id)
        except Exception:
            logger.exception("Unhandled error in pipeline %s loop", execution_id)
            # Try to mark as failed
            try:
                async with AsyncSessionLocal() as session_db:
                    execution = await self._get_execution(session_db, execution_id)
                    if execution and execution.status == PipelineStatus.RUNNING.value:
                        execution.status = PipelineStatus.FAILED.value
                        execution.error = "Unhandled pipeline executor error"
                        execution.completedAt = datetime.utcnow()
                        await session_db.commit()
            except Exception:
                logger.exception("Failed to mark pipeline %s as failed", execution_id)
        finally:
            self._running.pop(execution_id, None)
            self._cancelled.discard(execution_id)

    # ------------------------------------------------------------------
    # Internal: stage helpers
    # ------------------------------------------------------------------

    async def _activate_next_stage(
        self,
        db: AsyncSession,
        execution: Any,
    ) -> Any:
        """Bump currentStageIndex and persist."""
        execution.currentStageIndex += 1
        await db.commit()
        return execution

    async def _get_execution(self, db: AsyncSession, execution_id: str) -> Any:
        """Fetch a PipelineExecution by ID."""
        PipelineExecution, _, _ = _import_models()
        result = await db.execute(
            select(PipelineExecution).where(PipelineExecution.id == execution_id)
        )
        return result.scalar_one_or_none()

    async def _get_stage_at_index(
        self,
        db: AsyncSession,
        execution_id: str,
        stage_index: int,
    ) -> Any:
        """Fetch a PipelineStage by execution ID and stage index."""
        _, PipelineStage, _ = _import_models()
        result = await db.execute(
            select(PipelineStage).where(
                PipelineStage.executionId == execution_id,
                PipelineStage.stageIndex == stage_index,
            )
        )
        return result.scalar_one_or_none()

    def _stage_result_passed(self, stage: Any) -> bool:
        """Check if a verification stage result indicates pass."""
        if not stage.resultData:
            return False
        data = _json_loads(stage.resultData)
        return data.get("passed", False)

    async def _wait_for_session(
        self,
        session_id: str,
        poll_interval: float = 2.0,
        timeout: float = DEFAULT_IMPLEMENT_TIMEOUT_SECONDS,
    ) -> str:
        """Poll terminal_service until the session finishes.

        Returns the final status string: 'completed', 'failed', 'cancelled'.
        """
        from services.terminal_service import terminal_service, ExecutionStatus

        elapsed = 0.0
        while elapsed < timeout:
            session = terminal_service.get_session(session_id)
            if not session:
                return "failed"

            if session.status == ExecutionStatus.COMPLETED:
                return "completed"
            elif session.status == ExecutionStatus.FAILED:
                return "failed"
            elif session.status == ExecutionStatus.CANCELLED:
                return "cancelled"

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        # Timed out -- try to stop
        try:
            await terminal_service.stop_execution(session_id)
        except Exception:
            pass
        return "failed"

    async def _chrome_mcp_verify(
        self,
        issue: Any,
        project_path: str,
    ) -> VerificationResult:
        """Stub for Chrome MCP verification.

        TODO (CB-1243): Replace with actual Chrome MCP integration.
        For now, returns a passing result so pipelines complete end-to-end.
        """
        logger.info(
            "VERIFY stub: auto-passing for issue %s (Chrome MCP integration pending CB-1243)",
            getattr(issue, "key", "?"),
        )
        return VerificationResult(
            passed=True,
            evidence={"note": "Stub verification -- Chrome MCP not yet integrated (CB-1243)"},
            error_message=None,
            screenshots=[],
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _import_models():
    """Lazily import pipeline models.

    The models are being created by another agent in parallel.  We use lazy
    import so this module can be loaded even if models/pipeline.py does not
    exist yet at import time.
    """
    try:
        from models.pipeline import PipelineExecution, PipelineStage, PipelineConfig
        return PipelineExecution, PipelineStage, PipelineConfig
    except ImportError:
        raise ImportError(
            "models.pipeline not found. PipelineExecution, PipelineStage, and "
            "PipelineConfig models must be created before the pipeline executor "
            "can be used. See CB-1240 / CB-1241."
        )


def _json_dumps(obj: Any) -> str:
    """Safe JSON serialization."""
    import json
    return json.dumps(obj, default=str)


def _json_loads(s: Optional[str]) -> dict:
    """Safe JSON deserialization."""
    if not s:
        return {}
    import json
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

pipeline_executor = PipelineExecutor()
