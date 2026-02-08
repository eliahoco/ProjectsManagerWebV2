# V3 Agent Detailed Specifications

## Purpose

This document provides exhaustive detail on each agent's:
- Specific skills and capabilities
- Decision-making logic
- Input/output specifications
- Prompt templates
- Quality criteria
- Error handling

---

## Table of Contents

1. [Agent Skill Matrix](#agent-skill-matrix)
2. [Orchestration Agent](#o-1-system-orchestrator)
3. [Strategic Agents](#strategic-agents)
4. [Coordination Agents](#coordination-agents)
5. [Implementation Agents](#implementation-agents)
6. [Testing Agents](#testing-agents)
7. [Review Agents](#review-agents)
8. [Skill Definitions](#skill-definitions)

---

## Agent Skill Matrix

### Skills by Agent

| Agent | Primary Skills | Secondary Skills | Tools Used |
|-------|---------------|------------------|------------|
| **O-1 Orchestrator** | workflow_create, agent_assign, priority_manage, escalate | monitor, report | Queue, State, Timer |
| **S-1 Solution Architect** | design_system, select_tech, create_adr, risk_assess | diagram, estimate | RAG, Mermaid, Templates |
| **S-2 Project Manager** | breakdown_epic, breakdown_story, estimate, dependency_map | prioritize, track | CodeBoard API, Templates |
| **S-3 Security Architect** | threat_model, security_review, auth_design, compliance_check | pentest_plan | STRIDE, OWASP, Templates |
| **S-4 DevOps Architect** | pipeline_design, infra_design, deploy_plan, monitor_design | cost_estimate | Docker, K8s, CI Templates |
| **C-1 Tech Lead** | task_refine, code_guide, pattern_select, blocker_resolve | mentor, coordinate | Codebase, Patterns DB |
| **C-2 QA Lead** | test_strategy, coverage_plan, risk_test, qa_assign | defect_triage | Test Frameworks, Coverage |
| **C-3 API Design Lead** | openapi_design, contract_define, versioning, mock_create | doc_api | OpenAPI, Swagger |
| **C-4 Documentation Lead** | doc_plan, doc_review, template_create, style_enforce | publish | Markdown, Docusaurus |
| **I-1 Frontend Engineer** | component_create, page_create, hook_create, style_create | refactor, optimize | React, Next.js, Tailwind |
| **I-2 Backend Engineer** | endpoint_create, service_create, validation_create | refactor, optimize | FastAPI, Python |
| **I-3 Database Engineer** | schema_design, migration_create, query_optimize, index_create | backup_plan | Prisma, SQLAlchemy |
| **I-4 API Engineer** | route_implement, middleware_create, auth_implement | rate_limit | FastAPI, Express |
| **I-5 Auth Engineer** | auth_flow, session_manage, token_manage, permission_create | mfa_implement | JWT, OAuth, Sessions |
| **I-6 UI/UX Engineer** | animation_create, responsive_design, theme_create, a11y_implement | prototype | CSS, Framer Motion |
| **T-1 Unit Test** | unit_test_create, mock_create, fixture_create | coverage_report | Jest, pytest |
| **T-2 Integration Test** | integration_test_create, api_test_create | env_setup | Supertest, pytest |
| **T-3 E2E Test** | e2e_test_create, flow_test_create | visual_test | Playwright, Cypress |
| **T-4 Security Test** | vulnerability_scan, pentest_execute, security_audit | report_create | OWASP ZAP, Semgrep |
| **T-5 Performance Test** | load_test_create, stress_test, profile_analyze | bottleneck_find | k6, Locust |
| **T-6 Accessibility Test** | a11y_audit, wcag_check, screen_reader_test | fix_suggest | axe, Lighthouse |
| **R-1 Code Reviewer** | code_review, style_check, pattern_check, security_check | suggest_improve | ESLint, Ruff, Patterns |
| **R-2 Security Reviewer** | security_review, vulnerability_check, auth_review | compliance_check | SAST, Dependency Check |
| **R-3 Performance Reviewer** | perf_review, complexity_check, resource_check | optimize_suggest | Profilers, Metrics |
| **R-4 Final Approver** | final_review, gate_check, approve, reject | escalate | All Reviews |

---

## O-1: System Orchestrator

### Agent Overview

```yaml
agent_id: O-1
name: System Orchestrator
layer: orchestration
criticality: highest
autonomy_level: high

purpose: |
  Central coordinator that receives feature requests, creates workflows,
  assigns work to agents, monitors progress, and handles exceptions.
  The brain of the multi-agent system.
```

### Skills Detail

#### Skill: workflow_create

```yaml
skill_id: O1-S1
name: workflow_create
description: Create a complete workflow from a feature request

inputs:
  feature_request:
    type: object
    required: true
    schema:
      title: string
      description: string
      priority: enum[CRITICAL, HIGH, MEDIUM, LOW]
      constraints: object
      deadline: datetime | null

  context:
    type: object
    required: false
    schema:
      project_id: string
      existing_architecture: object
      tech_stack: array[string]

outputs:
  workflow:
    type: object
    schema:
      id: string
      name: string
      stages: array[Stage]
      dependencies: array[Dependency]
      estimated_duration: duration
      assigned_agents: array[AgentAssignment]

decision_logic:
  1_analyze_request:
    action: Parse feature request
    extract:
      - Feature type (new, enhancement, fix)
      - Scope (small, medium, large)
      - Domain areas (frontend, backend, database, etc.)
      - Risk level

  2_determine_workflow_type:
    conditions:
      - IF scope == small AND risk == low:
          workflow: simple_implementation
          stages: [design_quick, implement, test, review]

      - IF scope == medium:
          workflow: standard_implementation
          stages: [architecture, design, implement, test, review, approve]

      - IF scope == large OR risk == high:
          workflow: full_implementation
          stages: [architecture, security_review, design, implement, test, security_test, review, approve]

  3_create_stages:
    for_each_stage:
      - Identify required agents
      - Define stage inputs/outputs
      - Set quality gates
      - Define timeout

  4_map_dependencies:
    action: Create dependency graph
    rules:
      - Architecture before Design
      - Design before Implementation
      - Implementation before Test
      - Test before Review
      - Parallel where independent

  5_estimate_duration:
    method: Sum of stage estimates + 20% buffer
    factors:
      - Historical data for similar features
      - Agent availability
      - Dependency chains

prompt_template: |
  You are the System Orchestrator. Analyze this feature request and create a workflow.

  ## Feature Request
  Title: {title}
  Description: {description}
  Priority: {priority}
  Constraints: {constraints}

  ## Project Context
  {context}

  ## Your Task
  Create a workflow with:
  1. Appropriate stages for this feature's scope and risk
  2. Agent assignments for each stage
  3. Dependencies between stages
  4. Time estimates

  ## Output Format
  Return a JSON object with:
  ```json
  {
    "workflow_type": "simple|standard|full",
    "stages": [
      {
        "id": "stage_1",
        "name": "Stage Name",
        "agents": ["S-1", "S-3"],
        "inputs": ["feature_request"],
        "outputs": ["architecture_doc"],
        "quality_gate": "G1_architecture_review",
        "timeout_hours": 4,
        "depends_on": []
      }
    ],
    "estimated_hours": 24,
    "risk_assessment": "low|medium|high",
    "notes": "Any special considerations"
  }
  ```

error_handling:
  invalid_request:
    action: Return validation errors
    escalate: false

  ambiguous_scope:
    action: Request clarification via QUESTION message
    escalate: after 2 attempts

  no_available_agents:
    action: Queue workflow, notify orchestrator
    escalate: if wait > 1 hour

quality_criteria:
  - All required stages present
  - No circular dependencies
  - All agents exist and are appropriate
  - Estimates are reasonable (within 2x historical)
  - Quality gates assigned to high-risk stages
```

#### Skill: agent_assign

```yaml
skill_id: O1-S2
name: agent_assign
description: Assign the optimal agent for a task

inputs:
  task:
    type: object
    schema:
      id: string
      type: enum[architecture, design, implementation, test, review]
      domain: enum[frontend, backend, database, security, devops, qa]
      complexity: enum[low, medium, high]
      requirements: array[string]

  available_agents:
    type: array[Agent]

outputs:
  assignment:
    type: object
    schema:
      agent_id: string
      confidence: float
      reasoning: string
      backup_agent_id: string

decision_logic:
  1_filter_capable:
    action: Filter agents that can handle task type + domain
    result: candidate_list

  2_score_candidates:
    for_each_candidate:
      factors:
        skill_match:
          weight: 0.3
          calculation: overlap(agent.skills, task.requirements) / len(task.requirements)

        historical_success:
          weight: 0.25
          calculation: agent.success_rate_for_type[task.type]

        current_load:
          weight: 0.2
          calculation: 1 - (agent.active_tasks / agent.max_concurrent)

        recent_performance:
          weight: 0.15
          calculation: agent.avg_quality_last_10_tasks / 100

        domain_expertise:
          weight: 0.1
          calculation: agent.domain_scores[task.domain]

  3_select_best:
    action: Select highest scoring candidate
    threshold: score >= 0.6
    fallback: escalate if no candidate meets threshold

  4_assign_backup:
    action: Select second-best as backup
    purpose: Failover if primary fails

prompt_template: |
  You are assigning an agent to this task.

  ## Task
  {task}

  ## Available Agents
  {agents_with_scores}

  ## Selection Criteria
  - Skill match with task requirements
  - Historical success rate for this task type
  - Current workload
  - Recent performance scores
  - Domain expertise

  Select the best agent and provide reasoning.

quality_criteria:
  - Selected agent has required skills
  - Load is manageable
  - Backup is different from primary
  - Reasoning is documented
```

#### Skill: escalate

```yaml
skill_id: O1-S3
name: escalate
description: Escalate issues to appropriate level

inputs:
  issue:
    type: object
    schema:
      type: enum[blocker, failure, timeout, quality, resource]
      source_agent: string
      task_id: string
      description: string
      attempts: integer
      context: object

outputs:
  escalation:
    type: object
    schema:
      level: enum[coordination, strategic, human]
      target: string
      message: string
      priority: enum[CRITICAL, HIGH, MEDIUM]
      action_required: string

decision_logic:
  1_classify_issue:
    blocker:
      - Missing dependency → escalate to provider
      - Unclear requirements → escalate to PM
      - Technical question → escalate to Tech Lead

    failure:
      - First failure → retry
      - Second failure → escalate to coordinator
      - Third failure → escalate to strategic

    timeout:
      - < 2x estimate → extend
      - >= 2x estimate → escalate to coordinator
      - >= 4x estimate → escalate to human

    quality:
      - Minor issues → return to agent
      - Major issues → escalate to coordinator
      - Critical issues → escalate to strategic

  2_determine_target:
    coordination_level:
      targets: [C-1, C-2, C-3, C-4]
      for: Technical blockers, resource issues

    strategic_level:
      targets: [S-1, S-2, S-3, S-4]
      for: Architecture issues, major scope changes

    human_level:
      targets: [human_operator]
      for: Unresolvable issues, policy decisions

  3_compose_message:
    include:
      - Issue summary
      - Context (what was attempted)
      - Impact (what's blocked)
      - Recommended action
      - Urgency

prompt_template: |
  An issue requires escalation.

  ## Issue Details
  Type: {type}
  Source Agent: {source_agent}
  Task: {task_id}
  Description: {description}
  Attempts Made: {attempts}

  ## Context
  {context}

  ## Determine
  1. What level should this escalate to?
  2. Who specifically should handle it?
  3. What action do they need to take?
  4. What's the priority?

  Provide escalation decision with reasoning.
```

---

## Strategic Agents

### S-1: Solution Architect

#### Agent Overview

```yaml
agent_id: S-1
name: Solution Architect
layer: strategic
criticality: high
autonomy_level: medium

purpose: |
  Design system architecture, make technology decisions,
  create integration patterns, and document architectural decisions.
  Ensures the system is scalable, maintainable, and aligned with requirements.
```

#### Skills Detail

##### Skill: design_system

```yaml
skill_id: S1-S1
name: design_system
description: Create complete system architecture for a feature

inputs:
  feature:
    title: string
    description: string
    requirements:
      functional: array[string]
      non_functional: array[string]

  constraints:
    tech_stack: array[string]
    budget: string
    timeline: string
    team_skills: array[string]

  existing_system:
    components: array[Component]
    integrations: array[Integration]
    data_model: object

outputs:
  architecture:
    overview: string
    components: array[ComponentSpec]
    data_flow: MermaidDiagram
    integrations: array[IntegrationSpec]
    apis: array[APISpec]
    data_model_changes: array[ModelChange]
    deployment: DeploymentSpec

decision_logic:
  1_analyze_requirements:
    extract:
      - Core functionality needed
      - Data entities involved
      - User interactions
      - External integrations
      - Performance requirements
      - Security requirements

  2_identify_components:
    for_each_functionality:
      determine:
        - Which layer (UI, API, Service, Data)
        - New component or extend existing
        - Boundaries and responsibilities

  3_design_data_flow:
    map:
      - User actions to UI components
      - UI to API calls
      - API to service operations
      - Service to data operations
    document:
      - Synchronous flows
      - Asynchronous flows
      - Event flows

  4_define_apis:
    for_each_integration_point:
      specify:
        - Endpoint path
        - HTTP method
        - Request schema
        - Response schema
        - Error responses
        - Authentication

  5_plan_data_model:
    identify:
      - New entities
      - Modified entities
      - Relationships
      - Indexes needed
      - Migration path

  6_consider_non_functional:
    address:
      - Scalability approach
      - Caching strategy
      - Error handling
      - Logging/monitoring
      - Security measures

prompt_template: |
  You are the Solution Architect. Design the system architecture for this feature.

  ## Feature
  **Title**: {title}
  **Description**: {description}

  ## Requirements
  ### Functional
  {functional_requirements}

  ### Non-Functional
  {non_functional_requirements}

  ## Constraints
  - Tech Stack: {tech_stack}
  - Timeline: {timeline}
  - Team Skills: {team_skills}

  ## Existing System
  {existing_system_summary}

  ## Your Task
  Design a complete architecture that includes:

  1. **Component Overview**
     - List all components (new and modified)
     - Define responsibilities
     - Specify interfaces

  2. **Data Flow Diagram**
     - Mermaid diagram showing data flow
     - Cover all user interactions

  3. **API Specifications**
     - All new/modified endpoints
     - Request/response schemas

  4. **Data Model Changes**
     - New entities
     - Modified entities
     - Relationships

  5. **Integration Points**
     - External services
     - Internal service calls

  6. **Non-Functional Considerations**
     - Scalability
     - Security
     - Performance

  ## Output Format
  Provide a structured architecture document with Mermaid diagrams.

quality_criteria:
  completeness:
    - All requirements addressed
    - All components defined
    - All integrations specified
    - Data model complete

  consistency:
    - Naming conventions followed
    - Patterns match existing system
    - No contradictions

  feasibility:
    - Within tech stack constraints
    - Reasonable complexity
    - Achievable timeline

  quality:
    - Scalable design
    - Secure by design
    - Maintainable structure
```

##### Skill: create_adr

```yaml
skill_id: S1-S2
name: create_adr
description: Create Architecture Decision Record

inputs:
  decision:
    title: string
    context: string
    options_considered: array[Option]
    chosen_option: string
    reasoning: string

outputs:
  adr:
    type: markdown
    sections:
      - Title
      - Status
      - Context
      - Decision
      - Options Considered
      - Consequences
      - References

template: |
  # ADR-{number}: {title}

  ## Status
  {status: Proposed | Accepted | Deprecated | Superseded}

  ## Context
  {context_description}

  ## Decision
  We will {decision_statement}.

  ## Options Considered

  ### Option 1: {option_1_name}
  **Description**: {description}
  **Pros**:
  - {pro_1}
  - {pro_2}
  **Cons**:
  - {con_1}
  - {con_2}

  ### Option 2: {option_2_name}
  ...

  ## Consequences

  ### Positive
  - {positive_1}
  - {positive_2}

  ### Negative
  - {negative_1}
  - {negative_2}

  ### Risks
  - {risk_1}
  - {risk_2}

  ## References
  - {reference_1}
  - {reference_2}

prompt_template: |
  Create an Architecture Decision Record for:

  ## Decision Context
  {context}

  ## Options to Consider
  {options}

  ## Constraints
  {constraints}

  Document this decision following the ADR template, including:
  1. Clear context explaining why this decision is needed
  2. All options with honest pros/cons
  3. The recommended decision with reasoning
  4. Consequences (positive, negative, risks)

  Be objective and thorough.
```

##### Skill: risk_assess

```yaml
skill_id: S1-S3
name: risk_assess
description: Assess technical risks in architecture

inputs:
  architecture: ArchitectureDoc
  requirements: Requirements

outputs:
  risk_assessment:
    risks: array[Risk]
    overall_risk_level: enum[LOW, MEDIUM, HIGH, CRITICAL]
    mitigations: array[Mitigation]
    recommendations: array[string]

risk_categories:
  technical:
    - New technology adoption
    - Integration complexity
    - Performance uncertainty
    - Scalability concerns

  operational:
    - Deployment complexity
    - Monitoring gaps
    - Recovery procedures

  security:
    - Attack surface
    - Data exposure
    - Authentication gaps

  resource:
    - Skill gaps
    - Time constraints
    - Dependency availability

risk_matrix:
  likelihood: [RARE, UNLIKELY, POSSIBLE, LIKELY, CERTAIN]
  impact: [NEGLIGIBLE, MINOR, MODERATE, MAJOR, SEVERE]

  scoring:
    CRITICAL: likelihood >= LIKELY AND impact >= MAJOR
    HIGH: likelihood >= POSSIBLE AND impact >= MODERATE
    MEDIUM: likelihood >= UNLIKELY AND impact >= MINOR
    LOW: everything else

prompt_template: |
  Assess the technical risks in this architecture.

  ## Architecture
  {architecture}

  ## Requirements
  {requirements}

  ## Risk Categories to Evaluate
  1. Technical Risks
  2. Operational Risks
  3. Security Risks
  4. Resource Risks

  For each risk identified:
  - Description
  - Category
  - Likelihood (RARE to CERTAIN)
  - Impact (NEGLIGIBLE to SEVERE)
  - Risk Level (calculated)
  - Mitigation strategy
  - Residual risk after mitigation

  Provide overall risk level and recommendations.
```

---

### S-2: Project Manager

#### Agent Overview

```yaml
agent_id: S-2
name: Project Manager
layer: strategic
criticality: high
autonomy_level: medium

purpose: |
  Break down features into manageable work items, create hierarchical
  task structures, estimate effort, identify dependencies, and track progress.
```

#### Skills Detail

##### Skill: breakdown_epic

```yaml
skill_id: S2-S1
name: breakdown_epic
description: Break down a feature into Epic with Stories

inputs:
  feature:
    title: string
    description: string
    architecture: ArchitectureDoc

outputs:
  epic:
    title: string
    description: string
    acceptance_criteria: array[string]
    stories: array[Story]
    total_points: integer
    estimated_duration: string

decision_logic:
  1_identify_user_capabilities:
    analyze:
      - What can users DO with this feature?
      - What are the distinct user journeys?
      - What are the permission levels?
    output: list of user capabilities

  2_group_into_stories:
    rules:
      - Each story = one user capability
      - Story should be deliverable independently (as much as possible)
      - Story should be testable
      - Story should have clear value

  3_order_stories:
    criteria:
      - Dependencies (foundational first)
      - Risk (high risk early)
      - Value (high value early)

  4_estimate_epic:
    method: Sum of story points + 15% coordination overhead

story_format:
  title: "User can {action} so that {benefit}"
  description: |
    ## Overview
    {what this story delivers}

    ## User Journey
    1. {step 1}
    2. {step 2}
    ...

    ## Acceptance Criteria
    - Given {context}, When {action}, Then {result}
    - ...

  story_points: fibonacci[1, 2, 3, 5, 8, 13]

prompt_template: |
  Break down this feature into an Epic with Stories.

  ## Feature
  **Title**: {title}
  **Description**: {description}

  ## Architecture
  {architecture_summary}

  ## Your Task

  1. **Create Epic**
     - Clear title
     - Comprehensive description
     - High-level acceptance criteria

  2. **Identify Stories**
     For each distinct user capability:
     - Title: "User can {action} so that {benefit}"
     - Description with user journey
     - Acceptance criteria (Given/When/Then)
     - Story points estimate
     - Dependencies on other stories

  3. **Order Stories**
     - Consider dependencies
     - Consider risk
     - Consider value

  ## Output Format
  ```json
  {
    "epic": {
      "title": "...",
      "description": "...",
      "acceptance_criteria": ["..."]
    },
    "stories": [
      {
        "id": "S1",
        "title": "User can ...",
        "description": "...",
        "acceptance_criteria": ["Given..., When..., Then..."],
        "story_points": 5,
        "depends_on": [],
        "priority": "HIGH"
      }
    ],
    "total_points": 21,
    "recommended_order": ["S1", "S2", "S3"]
  }
  ```

quality_criteria:
  - All user capabilities covered
  - Stories are independent where possible
  - Acceptance criteria are testable
  - Estimates are reasonable
  - Dependencies are identified
```

##### Skill: breakdown_story

```yaml
skill_id: S2-S2
name: breakdown_story
description: Break down a Story into Tasks and Subtasks

inputs:
  story:
    title: string
    description: string
    acceptance_criteria: array[string]
    architecture: ArchitectureDoc

outputs:
  tasks: array[Task]

decision_logic:
  1_identify_work_areas:
    from_architecture:
      - Frontend components needed
      - Backend endpoints needed
      - Database changes needed
      - Integration work needed
      - Configuration needed

  2_create_tasks:
    rules:
      - One task = one assignable unit of work
      - Task should take 2-8 hours
      - Task should be specific and actionable
      - Task should have clear definition of done

  3_create_subtasks:
    rules:
      - Subtask = atomic action within task
      - Subtask should take 30min - 2 hours
      - Subtask should be checkable

  4_assign_to_specialists:
    mapping:
      frontend_component: I-1
      backend_endpoint: I-2
      database_change: I-3
      api_implementation: I-4
      auth_work: I-5
      styling_work: I-6

task_format:
  title: "{verb} {component} for {purpose}"
  description: |
    ## Objective
    {what to build}

    ## Implementation Details
    - {detail 1}
    - {detail 2}

    ## Definition of Done
    - [ ] {criterion 1}
    - [ ] {criterion 2}

  subtasks:
    - "{specific action 1}"
    - "{specific action 2}"

prompt_template: |
  Break down this Story into Tasks and Subtasks.

  ## Story
  **Title**: {title}
  **Description**: {description}
  **Acceptance Criteria**: {acceptance_criteria}

  ## Architecture Context
  {architecture_relevant_parts}

  ## Your Task

  1. **Identify Work Areas**
     - Frontend work
     - Backend work
     - Database work
     - Integration work

  2. **Create Tasks** (2-8 hours each)
     For each work area:
     - Specific, actionable title
     - Clear implementation details
     - Definition of done
     - Specialist assignment
     - Hour estimate

  3. **Create Subtasks** (30min - 2hrs each)
     For each task:
     - Atomic, checkable items
     - Ordered sequence

  ## Output Format
  ```json
  {
    "tasks": [
      {
        "id": "T1",
        "title": "Create UserProfile component",
        "description": "...",
        "specialist": "I-1",
        "estimated_hours": 4,
        "depends_on": [],
        "definition_of_done": ["...", "..."],
        "subtasks": [
          {"id": "ST1", "title": "Create component file", "hours": 0.5},
          {"id": "ST2", "title": "Implement props interface", "hours": 0.5},
          ...
        ]
      }
    ],
    "total_hours": 24,
    "critical_path": ["T1", "T3", "T5"]
  }
  ```

quality_criteria:
  - All acceptance criteria mapped to tasks
  - Tasks are appropriately sized (2-8 hours)
  - Subtasks are atomic
  - Specialists correctly assigned
  - Dependencies identified
  - Parallel work identified
```

##### Skill: dependency_map

```yaml
skill_id: S2-S3
name: dependency_map
description: Create dependency graph between work items

inputs:
  work_items: array[Epic | Story | Task]

outputs:
  dependency_graph:
    nodes: array[Node]
    edges: array[Edge]
    critical_path: array[string]
    parallel_groups: array[array[string]]

dependency_types:
  blocks:
    description: Item A must complete before B can start
    example: "Database schema must exist before API endpoint"

  informs:
    description: Item A provides information for B
    example: "API design informs frontend implementation"

  requires:
    description: Item A needs artifact from B
    example: "Frontend needs API endpoint URL"

analysis_logic:
  1_identify_dependencies:
    for_each_item:
      check:
        - Does this need output from another item?
        - Does this provide input to another item?
        - Does this share resources with another item?

  2_classify_dependencies:
    - Hard dependency (blocks)
    - Soft dependency (informs)
    - Resource dependency (shares)

  3_find_critical_path:
    algorithm: Longest path in DAG
    purpose: Identify minimum completion time

  4_find_parallel_groups:
    algorithm: Items with no dependencies between them
    purpose: Enable parallel execution

prompt_template: |
  Create a dependency map for these work items.

  ## Work Items
  {work_items}

  ## Your Task

  1. **Identify Dependencies**
     For each item, identify:
     - What it depends on (blocks)
     - What depends on it (blocked by)
     - Soft dependencies (informs)

  2. **Create Graph**
     - Nodes: work items
     - Edges: dependencies with type

  3. **Analyze**
     - Critical path (longest chain)
     - Parallel groups (can run simultaneously)
     - Bottlenecks

  ## Output Format
  ```json
  {
    "dependencies": [
      {"from": "T1", "to": "T2", "type": "blocks", "reason": "..."}
    ],
    "critical_path": ["T1", "T2", "T5"],
    "parallel_groups": [
      ["T1", "T3"],
      ["T2", "T4"]
    ],
    "bottlenecks": ["T2"],
    "minimum_duration_hours": 24
  }
  ```
```

---

### S-3: Security Architect

#### Skills Detail

##### Skill: threat_model

```yaml
skill_id: S3-S1
name: threat_model
description: Create STRIDE threat model for architecture

inputs:
  architecture: ArchitectureDoc
  data_classification: DataClassification
  user_roles: array[Role]

outputs:
  threat_model:
    assets: array[Asset]
    threat_actors: array[ThreatActor]
    threats: array[Threat]
    mitigations: array[Mitigation]
    residual_risks: array[Risk]

stride_categories:
  Spoofing:
    description: Pretending to be someone else
    examples:
      - Stolen credentials
      - Session hijacking
      - Token forgery
    common_mitigations:
      - Strong authentication
      - MFA
      - Session management

  Tampering:
    description: Modifying data or code
    examples:
      - SQL injection
      - Parameter tampering
      - Man-in-the-middle
    common_mitigations:
      - Input validation
      - Integrity checks
      - HTTPS

  Repudiation:
    description: Denying actions taken
    examples:
      - No audit trail
      - Log tampering
      - Anonymous actions
    common_mitigations:
      - Audit logging
      - Digital signatures
      - Timestamps

  Information_Disclosure:
    description: Exposing information
    examples:
      - Data leaks
      - Error messages
      - Insecure storage
    common_mitigations:
      - Encryption
      - Access control
      - Data masking

  Denial_of_Service:
    description: Making system unavailable
    examples:
      - Resource exhaustion
      - Algorithmic complexity
      - Distributed attacks
    common_mitigations:
      - Rate limiting
      - Input limits
      - Scaling

  Elevation_of_Privilege:
    description: Gaining unauthorized access
    examples:
      - Broken access control
      - Privilege escalation
      - Insecure defaults
    common_mitigations:
      - Principle of least privilege
      - Role-based access
      - Defense in depth

prompt_template: |
  Create a STRIDE threat model for this architecture.

  ## Architecture
  {architecture}

  ## Data Classification
  {data_classification}

  ## User Roles
  {user_roles}

  ## Your Task

  1. **Identify Assets**
     - Data assets (what needs protection)
     - System assets (components that process data)
     - Access points (entry points to system)

  2. **Identify Threat Actors**
     - External attackers
     - Malicious insiders
     - Accidental insiders

  3. **Apply STRIDE**
     For each component/data flow:
     - Spoofing threats
     - Tampering threats
     - Repudiation threats
     - Information Disclosure threats
     - Denial of Service threats
     - Elevation of Privilege threats

  4. **Define Mitigations**
     For each threat:
     - Mitigation strategy
     - Implementation requirement
     - Priority

  5. **Assess Residual Risk**
     After mitigations:
     - Remaining risks
     - Acceptance criteria

  ## Output Format
  Structured threat model document with:
  - Asset inventory
  - Threat catalog
  - Mitigation requirements
  - Risk matrix
```

##### Skill: auth_design

```yaml
skill_id: S3-S2
name: auth_design
description: Design authentication and authorization system

inputs:
  requirements:
    user_types: array[UserType]
    permissions: array[Permission]
    integrations: array[Integration]

outputs:
  auth_design:
    authentication:
      method: string
      flow: MermaidDiagram
      token_strategy: TokenStrategy
      session_management: SessionStrategy

    authorization:
      model: string
      roles: array[Role]
      permissions: array[Permission]
      policy: PolicyDefinition

auth_patterns:
  authentication:
    session_based:
      use_when: Traditional web apps
      components: [session_store, cookie_handler]

    jwt_based:
      use_when: APIs, SPAs
      components: [token_issuer, token_validator]

    oauth2:
      use_when: Third-party integration
      components: [oauth_client, callback_handler]

  authorization:
    rbac:
      use_when: Clear role hierarchy
      implementation: role_to_permissions_mapping

    abac:
      use_when: Complex, dynamic permissions
      implementation: attribute_policy_engine

    resource_based:
      use_when: Per-resource ownership
      implementation: resource_owner_check

prompt_template: |
  Design the authentication and authorization system.

  ## Requirements
  **User Types**: {user_types}
  **Permissions Needed**: {permissions}
  **Integrations**: {integrations}

  ## Your Task

  1. **Authentication Design**
     - Select authentication method
     - Design login flow
     - Define token/session strategy
     - Plan password policy
     - Consider MFA

  2. **Authorization Design**
     - Select authorization model (RBAC/ABAC)
     - Define roles
     - Map permissions to roles
     - Design permission checking

  3. **Security Considerations**
     - Token security
     - Session security
     - Password storage
     - Brute force protection

  4. **Implementation Requirements**
     - Components needed
     - APIs needed
     - Storage needed

  ## Output Format
  Comprehensive auth design document with diagrams.
```

---

## Implementation Agents

### I-1: Frontend Engineer

#### Skills Detail

##### Skill: component_create

```yaml
skill_id: I1-S1
name: component_create
description: Create a React component

inputs:
  specification:
    name: string
    purpose: string
    props: array[PropDef]
    state: array[StateDef]
    behavior: array[BehaviorDef]
    styling: StylingReq

  context:
    existing_components: array[Component]
    design_system: DesignSystem
    patterns: array[Pattern]

outputs:
  component:
    file_path: string
    code: string
    types: string
    tests: string
    storybook: string

implementation_patterns:
  component_structure:
    order:
      1. Imports
      2. Types/Interfaces
      3. Component function
      4. Hooks
      5. Event handlers
      6. Effects
      7. Render logic
      8. Export

  state_management:
    local: "useState for component-local state"
    derived: "useMemo for computed values"
    server: "useQuery for server data"
    form: "useForm for form state"

  styling:
    approach: "Tailwind classes"
    responsive: "Mobile-first"
    variants: "cn() utility for conditional classes"

code_standards:
  typescript:
    - Explicit prop types
    - No any types
    - Proper generics where needed

  react:
    - Functional components only
    - Custom hooks for shared logic
    - Proper dependency arrays

  accessibility:
    - Semantic HTML
    - ARIA labels where needed
    - Keyboard navigation

prompt_template: |
  Create a React component based on this specification.

  ## Component Specification
  **Name**: {name}
  **Purpose**: {purpose}

  ## Props
  {props_specification}

  ## State
  {state_specification}

  ## Behavior
  {behavior_specification}

  ## Styling Requirements
  {styling_requirements}

  ## Existing Context
  **Related Components**: {existing_components}
  **Design System**: {design_system}

  ## Your Task
  Create a complete React component including:

  1. **Component File** (`{name}.tsx`)
     - TypeScript with proper types
     - All props implemented
     - State management
     - Event handlers
     - Loading/error states
     - Responsive design
     - Accessibility

  2. **Types** (if complex, separate file)
     - Props interface
     - State types
     - Event types

  ## Code Standards
  - Use TypeScript strict mode
  - Use Tailwind for styling
  - Use shadcn/ui components where applicable
  - Follow existing patterns in codebase

  ## Output Format
  ```typescript
  // {name}.tsx
  {component_code}
  ```

quality_checklist:
  - [ ] Props interface defined
  - [ ] All props used
  - [ ] Loading state handled
  - [ ] Error state handled
  - [ ] Responsive design
  - [ ] Accessibility attributes
  - [ ] No console.log
  - [ ] Proper TypeScript types
  - [ ] Event handlers typed
  - [ ] useCallback for handlers passed to children
  - [ ] useMemo for expensive computations
```

##### Skill: hook_create

```yaml
skill_id: I1-S2
name: hook_create
description: Create a custom React hook

inputs:
  specification:
    name: string
    purpose: string
    inputs: array[InputDef]
    outputs: array[OutputDef]
    side_effects: array[SideEffect]

outputs:
  hook:
    file_path: string
    code: string
    types: string
    tests: string

hook_patterns:
  data_fetching:
    pattern: "useQuery wrapper"
    structure: |
      export function use{Resource}() {
        return useQuery({
          queryKey: ['{resource}'],
          queryFn: fetch{Resource}
        });
      }

  form_handling:
    pattern: "useForm wrapper"
    structure: |
      export function use{Form}Form() {
        return useForm<{FormData}>({
          resolver: zodResolver({schema}),
          defaultValues: {...}
        });
      }

  state_machine:
    pattern: "useReducer wrapper"
    structure: |
      export function use{Feature}() {
        const [state, dispatch] = useReducer(reducer, initialState);
        // ... actions
        return { state, ...actions };
      }

prompt_template: |
  Create a custom React hook based on this specification.

  ## Hook Specification
  **Name**: use{name}
  **Purpose**: {purpose}

  ## Inputs
  {inputs}

  ## Expected Outputs
  {outputs}

  ## Side Effects
  {side_effects}

  ## Your Task
  Create a custom hook that:
  1. Follows React hooks rules
  2. Has proper TypeScript types
  3. Handles cleanup properly
  4. Is reusable and composable

  ## Output Format
  ```typescript
  // use{name}.ts
  {hook_code}
  ```
```

---

### I-2: Backend Engineer

#### Skills Detail

##### Skill: endpoint_create

```yaml
skill_id: I2-S1
name: endpoint_create
description: Create a FastAPI endpoint

inputs:
  specification:
    path: string
    method: enum[GET, POST, PUT, PATCH, DELETE]
    request_body: Schema | null
    response_body: Schema
    query_params: array[ParamDef]
    path_params: array[ParamDef]
    authentication: AuthRequirement
    authorization: array[Permission]

  context:
    existing_routes: array[Route]
    services: array[Service]
    models: array[Model]

outputs:
  endpoint:
    route_file: string
    route_code: string
    schemas: string
    tests: string

implementation_patterns:
  route_structure:
    order:
      1. Decorator with path and method
      2. Dependencies (auth, db, etc.)
      3. Request validation
      4. Business logic (via service)
      5. Response formatting
      6. Error handling

  response_patterns:
    success: Return Pydantic model
    created: Return model with 201 status
    no_content: Return None with 204
    error: Raise HTTPException

  dependency_injection:
    database: "db: AsyncSession = Depends(get_db)"
    auth: "user: User = Depends(get_current_user)"
    service: "service: MyService = Depends(get_service)"

code_standards:
  typing:
    - All parameters typed
    - Return type annotated
    - Pydantic for request/response

  async:
    - Use async def for I/O operations
    - Await all database calls
    - Use asyncio.gather for parallel

  errors:
    - HTTPException for API errors
    - Proper status codes
    - Informative error messages

prompt_template: |
  Create a FastAPI endpoint based on this specification.

  ## Endpoint Specification
  **Path**: {path}
  **Method**: {method}

  ## Request
  **Body**: {request_body}
  **Query Params**: {query_params}
  **Path Params**: {path_params}

  ## Response
  {response_body}

  ## Security
  **Authentication**: {authentication}
  **Authorization**: {authorization}

  ## Context
  **Existing Services**: {services}
  **Models**: {models}

  ## Your Task
  Create a complete endpoint including:

  1. **Route Handler**
     - Proper decorators
     - Type annotations
     - Dependency injection
     - Error handling

  2. **Pydantic Schemas**
     - Request schema
     - Response schema

  3. **Service Call**
     - Delegate to service layer
     - Handle service errors

  ## Code Standards
  - Use async/await
  - Type all parameters
  - Use Pydantic v2
  - Proper HTTP status codes

  ## Output Format
  ```python
  # route.py
  {route_code}

  # schemas.py
  {schema_code}
  ```

quality_checklist:
  - [ ] Path follows REST conventions
  - [ ] All params typed
  - [ ] Request validated
  - [ ] Response schema matches
  - [ ] Auth/authz implemented
  - [ ] Errors handled
  - [ ] Async where needed
  - [ ] Service layer used
```

##### Skill: service_create

```yaml
skill_id: I2-S2
name: service_create
description: Create a service class for business logic

inputs:
  specification:
    name: string
    purpose: string
    methods: array[MethodDef]
    dependencies: array[Dependency]

  context:
    models: array[Model]
    existing_services: array[Service]

outputs:
  service:
    file_path: string
    code: string
    tests: string

implementation_patterns:
  service_structure:
    pattern: |
      class {Name}Service:
          def __init__(self, db: AsyncSession):
              self.db = db

          async def {method}(self, ...) -> ...:
              # Implementation
              pass

  repository_pattern:
    pattern: |
      class {Name}Repository:
          # Data access only
          pass

      class {Name}Service:
          def __init__(self, repo: {Name}Repository):
              self.repo = repo
          # Business logic only

prompt_template: |
  Create a service class for business logic.

  ## Service Specification
  **Name**: {name}Service
  **Purpose**: {purpose}

  ## Methods
  {methods}

  ## Dependencies
  {dependencies}

  ## Context
  **Models**: {models}

  ## Your Task
  Create a service class that:
  1. Encapsulates business logic
  2. Uses repository for data access
  3. Handles transactions properly
  4. Raises appropriate exceptions

  ## Output Format
  ```python
  # {name}_service.py
  {service_code}
  ```
```

---

## Testing Agents

### T-1: Unit Test Engineer

#### Skills Detail

##### Skill: unit_test_create

```yaml
skill_id: T1-S1
name: unit_test_create
description: Create unit tests for a function/component

inputs:
  code:
    file_path: string
    content: string
    type: enum[function, component, class, hook]

  requirements:
    coverage_target: float
    edge_cases: array[string]
    mocks_needed: array[MockDef]

outputs:
  tests:
    file_path: string
    code: string
    coverage_report: CoverageReport

test_patterns:
  function:
    structure: |
      describe('{functionName}', () => {
        it('should {expected behavior} when {condition}', () => {
          // Arrange
          // Act
          // Assert
        });
      });

  component:
    structure: |
      describe('{ComponentName}', () => {
        it('renders correctly', () => {});
        it('handles {interaction}', () => {});
        it('displays {state} correctly', () => {});
      });

  hook:
    structure: |
      describe('use{HookName}', () => {
        it('returns initial state', () => {});
        it('updates state on {action}', () => {});
        it('handles errors', () => {});
      });

test_categories:
  happy_path:
    - Normal input → Expected output
    - Valid state transitions
    - Successful operations

  edge_cases:
    - Empty inputs
    - Boundary values
    - Maximum values
    - Unicode/special characters

  error_cases:
    - Invalid inputs
    - Network failures
    - Permission denied
    - Timeout

  integration_points:
    - Mock external dependencies
    - Verify API calls
    - Check side effects

prompt_template: |
  Create unit tests for this code.

  ## Code to Test
  **File**: {file_path}
  **Type**: {type}

  ```{language}
  {content}
  ```

  ## Requirements
  **Coverage Target**: {coverage_target}%
  **Edge Cases to Cover**: {edge_cases}
  **Mocks Needed**: {mocks_needed}

  ## Your Task
  Create comprehensive unit tests covering:

  1. **Happy Path Tests**
     - Normal usage scenarios
     - Expected outputs

  2. **Edge Case Tests**
     - Boundary conditions
     - Empty/null inputs
     - Maximum values

  3. **Error Case Tests**
     - Invalid inputs
     - Error handling

  4. **Mock Setup**
     - External dependencies
     - API calls

  ## Test Structure
  - Use Arrange-Act-Assert pattern
  - One assertion per test (when practical)
  - Descriptive test names
  - Proper cleanup

  ## Output Format
  ```{test_language}
  // {test_file_path}
  {test_code}
  ```

quality_checklist:
  - [ ] All public functions tested
  - [ ] Happy path covered
  - [ ] Edge cases covered
  - [ ] Error cases covered
  - [ ] Mocks properly isolated
  - [ ] Tests are independent
  - [ ] No test interdependencies
  - [ ] Cleanup in afterEach/finally
```

---

## Review Agents

### R-1: Code Reviewer

#### Skills Detail

##### Skill: code_review

```yaml
skill_id: R1-S1
name: code_review
description: Comprehensive code review

inputs:
  code_diff:
    files: array[FileDiff]
    context: string

  standards:
    style_guide: StyleGuide
    patterns: array[Pattern]
    security_rules: array[SecurityRule]

outputs:
  review:
    status: enum[APPROVED, CHANGES_REQUESTED, COMMENTED]
    comments: array[ReviewComment]
    summary: string
    blocking_issues: array[Issue]
    suggestions: array[Suggestion]

review_categories:
  critical:
    severity: blocking
    examples:
      - Security vulnerabilities
      - Data loss risks
      - Breaking changes without migration
      - Race conditions
      - Memory leaks

  major:
    severity: should_fix
    examples:
      - Missing error handling
      - Performance issues
      - Poor abstractions
      - Missing validation
      - Incorrect types

  minor:
    severity: nice_to_fix
    examples:
      - Code style issues
      - Naming improvements
      - Missing comments
      - Redundant code

  suggestion:
    severity: optional
    examples:
      - Refactoring opportunities
      - Alternative approaches
      - Future improvements

review_checklist:
  functionality:
    - Requirements satisfied
    - Edge cases handled
    - Error states handled
    - Backwards compatible

  code_quality:
    - Readable and maintainable
    - DRY principle
    - Single responsibility
    - Appropriate abstraction

  security:
    - Input validation
    - Output encoding
    - Authentication checks
    - Authorization checks
    - No secrets in code

  performance:
    - Efficient algorithms
    - No unnecessary operations
    - Proper caching
    - Database query efficiency

  testing:
    - Unit tests included
    - Edge cases tested
    - Mocks appropriate

prompt_template: |
  Review this code change.

  ## Code Diff
  {code_diff}

  ## Context
  {context}

  ## Standards
  **Style Guide**: {style_guide}
  **Required Patterns**: {patterns}

  ## Your Task
  Perform a thorough code review:

  1. **Functionality Review**
     - Does it meet requirements?
     - Are edge cases handled?
     - Is error handling proper?

  2. **Code Quality Review**
     - Is it readable?
     - Is it maintainable?
     - Are abstractions appropriate?

  3. **Security Review**
     - Input validation?
     - Authentication/authorization?
     - No vulnerabilities?

  4. **Performance Review**
     - Efficient implementation?
     - No unnecessary operations?

  5. **Testing Review**
     - Adequate test coverage?
     - Quality of tests?

  ## Comment Format
  For each issue:
  - File and line number
  - Severity: CRITICAL | MAJOR | MINOR | SUGGESTION
  - Description of issue
  - Suggested fix
  - Code example if helpful

  ## Decision
  - APPROVED: No blocking issues
  - CHANGES_REQUESTED: Has critical/major issues
  - COMMENTED: Only minor issues/suggestions

  ## Output Format
  ```json
  {
    "status": "CHANGES_REQUESTED",
    "summary": "...",
    "comments": [
      {
        "file": "path/to/file.ts",
        "line": 42,
        "severity": "MAJOR",
        "issue": "Missing null check",
        "suggestion": "Add null check before accessing property",
        "example": "if (user?.name) { ... }"
      }
    ],
    "blocking_issues": ["..."],
    "suggestions": ["..."]
  }
  ```
```

---

## Skill Definitions

### Reusable Skills (Available to Multiple Agents)

```yaml
skills:
  read_file:
    description: Read file contents
    available_to: [all]
    inputs: [file_path]
    outputs: [content, metadata]

  write_file:
    description: Write file contents
    available_to: [implementation_agents]
    inputs: [file_path, content]
    outputs: [success, error]

  search_codebase:
    description: Search for patterns in codebase
    available_to: [all]
    inputs: [pattern, file_types, path]
    outputs: [matches]

  run_command:
    description: Execute shell command
    available_to: [orchestrator, devops, test_agents]
    inputs: [command, cwd, timeout]
    outputs: [stdout, stderr, exit_code]

  query_rag:
    description: Query RAG for context
    available_to: [all]
    inputs: [query, project_id, n_results]
    outputs: [documents, scores]

  create_issue:
    description: Create CodeBoard issue
    available_to: [S-2, C-1, C-2, R-1]
    inputs: [title, description, type, priority, parent_id]
    outputs: [issue_id, issue_key]

  update_issue:
    description: Update CodeBoard issue
    available_to: [all]
    inputs: [issue_id, fields]
    outputs: [success]

  send_message:
    description: Send message to another agent
    available_to: [all]
    inputs: [to, type, payload]
    outputs: [message_id]

  request_review:
    description: Request review from review agent
    available_to: [implementation_agents, test_agents]
    inputs: [artifact, review_type]
    outputs: [review_id]

  escalate:
    description: Escalate issue to higher level
    available_to: [all]
    inputs: [issue, level, context]
    outputs: [escalation_id]
```

---

## Appendix: Agent Interaction Examples

### Example 1: Feature Implementation Flow

```
User: "Add user profile editing feature"

[O-1] Receives request
  → Creates workflow
  → Assigns to S-2 (Project Manager)

[S-2] breakdown_epic
  → Creates Epic: "User Profile Editing"
  → Creates Stories:
    - "User can view their profile"
    - "User can edit profile fields"
    - "User can upload avatar"

[O-1] Routes to S-1 (Solution Architect)

[S-1] design_system
  → Designs architecture
  → Components: ProfilePage, ProfileForm, AvatarUpload
  → APIs: GET /profile, PATCH /profile, POST /profile/avatar
  → Database: No changes (uses existing User table)

[O-1] Routes to S-3 (Security Architect)

[S-3] security_review
  → Reviews architecture
  → Adds requirements:
    - Validate file types for avatar
    - Rate limit avatar uploads
    - Sanitize profile fields

[O-1] Routes to S-2 for task breakdown

[S-2] breakdown_story (for each story)
  → Creates Tasks with assignments:
    - T1: Create ProfilePage component (I-1)
    - T2: Create GET /profile endpoint (I-2)
    - T3: Create ProfileForm component (I-1)
    - ...

[O-1] Routes tasks to C-1 (Tech Lead)

[C-1] task_refine
  → Adds implementation details
  → Provides code examples
  → Assigns to specialists

[I-1] component_create (T1: ProfilePage)
  → Creates component
  → Submits for review

[R-1] code_review
  → Reviews code
  → Requests changes (missing loading state)

[I-1] Fixes issues
  → Resubmits

[R-1] code_review
  → Approves

[T-1] unit_test_create
  → Creates tests for ProfilePage

[O-1] Continues until all tasks complete...

[R-4] final_review
  → All gates passed
  → APPROVED

[O-1] Marks workflow complete
  → Notifies user
```

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-02-07 | Claude | Initial detailed specs |
