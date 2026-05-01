"""
QA Service - Handles QA plan generation and execution
"""

import asyncio
import json
import re
import uuid
from typing import List, Dict, Any, Optional, Callable, AsyncGenerator, TYPE_CHECKING
from datetime import datetime
import logging

from services.ai_service import ai_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from services.rag_service import RAGService

logger = logging.getLogger(__name__)


class ExecutionState:
    """Tracks state for a running execution batch"""

    def __init__(self, execution_id: str, total_tasks: int):
        self.execution_id = execution_id
        self.total_tasks = total_tasks
        self.completed_tasks = 0
        self.current_task_index = 0
        self.current_task_key: Optional[str] = None
        self.status = "running"  # running, completed, aborted, error
        self.results: List[Dict[str, Any]] = []
        self.abort_requested = False
        self.started_at = datetime.now()
        self.ended_at: Optional[datetime] = None

    def request_abort(self):
        """Request abortion of this execution"""
        self.abort_requested = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for API response"""
        return {
            "executionId": self.execution_id,
            "totalTasks": self.total_tasks,
            "completedTasks": self.completed_tasks,
            "currentTaskIndex": self.current_task_index,
            "currentTaskKey": self.current_task_key,
            "status": self.status,
            "progress": round(self.completed_tasks / self.total_tasks * 100, 1) if self.total_tasks > 0 else 0,
            "startedAt": self.started_at.isoformat(),
            "endedAt": self.ended_at.isoformat() if self.ended_at else None,
        }


class QAService:
    """Service for QA operations including plan generation and execution"""

    def __init__(self):
        self.max_history_entries = 10  # Keep last 10 full runs
        # Track active executions for abort capability
        self._active_executions: Dict[str, ExecutionState] = {}
        # CB-1600: RAG service for fetching implementation context (ExecutionSummary).
        # Wired in app/main.py lifespan after RAGService initialization. Optional —
        # if None, generate_qa_plan skips the implementation-details section.
        self._rag: Optional["RAGService"] = None

    def get_execution_state(self, execution_id: str) -> Optional[ExecutionState]:
        """Get the state of an execution by ID"""
        return self._active_executions.get(execution_id)

    def abort_execution(self, execution_id: str) -> bool:
        """Request abortion of an execution. Returns True if execution found."""
        state = self._active_executions.get(execution_id)
        if state:
            state.request_abort()
            logger.info(f"Abort requested for execution {execution_id}")
            return True
        return False

    def list_active_executions(self) -> List[Dict[str, Any]]:
        """List all active executions"""
        return [
            state.to_dict()
            for state in self._active_executions.values()
            if state.status == "running"
        ]

    def _parse_qa_config(self, custom_instructions: Optional[str]) -> Dict[str, Any]:
        """Parse QA configuration from custom instructions."""
        config = {
            "level": "standard",
            "min_tests": 8,
            "max_tests": 12,
            "cycles": 1,
            "areas": ["functional"],
            # Environment options
            "target_browsers": [],
            "target_devices": [],
            "include_responsive": False,
            # Test data options
            "include_data_variations": False,
            "include_localization": False,
            "locales": [],
            # Execution options
            "estimate_time": True,
            "include_prerequisites": True,
            "include_cleanup": False,
            # Test depth & complexity options
            "test_complexity": "moderate",
            "include_api_tests": False,
            "include_data_integrity_tests": False,
            "include_error_recovery_tests": False,
            "include_concurrency_tests": False,
            "include_state_management_tests": False,
        }

        if not custom_instructions:
            return config

        # Parse testing level
        if "### Testing Level: Basic" in custom_instructions:
            config["level"] = "basic"
            config["min_tests"] = 3
            config["max_tests"] = 5
        elif "### Testing Level: Standard" in custom_instructions:
            config["level"] = "standard"
            config["min_tests"] = 8
            config["max_tests"] = 12
        elif "### Testing Level: Comprehensive" in custom_instructions:
            config["level"] = "comprehensive"
            config["min_tests"] = 15
            config["max_tests"] = 20

        # Parse test cycles
        cycles_match = re.search(r"### Test Cycles: (\d+)", custom_instructions)
        if cycles_match:
            config["cycles"] = int(cycles_match.group(1))

        # Parse test areas
        areas = []
        if "**Functional**" in custom_instructions:
            areas.append("functional")
        if "**UI/UX**" in custom_instructions:
            areas.append("ui")
        if "**Integration**" in custom_instructions:
            areas.append("integration")
        if "**Performance**" in custom_instructions:
            areas.append("performance")
        if "**Security**" in custom_instructions:
            areas.append("security")
        if "**Accessibility**" in custom_instructions:
            areas.append("accessibility")

        if areas:
            config["areas"] = areas

        # Parse environment options
        if "### Environment & Devices:" in custom_instructions:
            # Target browsers
            browsers_match = re.search(r"Target Browsers: ([^\n]+)", custom_instructions)
            if browsers_match:
                config["target_browsers"] = [b.strip() for b in browsers_match.group(1).split(",")]

            # Target devices
            devices_match = re.search(r"Target Devices: ([^\n]+)", custom_instructions)
            if devices_match:
                config["target_devices"] = [d.strip() for d in devices_match.group(1).split(",")]

            # Responsive tests
            if "responsive design tests" in custom_instructions.lower():
                config["include_responsive"] = True

        # Parse test data options
        if "### Test Data Options:" in custom_instructions:
            if "varied data sets" in custom_instructions.lower():
                config["include_data_variations"] = True
            if "localization/internationalization" in custom_instructions.lower():
                config["include_localization"] = True
            # Target locales
            locales_match = re.search(r"Target Locales: ([^\n]+)", custom_instructions)
            if locales_match:
                config["locales"] = [l.strip() for l in locales_match.group(1).split(",")]

        # Parse execution options
        if "### Execution Options:" in custom_instructions:
            config["estimate_time"] = "estimated execution time" in custom_instructions.lower()
            config["include_prerequisites"] = "prerequisites/preconditions" in custom_instructions.lower()
            config["include_cleanup"] = "cleanup/teardown" in custom_instructions.lower()

        # Parse test depth & complexity options
        if "### Test Depth & Complexity:" in custom_instructions:
            complexity_match = re.search(r"Complexity Level: (\w+)", custom_instructions)
            if complexity_match:
                config["test_complexity"] = complexity_match.group(1).lower()

        # Parse specialized testing options
        if "### Specialized Testing:" in custom_instructions:
            if "api/endpoint tests" in custom_instructions.lower():
                config["include_api_tests"] = True
            if "data integrity tests" in custom_instructions.lower():
                config["include_data_integrity_tests"] = True
            if "error recovery tests" in custom_instructions.lower():
                config["include_error_recovery_tests"] = True
            if "concurrency tests" in custom_instructions.lower():
                config["include_concurrency_tests"] = True
            if "state management tests" in custom_instructions.lower():
                config["include_state_management_tests"] = True

        return config

    async def generate_qa_plan(
        self,
        project_id: str,
        issue_id: str,
        issue_title: str,
        issue_description: Optional[str],
        issue_type: str,
        children: List[Dict],
        custom_instructions: Optional[str] = None,
        db: Optional["AsyncSession"] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate QA test cases for an issue using AI.

        Args:
            project_id: The project ID
            issue_id: The issue being tested
            issue_title: Issue title
            issue_description: Issue description
            issue_type: Issue type (FEATURE, EPIC, STORY, TASK, etc.)
            children: List of child issues
            custom_instructions: Optional custom instructions for QA generation
            db: Optional AsyncSession used to fetch the latest ExecutionSummary
                for this issue (CB-1600). When provided alongside a wired
                self._rag, the implementation-details block is injected into
                the prompt. If omitted (or RAG is unwired) the section is
                skipped — preserves backwards compatibility with callers that
                have not yet been updated by CB-1601.

        Returns:
            List of QA task suggestions
        """
        if not ai_service.is_available():
            logger.warning("AI service not available for QA plan generation")
            return []

        # CB-1600: fetch implementation context from latest ExecutionSummary
        # via RAG so generated tests target what was actually built.
        impl_context = ""
        if db is not None and self._rag is not None:
            try:
                impl_context = await self._rag.get_implementation_context_for_qa(
                    db, project_id, issue_id
                )
            except Exception as e:
                logger.warning(
                    f"Failed to fetch implementation context for issue {issue_id}: {e}"
                )
                impl_context = ""

        # Parse QA configuration from custom instructions
        qa_config = self._parse_qa_config(custom_instructions)
        logger.info(f"QA Config: level={qa_config['level']}, tests={qa_config['min_tests']}-{qa_config['max_tests']}, areas={qa_config['areas']}")

        # Build context from children
        children_context = ""
        if children:
            children_context = "\n\nRelated items to test:\n"
            for child in children[:20]:  # Limit to 20 children
                children_context += f"- {child.get('type', 'TASK')}: {child.get('title', '')}\n"

        # Build custom instructions section
        custom_section = ""
        if custom_instructions:
            custom_section = f"\n\nAdditional Testing Requirements:\n{custom_instructions}\n"

        # Build area-specific instructions
        area_instructions = []
        if "functional" in qa_config["areas"]:
            area_instructions.append("- Core feature functionality and business logic validation")
        if "ui" in qa_config["areas"]:
            area_instructions.append("- User interface elements, interactions, and visual feedback")
        if "integration" in qa_config["areas"]:
            area_instructions.append("- Integration with APIs, databases, and external services")
        if "performance" in qa_config["areas"]:
            area_instructions.append("- Performance under load, response times, and resource usage")
        if "security" in qa_config["areas"]:
            area_instructions.append("- Security vulnerabilities, access control, and data protection")
        if "accessibility" in qa_config["areas"]:
            area_instructions.append("- WCAG compliance, keyboard navigation, and screen reader support")

        areas_section = "\n".join(area_instructions) if area_instructions else "- General functionality testing"

        # Adjust prompt based on level
        level_guidance = ""
        if qa_config["level"] == "basic":
            level_guidance = "Focus on essential smoke tests and critical path validation. Keep tests simple and direct."
        elif qa_config["level"] == "standard":
            level_guidance = "Include happy path, edge cases, and basic error handling. Balance thoroughness with practicality."
        else:  # comprehensive
            level_guidance = "Provide exhaustive coverage including edge cases, boundary conditions, error scenarios, and stress testing."

        # Cycle-specific guidance
        cycle_guidance = ""
        if qa_config["cycles"] > 1:
            cycle_guidance = f"\nNote: Tests should be designed to support {qa_config['cycles']} execution cycles. Include regression tests that verify previous functionality remains intact."

        # Environment-specific guidance
        environment_guidance = ""
        if qa_config["target_browsers"]:
            environment_guidance += f"\n- Target browsers: {', '.join(qa_config['target_browsers'])}"
        if qa_config["target_devices"]:
            environment_guidance += f"\n- Target devices: {', '.join(qa_config['target_devices'])}"
        if qa_config["include_responsive"]:
            environment_guidance += "\n- Include tests for responsive design and different screen sizes"

        # Test data guidance
        test_data_guidance = ""
        if qa_config["include_data_variations"]:
            test_data_guidance += "\n- Include tests with varied data sets (valid, invalid, edge case data)"
        if qa_config["include_localization"]:
            test_data_guidance += "\n- Include localization/internationalization tests"
            if qa_config["locales"]:
                test_data_guidance += f" for: {', '.join(qa_config['locales'])}"

        # Execution format guidance
        execution_format = ""
        if qa_config["estimate_time"]:
            execution_format += "\n- estimatedTime: Estimated execution time (e.g., '5 min', '15 min')"
        if qa_config["include_prerequisites"]:
            execution_format += "\n- prerequisites: List of setup steps or preconditions"
        if qa_config["include_cleanup"]:
            execution_format += "\n- cleanup: Teardown/cleanup steps after test execution"

        # Test complexity guidance
        complexity_guidance = ""
        if qa_config["test_complexity"] == "simple":
            complexity_guidance = "\n- Use simple, single-step verifications with clear pass/fail criteria"
        elif qa_config["test_complexity"] == "detailed":
            complexity_guidance = "\n- Create comprehensive multi-step scenarios with thorough validations and edge case coverage"
        else:  # moderate
            complexity_guidance = "\n- Use balanced multi-step scenarios with reasonable validation coverage"

        # Specialized testing guidance
        specialized_guidance = ""
        if qa_config["include_api_tests"]:
            specialized_guidance += "\n- Include API/endpoint tests: validate REST/GraphQL endpoints, response codes, payloads, error handling"
        if qa_config["include_data_integrity_tests"]:
            specialized_guidance += "\n- Include data integrity tests: verify database consistency, data persistence, CRUD operations, data validation"
        if qa_config["include_error_recovery_tests"]:
            specialized_guidance += "\n- Include error recovery tests: resilience, graceful degradation, retry mechanisms, timeout handling"
        if qa_config["include_concurrency_tests"]:
            specialized_guidance += "\n- Include concurrency tests: multi-user scenarios, race conditions, simultaneous operations, locking behavior"
        if qa_config["include_state_management_tests"]:
            specialized_guidance += "\n- Include state management tests: state transitions, persistence across sessions, undo/redo, session handling"

        # CB-1600: implementation-details section, only when context is non-empty.
        # Placed between the item-to-test block and the testing-configuration
        # block so the AI grounds tests in what was actually built before
        # selecting test areas/levels.
        # Defense-in-depth (CB-1600 sec audit, M-1 + L-1):
        #   * Neutralize literal close-fence so a crafted ExecutionSummary cannot
        #     escape the IMPLEMENTATION DETAILS block to inject prompt instructions.
        #   * Cap length at 8 KB to bound input-token cost from a pathological summary.
        impl_section = ""
        if impl_context:
            safe_context = impl_context.replace(
                "=== END IMPLEMENTATION DETAILS ===",
                "=== END IMPL DETAILS (escaped) ===",
            )
            if len(safe_context) > 8000:
                safe_context = safe_context[:8000] + "\n[... truncated ...]"
            impl_section = f"\n=== IMPLEMENTATION DETAILS ===\n{safe_context}\n=== END IMPLEMENTATION DETAILS ===\n"

        prompt = f"""Generate comprehensive QA test cases for this {issue_type}.

=== ITEM TO TEST ===
Title: {issue_title}
Type: {issue_type}
{f"Description: {issue_description}" if issue_description else ""}
{children_context}
{custom_section}
=== END OF ITEM ===
{impl_section}
=== TESTING CONFIGURATION ===
Testing Level: {qa_config['level'].upper()}
{level_guidance}

Test Complexity: {qa_config['test_complexity'].upper()}
{complexity_guidance}

Required Test Areas:
{areas_section}
{cycle_guidance}
{environment_guidance if environment_guidance else ""}
{test_data_guidance if test_data_guidance else ""}
{specialized_guidance if specialized_guidance else ""}
=== END CONFIGURATION ===

Generate detailed QA test cases. For each test case provide:
- title: Clear, specific test case title (e.g., "Verify login with valid credentials")
- scenario: Step-by-step test procedure (numbered steps)
- expectedResult: What should happen when test passes
- type: AUTOMATED or MANUAL (MANUAL for visual/UX tests, accessibility, and subjective evaluation)
- priority: CRITICAL, HIGH, MEDIUM, or LOW{execution_format}

Return a JSON array:
[
  {{
    "title": "Verify feature works correctly",
    "scenario": "1. Open the application\\n2. Navigate to feature\\n3. Perform action\\n4. Check result",
    "expectedResult": "The feature should work as expected with correct output",
    "type": "AUTOMATED",
    "priority": "HIGH"{', "estimatedTime": "5 min"' if qa_config["estimate_time"] else ""}{', "prerequisites": ["User is logged in"]' if qa_config["include_prerequisites"] else ""}{', "cleanup": ["Log out user"]' if qa_config["include_cleanup"] else ""}
  }}
]

Generate {qa_config['min_tests']}-{qa_config['max_tests']} test cases covering the specified test areas.
Return ONLY the JSON array, no other text."""

        try:
            logger.info(f"Generating QA plan for issue {issue_id}: {issue_title}")
            content = await ai_service._generate(prompt, max_tokens=4000)

            if content:
                qa_tasks = ai_service._extract_json_array(content)
                logger.info(f"Generated {len(qa_tasks)} QA tasks")
                return qa_tasks
            return []
        except Exception as e:
            logger.error(f"Error generating QA plan: {e}")
            return []

    async def execute_qa_task(
        self,
        qa_task: Dict,
        project_path: str,
        issue_context: Optional[Dict] = None,
        db: Optional["AsyncSession"] = None,
    ) -> Dict[str, Any]:
        """
        Execute a single automated QA task using AI.

        This function analyzes the test case, considers the issue context and
        project structure, and uses AI to determine if the test would pass
        or fail based on the expected implementation.

        Args:
            qa_task: The QA task to execute containing:
                - id: Task ID
                - key: Task key (e.g., "QA-001")
                - title: Test case title
                - scenario: Step-by-step test procedure
                - expectedResult: What should happen when test passes
                - type: AUTOMATED or MANUAL
                - priority: CRITICAL, HIGH, MEDIUM, LOW
            project_path: Path to the project being tested
            issue_context: Optional context about the issue being tested:
                - id: Issue ID (DB primary key) — required to look up the
                  ExecutionSummary in CB-1603
                - projectId: Project ID — required to enforce cross-project
                  isolation when fetching the ExecutionSummary
                - key: Issue key (e.g., "CB-123")
                - title: Issue title
                - type: Issue type (FEATURE, STORY, TASK, etc.)
                - description: Issue description
                - status: Current issue status
            db: Optional AsyncSession used (alongside a wired self._rag) to
                fetch the latest ExecutionSummary for the linked issue
                (CB-1603). When provided, the implementation-context block is
                injected into the execution prompt so the AI can ground its
                pass/fail verdict in what was actually built. Omitted (or
                rag-unwired) callers fall back to the pre-CB-1603 prompt.

        Returns:
            Execution result dict with:
                - qaTaskId: The QA task ID
                - key: The QA task key
                - status: 'PASS', 'FAILED', or 'NOT_DONE'
                - actualResult: Description of what happened during execution
                - executionTime: Time taken in seconds
                - error: Error message if any, otherwise None
        """
        start_time = datetime.now()
        task_id = qa_task.get('id')
        task_key = qa_task.get('key')

        # Manual tests cannot be auto-executed
        if qa_task.get('type') == 'MANUAL':
            logger.info(f"QA task {task_key} is manual, skipping automated execution")
            return {
                'qaTaskId': task_id,
                'key': task_key,
                'status': 'NOT_DONE',
                'actualResult': 'This is a manual test case. Please execute manually and mark the result.',
                'executionTime': 0,
                'error': None,
            }

        # Check AI service availability
        if not ai_service.is_available():
            logger.warning(f"AI service not available for QA task {task_key}")
            return {
                'qaTaskId': task_id,
                'key': task_key,
                'status': 'FAILED',
                'actualResult': None,
                'executionTime': 0,
                'error': 'AI service not available',
            }

        # Build issue context section for the prompt
        issue_context_section = ""
        if issue_context:
            issue_context_section = f"""
=== ISSUE BEING TESTED ===
Issue Key: {issue_context.get('key', 'Unknown')}
Issue Title: {issue_context.get('title', 'Unknown')}
Issue Type: {issue_context.get('type', 'Unknown')}
Issue Status: {issue_context.get('status', 'Unknown')}
{f"Description: {issue_context.get('description')}" if issue_context.get('description') else ""}
=== END ISSUE CONTEXT ===
"""

        # CB-1603: fetch implementation context from latest ExecutionSummary
        # via RAG so the AI grounds pass/fail in what was actually built
        # (file paths, components, architecture notes) rather than in abstract
        # requirements. Requires db, a wired self._rag, and an issue_context
        # carrying both `id` and `projectId` (project scoping enforces the
        # same cross-project isolation boundary as CB-1600/CB-1601).
        impl_context = ""
        if (
            db is not None
            and self._rag is not None
            and issue_context is not None
            and issue_context.get("id")
            and issue_context.get("projectId")
        ):
            try:
                impl_context = await self._rag.get_implementation_context_for_qa(
                    db,
                    issue_context["projectId"],
                    issue_context["id"],
                )
            except Exception as e:
                logger.warning(
                    f"Failed to fetch implementation context for QA task "
                    f"{task_key} (issue {issue_context.get('key')}): {e}"
                )
                impl_context = ""

        # Defense-in-depth (mirrors CB-1600 sec audit M-1 + L-1 on
        # generate_qa_plan):
        #   * Neutralize the literal close fence so a crafted ExecutionSummary
        #     cannot escape the IMPLEMENTATION CONTEXT block to inject prompt
        #     instructions that flip the verdict.
        #   * Cap length at 8 KB to bound input-token cost from a pathological
        #     summary.
        impl_section = ""
        if impl_context:
            safe_context = impl_context.replace(
                "=== END IMPLEMENTATION CONTEXT ===",
                "=== END IMPL CONTEXT (escaped) ===",
            )
            if len(safe_context) > 8000:
                safe_context = safe_context[:8000] + "\n[... truncated ...]"
            impl_section = (
                f"\n=== IMPLEMENTATION CONTEXT ===\n{safe_context}\n"
                f"=== END IMPLEMENTATION CONTEXT ===\n"
            )

        # Build priority context
        priority = qa_task.get('priority', 'MEDIUM')
        priority_note = ""
        if priority == 'CRITICAL':
            priority_note = "This is a CRITICAL priority test - any failure is a blocker."
        elif priority == 'HIGH':
            priority_note = "This is a HIGH priority test - failures should be addressed promptly."

        # Build the execution prompt
        prompt = f"""You are a QA engineer executing an automated test case. Analyze the test case and determine if it would PASS or FAIL based on the expected implementation.

=== TEST CASE ===
Test Key: {task_key}
Title: {qa_task.get('title')}
Priority: {priority}
{priority_note}

Test Scenario (Steps to Execute):
{qa_task.get('scenario', 'No scenario provided')}

Expected Result:
{qa_task.get('expectedResult', 'No expected result provided')}

Project Path: {project_path}
=== END TEST CASE ===
{issue_context_section}{impl_section}
Analyze this test case and simulate its execution. Consider:

1. FUNCTIONALITY CHECK: Does the described functionality make sense for this type of feature?
2. SCENARIO VALIDITY: Are the test steps logical and executable?
3. EXPECTED RESULT: Is the expected result reasonable and testable?
4. IMPLEMENTATION ANALYSIS: Based on common implementation patterns, would this test likely pass?

Think through each step of the scenario and determine the likely outcome.

Return a JSON object with your analysis:
{{
  "status": "PASS" or "FAILED",
  "actualResult": "Detailed description of the test execution simulation and outcome",
  "details": "Technical analysis explaining why the test passed or failed",
  "confidence": "HIGH" or "MEDIUM" or "LOW"
}}

IMPORTANT:
- status must be exactly "PASS" or "FAILED"
- actualResult should describe what happened during the simulated test execution
- Be realistic - consider edge cases and common implementation issues

Return ONLY the JSON object, no additional text."""

        try:
            logger.info(f"Executing QA task: {task_key} - {qa_task.get('title')}")
            content = await ai_service._generate(prompt, max_tokens=800)

            execution_time = (datetime.now() - start_time).total_seconds()

            if content:
                result = ai_service._extract_json_object(content)
                status = result.get('status', 'FAILED').upper()

                # Validate status
                if status not in ['PASS', 'FAILED']:
                    logger.warning(f"Invalid status '{status}' for task {task_key}, defaulting to FAILED")
                    status = 'FAILED'

                # Build actual result with details if available
                actual_result = result.get('actualResult', 'Test executed')
                details = result.get('details')
                if details and details != actual_result:
                    actual_result = f"{actual_result}\n\nDetails: {details}"

                confidence = result.get('confidence', 'MEDIUM')
                logger.info(f"QA task {task_key} completed: {status} (confidence: {confidence})")

                return {
                    'qaTaskId': task_id,
                    'key': task_key,
                    'status': status,
                    'actualResult': actual_result,
                    'executionTime': execution_time,
                    'error': None,
                }

            logger.warning(f"No response from AI for QA task {task_key}")
            return {
                'qaTaskId': task_id,
                'key': task_key,
                'status': 'FAILED',
                'actualResult': None,
                'executionTime': execution_time,
                'error': 'No response from AI',
            }

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error executing QA task {task_key}: {e}")
            return {
                'qaTaskId': task_id,
                'key': task_key,
                'status': 'FAILED',
                'actualResult': None,
                'executionTime': execution_time,
                'error': str(e),
            }

    async def execute_qa_tasks_sequential(
        self,
        qa_tasks: List[Dict],
        project_path: str,
        issue_context: Optional[Dict] = None,
        on_progress: Optional[Callable] = None,
        execution_id: Optional[str] = None,
        db: Optional["AsyncSession"] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute QA tasks one by one (sequential).

        Args:
            qa_tasks: List of QA tasks to execute
            project_path: Path to the project
            issue_context: Optional context about the issue being tested
            on_progress: Optional callback for progress updates
            execution_id: Optional execution ID for state tracking

        Returns:
            List of execution results
        """
        results = []
        total = len(qa_tasks)

        # Create execution state if ID provided
        state: Optional[ExecutionState] = None
        if execution_id:
            state = ExecutionState(execution_id, total)
            self._active_executions[execution_id] = state
            logger.info(f"Started sequential execution {execution_id} with {total} tasks")

        try:
            for i, task in enumerate(qa_tasks):
                # Check for abort request
                if state and state.abort_requested:
                    logger.info(f"Execution {execution_id} aborted at task {i + 1}/{total}")
                    state.status = "aborted"
                    state.ended_at = datetime.now()
                    break

                # Update state
                if state:
                    state.current_task_index = i
                    state.current_task_key = task.get('key')

                if on_progress:
                    on_progress(i, total, task.get('key'), 'IN_PROGRESS')

                result = await self.execute_qa_task(
                    task, project_path, issue_context, db=db
                )
                results.append(result)

                # Update state after task completion
                if state:
                    state.completed_tasks = i + 1
                    state.results.append(result)

                if on_progress:
                    on_progress(i + 1, total, task.get('key'), result.get('status'))

            # Mark execution as completed
            if state and state.status == "running":
                state.status = "completed"
                state.ended_at = datetime.now()
                logger.info(f"Execution {execution_id} completed: {len(results)} tasks executed")

        except Exception as e:
            logger.error(f"Error in sequential execution {execution_id}: {e}")
            if state:
                state.status = "error"
                state.ended_at = datetime.now()
            raise
        finally:
            # Clean up old executions after a delay (keep for 5 minutes for status queries)
            if execution_id:
                asyncio.create_task(self._cleanup_execution(execution_id, delay=300))

        return results

    async def _cleanup_execution(self, execution_id: str, delay: int = 300):
        """Remove execution state after a delay"""
        await asyncio.sleep(delay)
        if execution_id in self._active_executions:
            del self._active_executions[execution_id]
            logger.debug(f"Cleaned up execution state for {execution_id}")

    async def execute_qa_tasks_sequential_stream(
        self,
        qa_tasks: List[Dict],
        project_path: str,
        issue_context: Optional[Dict] = None,
        execution_id: Optional[str] = None,
        db: Optional["AsyncSession"] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute QA tasks sequentially with streaming progress updates.

        Yields progress events as tasks are executed.

        Args:
            qa_tasks: List of QA tasks to execute
            project_path: Path to the project
            issue_context: Optional context about the issue being tested
            execution_id: Optional execution ID for state tracking

        Yields:
            Progress events with task status updates
        """
        total = len(qa_tasks)
        if not execution_id:
            execution_id = str(uuid.uuid4())

        # Create execution state
        state = ExecutionState(execution_id, total)
        self._active_executions[execution_id] = state
        logger.info(f"Started streaming sequential execution {execution_id} with {total} tasks")

        # Yield initial event
        yield {
            "event": "start",
            "executionId": execution_id,
            "totalTasks": total,
            "timestamp": datetime.now().isoformat(),
        }

        results = []
        try:
            for i, task in enumerate(qa_tasks):
                # Check for abort request
                if state.abort_requested:
                    logger.info(f"Execution {execution_id} aborted at task {i + 1}/{total}")
                    state.status = "aborted"
                    state.ended_at = datetime.now()
                    yield {
                        "event": "aborted",
                        "executionId": execution_id,
                        "completedTasks": i,
                        "totalTasks": total,
                        "timestamp": datetime.now().isoformat(),
                    }
                    break

                # Update state and yield task start event
                state.current_task_index = i
                state.current_task_key = task.get('key')

                yield {
                    "event": "task_start",
                    "executionId": execution_id,
                    "taskIndex": i,
                    "taskKey": task.get('key'),
                    "taskTitle": task.get('title'),
                    "totalTasks": total,
                    "progress": round(i / total * 100, 1),
                    "timestamp": datetime.now().isoformat(),
                }

                # Execute the task
                result = await self.execute_qa_task(
                    task, project_path, issue_context, db=db
                )
                results.append(result)

                # Update state
                state.completed_tasks = i + 1
                state.results.append(result)

                # Yield task completion event
                yield {
                    "event": "task_complete",
                    "executionId": execution_id,
                    "taskIndex": i,
                    "taskKey": task.get('key'),
                    "taskTitle": task.get('title'),
                    "status": result.get('status'),
                    "executionTime": result.get('executionTime'),
                    "error": result.get('error'),
                    "completedTasks": i + 1,
                    "totalTasks": total,
                    "progress": round((i + 1) / total * 100, 1),
                    "timestamp": datetime.now().isoformat(),
                }

            # Mark execution as completed
            if state.status == "running":
                state.status = "completed"
                state.ended_at = datetime.now()

                # Calculate summary
                passed = sum(1 for r in results if r.get('status') == 'PASS')
                failed = sum(1 for r in results if r.get('status') == 'FAILED')

                yield {
                    "event": "complete",
                    "executionId": execution_id,
                    "totalTasks": total,
                    "completedTasks": len(results),
                    "passedTasks": passed,
                    "failedTasks": failed,
                    "results": results,
                    "timestamp": datetime.now().isoformat(),
                }

        except Exception as e:
            logger.error(f"Error in streaming execution {execution_id}: {e}")
            state.status = "error"
            state.ended_at = datetime.now()
            yield {
                "event": "error",
                "executionId": execution_id,
                "error": str(e),
                "completedTasks": len(results),
                "totalTasks": total,
                "timestamp": datetime.now().isoformat(),
            }
        finally:
            # Clean up after delay
            asyncio.create_task(self._cleanup_execution(execution_id, delay=300))

    async def execute_qa_tasks_parallel(
        self,
        qa_tasks: List[Dict],
        project_path: str,
        issue_context: Optional[Dict] = None,
        max_concurrent: int = 5,
        db: Optional["AsyncSession"] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute QA tasks in parallel with concurrency limit.

        Args:
            qa_tasks: List of QA tasks to execute
            project_path: Path to the project
            issue_context: Optional context about the issue being tested
            max_concurrent: Maximum number of concurrent executions

        Returns:
            List of execution results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_with_limit(task):
            async with semaphore:
                return await self.execute_qa_task(
                    task, project_path, issue_context, db=db
                )

        tasks = [execute_with_limit(task) for task in qa_tasks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    'qaTaskId': qa_tasks[i].get('id'),
                    'key': qa_tasks[i].get('key'),
                    'status': 'FAILED',
                    'actualResult': None,
                    'executionTime': 0,
                    'error': str(result),
                })
            else:
                processed_results.append(result)

        return processed_results

    async def execute_qa_tasks_parallel_stream(
        self,
        qa_tasks: List[Dict],
        project_path: str,
        issue_context: Optional[Dict] = None,
        max_concurrent: int = 5,
        execution_id: Optional[str] = None,
        db: Optional["AsyncSession"] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute QA tasks in parallel with streaming progress updates.

        Tasks are executed concurrently up to max_concurrent at a time.
        Progress events are yielded as tasks start and complete (in completion order).

        Args:
            qa_tasks: List of QA tasks to execute
            project_path: Path to the project
            issue_context: Optional context about the issue being tested
            max_concurrent: Maximum number of concurrent executions
            execution_id: Optional execution ID for state tracking

        Yields:
            Progress events with task status updates
        """
        total = len(qa_tasks)
        if not execution_id:
            execution_id = str(uuid.uuid4())

        # Create execution state
        state = ExecutionState(execution_id, total)
        self._active_executions[execution_id] = state
        logger.info(f"Started streaming parallel execution {execution_id} with {total} tasks, max_concurrent={max_concurrent}")

        # Yield initial event
        yield {
            "event": "start",
            "executionId": execution_id,
            "totalTasks": total,
            "maxConcurrent": max_concurrent,
            "timestamp": datetime.now().isoformat(),
        }

        # Use a queue to collect events from parallel tasks
        event_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        semaphore = asyncio.Semaphore(max_concurrent)
        results: List[Dict[str, Any]] = []
        tasks_in_flight = 0
        tasks_started = 0

        async def execute_task_with_events(task: Dict, task_index: int):
            """Execute a single task and put events on the queue."""
            nonlocal tasks_in_flight

            # Check for abort before starting
            if state.abort_requested:
                return

            task_key = task.get('key')
            task_title = task.get('title')

            async with semaphore:
                # Check again after acquiring semaphore
                if state.abort_requested:
                    return

                tasks_in_flight += 1

                # Put task_start event on queue
                await event_queue.put({
                    "event": "task_start",
                    "executionId": execution_id,
                    "taskIndex": task_index,
                    "taskKey": task_key,
                    "taskTitle": task_title,
                    "totalTasks": total,
                    "tasksInFlight": tasks_in_flight,
                    "timestamp": datetime.now().isoformat(),
                })

                try:
                    result = await self.execute_qa_task(
                        task, project_path, issue_context, db=db
                    )
                except Exception as e:
                    result = {
                        'qaTaskId': task.get('id'),
                        'key': task_key,
                        'status': 'FAILED',
                        'actualResult': None,
                        'executionTime': 0,
                        'error': str(e),
                    }

                tasks_in_flight -= 1

                # Put task_complete event on queue
                await event_queue.put({
                    "event": "task_complete",
                    "executionId": execution_id,
                    "taskIndex": task_index,
                    "taskKey": task_key,
                    "taskTitle": task_title,
                    "status": result.get('status'),
                    "executionTime": result.get('executionTime'),
                    "error": result.get('error'),
                    "tasksInFlight": tasks_in_flight,
                    "totalTasks": total,
                    "timestamp": datetime.now().isoformat(),
                    "result": result,  # Include full result for processing
                })

        try:
            # Start all tasks (they'll be limited by semaphore)
            task_coroutines = [
                execute_task_with_events(task, i)
                for i, task in enumerate(qa_tasks)
            ]

            # Create background task to run all parallel executions
            async def run_all_tasks():
                await asyncio.gather(*task_coroutines, return_exceptions=True)
                # Signal completion by putting None on queue
                await event_queue.put(None)

            runner_task = asyncio.create_task(run_all_tasks())

            # Process events from the queue as they come in
            completed_count = 0
            while True:
                # Check for abort
                if state.abort_requested and not runner_task.done():
                    logger.info(f"Execution {execution_id} abort requested, waiting for in-flight tasks")

                try:
                    # Wait for next event with timeout to check abort status
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    # Check if runner is done (all tasks completed)
                    if runner_task.done():
                        break
                    continue

                if event is None:
                    # All tasks finished
                    break

                # Track task starts
                if event["event"] == "task_start":
                    tasks_started += 1
                    state.current_task_key = event["taskKey"]

                # Track completions and collect results
                if event["event"] == "task_complete":
                    completed_count += 1
                    result = event.pop("result", None)  # Remove from event before yielding
                    if result:
                        results.append(result)
                        state.results.append(result)
                    state.completed_tasks = completed_count

                    # Add progress to event
                    event["completedTasks"] = completed_count
                    event["progress"] = round(completed_count / total * 100, 1)

                yield event

            # Wait for runner to complete (should already be done)
            if not runner_task.done():
                await runner_task

            # Determine final status
            if state.abort_requested:
                state.status = "aborted"
                state.ended_at = datetime.now()
                yield {
                    "event": "aborted",
                    "executionId": execution_id,
                    "completedTasks": completed_count,
                    "totalTasks": total,
                    "timestamp": datetime.now().isoformat(),
                }
            else:
                state.status = "completed"
                state.ended_at = datetime.now()

                # Calculate summary
                passed = sum(1 for r in results if r.get('status') == 'PASS')
                failed = sum(1 for r in results if r.get('status') == 'FAILED')

                yield {
                    "event": "complete",
                    "executionId": execution_id,
                    "totalTasks": total,
                    "completedTasks": len(results),
                    "passedTasks": passed,
                    "failedTasks": failed,
                    "results": results,
                    "timestamp": datetime.now().isoformat(),
                }

        except Exception as e:
            logger.error(f"Error in parallel streaming execution {execution_id}: {e}")
            state.status = "error"
            state.ended_at = datetime.now()
            yield {
                "event": "error",
                "executionId": execution_id,
                "error": str(e),
                "completedTasks": len(results),
                "totalTasks": total,
                "timestamp": datetime.now().isoformat(),
            }
        finally:
            # Clean up after delay
            asyncio.create_task(self._cleanup_execution(execution_id, delay=300))

    def calculate_summary(
        self,
        qa_tasks: List[Dict],
        threshold: float = 0.9,
    ) -> Dict[str, Any]:
        """
        Calculate QA summary statistics.

        Args:
            qa_tasks: List of QA tasks with status
            threshold: Pass rate threshold (0.0 to 1.0)

        Returns:
            Summary statistics
        """
        total = len(qa_tasks)
        if total == 0:
            return {
                'totalTasks': 0,
                'passedTasks': 0,
                'failedTasks': 0,
                'notDoneTasks': 0,
                'inProgressTasks': 0,
                'passRate': 0.0,
                'isPassingThreshold': False,
            }

        passed = sum(1 for t in qa_tasks if t.get('status') == 'PASS')
        failed = sum(1 for t in qa_tasks if t.get('status') == 'FAILED')
        not_done = sum(1 for t in qa_tasks if t.get('status') == 'NOT_DONE')
        in_progress = sum(1 for t in qa_tasks if t.get('status') == 'IN_PROGRESS')

        # Calculate pass rate from completed tests only
        completed = passed + failed
        pass_rate = passed / completed if completed > 0 else 0.0

        return {
            'totalTasks': total,
            'passedTasks': passed,
            'failedTasks': failed,
            'notDoneTasks': not_done,
            'inProgressTasks': in_progress,
            'passRate': round(pass_rate, 4),
            'isPassingThreshold': pass_rate >= threshold,
        }

    def add_execution_to_history(
        self,
        current_history: Optional[str],
        execution_result: Dict,
    ) -> str:
        """
        Add an execution result to the history, keeping only last N entries.

        Args:
            current_history: Current history JSON string
            execution_result: New execution result to add

        Returns:
            Updated history JSON string
        """
        try:
            history = json.loads(current_history) if current_history else []
        except json.JSONDecodeError:
            history = []

        # Create history entry
        entry = {
            'id': str(uuid.uuid4())[:8],
            'timestamp': datetime.now().isoformat(),
            'status': execution_result.get('status'),
            'actualResult': execution_result.get('actualResult'),
            'executionTime': execution_result.get('executionTime'),
            'error': execution_result.get('error'),
        }

        # Add to front of list
        history.insert(0, entry)

        # Keep only last N entries with full details
        if len(history) > self.max_history_entries:
            # Summarize older entries
            older = history[self.max_history_entries:]
            history = history[:self.max_history_entries]

            # Add summary of older runs
            if older:
                pass_count = sum(1 for e in older if e.get('status') == 'PASS')
                fail_count = sum(1 for e in older if e.get('status') == 'FAILED')
                history.append({
                    'summary': True,
                    'olderRuns': len(older),
                    'passCount': pass_count,
                    'failCount': fail_count,
                })

        return json.dumps(history)

    def build_bug_description(
        self,
        qa_task: Dict,
        issue: Optional[Dict] = None,
    ) -> str:
        """
        Build a bug issue description from a failed QA task.

        Args:
            qa_task: The failed QA task
            issue: The original issue being tested

        Returns:
            Formatted bug description
        """
        description = f"""## Bug from Failed QA Test

### QA Task
- **Key**: {qa_task.get('key')}
- **Title**: {qa_task.get('title')}

### Test Scenario
{qa_task.get('scenario', 'No scenario provided')}

### Expected Result
{qa_task.get('expectedResult', 'No expected result provided')}

### Actual Result
{qa_task.get('actualResult', 'No actual result recorded')}

"""

        if issue:
            description += f"""### Original Issue
- **Key**: {issue.get('key')}
- **Title**: {issue.get('title')}
- **Type**: {issue.get('type')}

"""

        description += """### Steps to Reproduce
1. Follow the test scenario steps above
2. Observe the actual result differs from expected

### Environment
- Detected during automated QA execution
"""

        return description


# Singleton instance
qa_service = QAService()
