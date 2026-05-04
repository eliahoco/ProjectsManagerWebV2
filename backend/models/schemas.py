"""
Pydantic schemas for API request/response validation
"""

import json
import re

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any, Dict
from datetime import datetime
from enum import Enum


def ms_to_datetime(ms_timestamp: Any) -> Optional[datetime]:
    """Convert millisecond timestamp to datetime"""
    if ms_timestamp is None:
        return None
    if isinstance(ms_timestamp, datetime):
        return ms_timestamp
    if isinstance(ms_timestamp, (int, float)):
        return datetime.fromtimestamp(ms_timestamp / 1000.0)
    return ms_timestamp


# Enums
class IssueType(str, Enum):
    FEATURE = "FEATURE"
    EPIC = "EPIC"
    STORY = "STORY"
    TASK = "TASK"
    SUBTASK = "SUBTASK"
    BUG = "BUG"


class IssueStatus(str, Enum):
    BACKLOG = "BACKLOG"
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    COMPLETED_WAITING_QA = "COMPLETED_WAITING_QA"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class Priority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class LinkType(str, Enum):
    BLOCKS = "BLOCKS"
    IS_BLOCKED_BY = "IS_BLOCKED_BY"
    RELATES_TO = "RELATES_TO"
    DUPLICATES = "DUPLICATES"
    IS_DUPLICATED_BY = "IS_DUPLICATED_BY"
    CAUSED_BY = "CAUSED_BY"
    CAUSES = "CAUSES"


class CommitLinkType(str, Enum):
    MENTIONS = "MENTIONS"      # Commit message contains issue key
    FIXES = "FIXES"            # Commit fixes the issue (triggers DONE status)
    CLOSES = "CLOSES"          # Commit closes the issue (triggers DONE status)
    IMPLEMENTS = "IMPLEMENTS"  # Commit implements the issue (triggers IN_REVIEW status)


# Base schemas
class Complexity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IssueBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    type: IssueType = IssueType.TASK
    status: IssueStatus = IssueStatus.BACKLOG
    priority: Priority = Priority.MEDIUM
    parentId: Optional[str] = None
    assignee: Optional[str] = None
    reporter: Optional[str] = None
    storyPoints: Optional[int] = Field(None, ge=0)
    estimate: Optional[float] = Field(None, ge=0)
    dueDate: Optional[datetime] = None
    labels: Optional[str] = None  # JSON array
    breakdownBatchId: Optional[str] = None  # UUID to group issues from same AI breakdown


class IssueCreate(IssueBase):
    """Schema for creating a new issue"""
    pass


class IssueUpdate(BaseModel):
    """Schema for updating an issue - all fields optional"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    type: Optional[IssueType] = None
    status: Optional[IssueStatus] = None
    priority: Optional[Priority] = None
    parentId: Optional[str] = None
    assignee: Optional[str] = None
    reporter: Optional[str] = None
    storyPoints: Optional[int] = Field(None, ge=0)
    estimate: Optional[float] = Field(None, ge=0)
    timeSpent: Optional[float] = Field(None, ge=0)
    dueDate: Optional[datetime] = None
    labels: Optional[str] = None
    breakdownBatchId: Optional[str] = None
    # Implementation Documentation
    implementationSummary: Optional[str] = None
    technicalApproach: Optional[str] = None
    documentationPath: Optional[str] = None
    # Enhanced Metadata
    estimatedHours: Optional[float] = Field(None, ge=0)
    actualHours: Optional[float] = Field(None, ge=0)
    complexity: Optional[Complexity] = None
    # AI Context
    aiContext: Optional[str] = None


class IssueResponse(IssueBase):
    """Schema for issue response"""
    id: str
    projectId: str
    key: str
    sequence: int
    timeSpent: Optional[float] = None
    startedAt: Optional[datetime] = None
    completedAt: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime
    # Implementation Documentation
    implementationSummary: Optional[str] = None
    technicalApproach: Optional[str] = None
    documentationPath: Optional[str] = None
    # Enhanced Metadata
    estimatedHours: Optional[float] = None
    actualHours: Optional[float] = None
    complexity: Optional[str] = None
    # AI Context
    aiContext: Optional[str] = None

    class Config:
        from_attributes = True


class IssueWithChildren(IssueResponse):
    """Issue with nested children"""
    children: List["IssueResponse"] = []


# Comment schemas
class CommentBase(BaseModel):
    content: str = Field(..., min_length=1)


class CommentCreate(CommentBase):
    author: str = Field(default="System")


class CommentResponse(CommentBase):
    id: str
    issueId: str
    author: str
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True


# Activity schemas
class ActivityResponse(BaseModel):
    id: str
    issueId: str
    actor: str
    action: str
    field: Optional[str] = None
    oldValue: Optional[str] = None
    newValue: Optional[str] = None
    createdAt: datetime

    class Config:
        from_attributes = True


# Issue Link schemas
class IssueLinkCreate(BaseModel):
    """Create payload for POST /api/issues/{id}/relations (CB-1971).

    `extra="forbid"` rejects over-posting; `toIssueId` is bound by the
    project's id-shape (CUIDs ~25 chars, UUIDs 36, CB-XXXX keys far
    shorter — 64 is a forgiving ceiling). The pattern blocks control
    chars (CRLF) so the value can't forge log lines downstream.
    """
    model_config = {"extra": "forbid"}

    toIssueId: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_\-]+$",
    )
    linkType: LinkType


class IssueSummary(BaseModel):
    """Read-only summary projection of an Issue used to embed both ends of a link.

    Populated from the ORM relationship side; never accepted as input.
    Status is typed as ``str`` (not ``IssueStatus``) to mirror ``IssueResponse``
    and avoid 500s on legacy rows whose status falls outside the enum.
    """
    id: str
    key: str
    title: str
    status: str

    class Config:
        from_attributes = True


class IssueLinkResponse(BaseModel):
    id: str
    fromIssueId: str
    toIssueId: str
    linkType: LinkType
    createdAt: datetime
    fromIssue: Optional[IssueSummary] = None
    toIssue: Optional[IssueSummary] = None

    class Config:
        from_attributes = True


# Bulk relation create (CB-1972). Hard-cap targets to bound the per-request
# work — each target may trigger a cycle-BFS for transitive types, and the
# cycle BFS itself is bounded by `_MAX_CYCLE_VISIT` in api/relations.py.
# 100 covers realistic batch-link use cases (multi-select in the UI, import
# flows) without letting a single POST hold a worker indefinitely.
_ISSUE_LINK_BULK_MAX_TARGETS = 100
_ISSUE_LINK_ID_PATTERN = r"^[A-Za-z0-9_\-]+$"


class IssueLinkBulkCreate(BaseModel):
    """Create payload for POST /api/issues/{id}/relations/bulk (CB-1972).

    `extra="forbid"` blocks over-posting. `toIssueIds` is bounded both in
    list size and per-id length/shape — same regex as the single-create
    schema, applied per item via `field_validator`. Duplicates within the
    request are tolerated here and deduplicated at the endpoint layer
    (preserving order) so callers can safely paste a list with repeats.
    """
    model_config = {"extra": "forbid"}

    toIssueIds: List[str] = Field(
        ...,
        min_length=1,
        max_length=_ISSUE_LINK_BULK_MAX_TARGETS,
    )
    linkType: LinkType

    @field_validator("toIssueIds")
    @classmethod
    def _check_id_shape(cls, value: List[str]) -> List[str]:
        for tid in value:
            if not isinstance(tid, str) or not (1 <= len(tid) <= 64):
                raise ValueError("toIssueId must be a 1-64 char string")
            if not re.fullmatch(_ISSUE_LINK_ID_PATTERN, tid):
                raise ValueError("toIssueId contains invalid characters")
        return value


class IssueLinkBulkSkipped(BaseModel):
    """One entry of the `skipped` list returned by the bulk-create endpoint.

    `reason` is one of `DUPLICATE` (link already exists in either
    direction) or `CYCLE` (transitive types only — would close a cycle in
    the BLOCKS or CAUSES family graph). Surfaced explicitly so the client
    can distinguish *why* an item didn't make it in without forcing a
    second round-trip to GET the existing relations.
    """
    toIssueId: str
    reason: str


class IssueLinkBulkResponse(BaseModel):
    """Response for POST /api/issues/{id}/relations/bulk (CB-1972).

    `created` mirrors the single-create response shape (CB-1971) — full
    IssueLinkResponse with embedded fromIssue/toIssue summaries — and is
    ordered to match the order in which links were inserted (which itself
    reflects the de-duplicated order of the request payload). `skipped`
    enumerates targets that were silently skipped instead of raising.
    """
    created: List[IssueLinkResponse]
    skipped: List[IssueLinkBulkSkipped]


class IssueLinkDeleteResponse(BaseModel):
    """Response for DELETE /api/issues/{id}/relations/{relation_id} (CB-1974).

    `deleted` is the number of rows removed in the same transaction —
    always 2 in practice (the targeted row plus its companion inverse row
    written by the create path, CB-1971). Surfaced as an integer instead
    of a fixed constant so a future evolution that drops the companion
    invariant doesn't silently break the contract — clients can assert
    on the count and notice.

    Bounds: ``ge=1`` because the endpoint raises 404 on rowcount=0 (no
    successful response is ever returned with 0); ``le=2`` because the
    DELETE matches at most the addressed row plus exactly one companion
    under UNIQUE(fromIssueId, toIssueId, linkType). A future regression
    that returns 0 or >2 will fail Pydantic response validation and
    surface as a 500 instead of a silent contract drift.
    """
    deleted: int = Field(..., ge=1, le=2)


class IssueRelationsListResponse(BaseModel):
    """Response for GET /api/issues/{id}/relations (CB-1973).

    Splits the rows by direction:
      * `outbound` — rows where the requested issue is the `from` end
        (i.e. the row's ``fromIssueId`` equals the issue id in the URL).
      * `inbound` — rows where the requested issue is the `to` end.

    Because the create path writes a primary row plus a companion inverse
    row in the same transaction (CB-1971), every relation involving the
    issue surfaces in BOTH lists — once as the user-authored direction and
    once as its companion. Consumers that want a deduplicated view can
    pick the side that matches their UI orientation; the embedded
    fromIssue/toIssue summaries (CB-1960) carry enough context to render
    either side without additional fetches.
    """
    outbound: List[IssueLinkResponse]
    inbound: List[IssueLinkResponse]


# ============================================
# Issue Group schemas (CB-1955 / Story CB-1961 / Task CB-1963)
#
# Wire-format contract for the IssueGroup + IssueGroupMember tables defined
# in models/grouping.py. Aggregate status (statusBreakdown, completionPercent,
# dominantStatus) is computed on read by the CB-1958 helper — no stored column.
# ============================================

# Hard caps on the create payload — bounded so the create path is predictable
# and a malicious or buggy caller can't ship a multi-MB body that gets
# persisted, indexed, and re-serialized in every list response.
#   * 500 ids per create call: anything larger goes through a follow-up
#     bulk-add endpoint instead of one giant POST body.
#   * 64-char id: cuid is ~25 chars and CB-XXXX keys are far shorter; 64 is a
#     forgiving ceiling.
#   * 10_000-char description: matches the order of magnitude used elsewhere
#     for human prose fields. Title is already capped at 500.
_ISSUE_GROUP_MAX_INITIAL_MEMBERS = 500
_ISSUE_GROUP_MAX_ISSUE_ID_LEN = 64
_ISSUE_GROUP_MAX_DESCRIPTION_LEN = 10_000


class IssueGroupCreate(BaseModel):
    """Schema for creating a new IssueGroup.

    `issueIds` is optional — a group can be created empty and have members
    added later. When supplied, the schema dedupes (the underlying
    `IssueGroupMember` table has a UNIQUE(groupId, issueId), so duplicates
    would otherwise surface as a 500 from the service layer) and enforces
    per-id length. Cross-project membership is the service layer's job —
    only id-shape and list-cap are checked here.
    """
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(
        default=None, max_length=_ISSUE_GROUP_MAX_DESCRIPTION_LEN,
    )
    issueIds: Optional[List[str]] = Field(
        default=None,
        max_length=_ISSUE_GROUP_MAX_INITIAL_MEMBERS,
    )

    @field_validator("issueIds")
    @classmethod
    def _validate_issue_ids(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        deduped: List[str] = []
        seen: set[str] = set()
        for raw in v:
            if not isinstance(raw, str):
                raise ValueError("issueIds entries must be strings")
            issue_id = raw.strip()
            if not issue_id:
                raise ValueError("issueIds entries must be non-empty")
            if len(issue_id) > _ISSUE_GROUP_MAX_ISSUE_ID_LEN:
                raise ValueError(
                    f"issueId exceeds {_ISSUE_GROUP_MAX_ISSUE_ID_LEN} chars "
                    f"(got {len(issue_id)})"
                )
            if issue_id in seen:
                continue
            seen.add(issue_id)
            deduped.append(issue_id)
        return deduped


class IssueGroupUpdate(BaseModel):
    """Schema for updating an IssueGroup — title/description only.

    Membership is managed via dedicated member endpoints (CB-1961 epic), not
    via this PATCH body, so we deliberately omit issueIds here.
    """
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = Field(
        default=None, max_length=_ISSUE_GROUP_MAX_DESCRIPTION_LEN,
    )


class IssueGroupResponse(BaseModel):
    """Group summary used in list endpoints.

    `memberCount` is set by the service layer via ``setattr(group, ...)``
    before ``model_validate`` — there is no ORM column for it. When the attr
    is absent the field falls back to the default of 0 (validated by the
    test suite); never wire ``func.count`` into the ORM in pursuit of this
    field. Aggregate status is intentionally NOT included here; clients that
    need it must fetch the detail endpoint.
    """
    id: str
    projectId: str
    title: str
    description: Optional[str] = None
    memberCount: int = Field(default=0, ge=0)
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True


class IssueGroupMemberResponse(BaseModel):
    """Membership row with embedded issue summary projection.

    Mirrors the IssueLinkResponse pattern (CB-1960): the `issue` field is
    populated from the read-only ORM relationship via selectinload at the
    call site. Defaults to None so a bare ORM row without eager loading
    still validates without raising.

    `position` (CB-1965) is the 1-based ordinal of this member within its
    group. The default of 0 covers two cases: legacy rows that pre-date the
    column, and bare ORM instances built in tests without going through the
    `next_member_position` service helper.
    """
    id: str
    groupId: str
    issueId: str
    position: int = Field(default=0, ge=0)
    createdAt: datetime
    issue: Optional[IssueSummary] = None

    @field_validator("position", mode="before")
    @classmethod
    def _default_position(cls, v: Any) -> Any:
        # SQLAlchemy only fires Column(default=0) at flush time, so a bare
        # ORM row built in tests or before commit has position=None.
        # Coerce None → 0 so model_validate succeeds without forcing every
        # caller to commit first.
        return 0 if v is None else v

    class Config:
        from_attributes = True


class GroupAggregateStatus(BaseModel):
    """Computed status snapshot for a group's members.

    Output shape for the CB-1958 compute_group_status helper. Empty groups
    return an empty breakdown, completionPercent=0.0, dominantStatus=None.
    `dominantStatus` is typed as plain str (not IssueStatus enum) for the
    same reason IssueSummary.status is — to avoid 500s on legacy rows whose
    status falls outside the current enum.
    """
    statusBreakdown: Dict[str, int] = Field(default_factory=dict)
    completionPercent: float = Field(default=0.0, ge=0.0, le=100.0)
    dominantStatus: Optional[str] = None


class IssueGroupDetailResponse(BaseModel):
    """Single group + full member list + aggregate status.

    Used by GET /api/groups/{id}. `members` always contains the membership
    rows even when their embedded `issue` projection is None (no eager
    load), so callers can distinguish "no members" from "members without
    issue summaries hydrated".
    """
    id: str
    projectId: str
    title: str
    description: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime
    members: List[IssueGroupMemberResponse] = Field(default_factory=list)
    aggregateStatus: GroupAggregateStatus = Field(default_factory=GroupAggregateStatus)

    class Config:
        from_attributes = True


class PaginatedGroupResponse(BaseModel):
    """Paginated wrapper for the group list endpoint.

    Mirrors PaginatedResponse for issues so the frontend can reuse the same
    pagination component without a parallel shape.
    """
    items: List[IssueGroupResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int


# Bulk membership add (CB-1989). Reuses the create-group caps so a caller can
# never bulk-grow a group's bounded membership in a single POST larger than
# the original max-initial-members budget. The id-shape rules mirror
# IssueGroupCreate so callers see a single consistent contract for member ids
# regardless of which endpoint they hit.
class IssueGroupMembersBulkAdd(BaseModel):
    """Schema for POST /api/groups/{group_id}/members (CB-1989).

    Body shape: ``{issueIds: [str]}``. The schema dedupes duplicates within
    the request (the same UNIQUE(groupId, issueId) the create path defends
    against) and enforces per-id length, mirroring IssueGroupCreate so the
    two endpoints share one wire contract for member ids. ``min_length=1``
    because an empty bulk-add is a no-op the caller shouldn't be making.
    Cross-project membership and missing-issue checks live in the endpoint —
    only id-shape and list-cap are checked here.
    """
    model_config = {"extra": "forbid"}

    issueIds: List[str] = Field(
        ...,
        min_length=1,
        max_length=_ISSUE_GROUP_MAX_INITIAL_MEMBERS,
    )

    @field_validator("issueIds")
    @classmethod
    def _validate_issue_ids(cls, v: List[str]) -> List[str]:
        deduped: List[str] = []
        seen: set[str] = set()
        for raw in v:
            if not isinstance(raw, str):
                raise ValueError("issueIds entries must be strings")
            issue_id = raw.strip()
            if not issue_id:
                raise ValueError("issueIds entries must be non-empty")
            if len(issue_id) > _ISSUE_GROUP_MAX_ISSUE_ID_LEN:
                raise ValueError(
                    f"issueId exceeds {_ISSUE_GROUP_MAX_ISSUE_ID_LEN} chars "
                    f"(got {len(issue_id)})"
                )
            if issue_id in seen:
                continue
            seen.add(issue_id)
            deduped.append(issue_id)
        return deduped


class IssueGroupMembersBulkAddResponse(BaseModel):
    """Response for POST /api/groups/{group_id}/members (CB-1989).

    `added` is the list of issueIds that were inserted as new members in
    this call. `skipped` is the list of issueIds that were silently skipped
    because they were already members of the group (UNIQUE(groupId,
    issueId) would otherwise fire). Order in both lists preserves the
    deduplicated request order so the caller can correlate against their
    input array.

    The shape is intentionally minimal (issueIds only, no embedded member
    rows) — clients that need the full membership list call the detail
    endpoint (CB-1986) once after the bulk-add.
    """
    added: List[str] = Field(default_factory=list)
    skipped: List[str] = Field(default_factory=list)


# Bulk membership remove (CB-1990). Same wire-shape rules as BulkAdd so
# callers see one consistent contract for member-id payloads regardless of
# which membership endpoint they hit. The cap mirrors the create-group
# budget so a single DELETE can never strip more rows than a single POST
# could ever have inserted.
class IssueGroupMembersBulkRemove(BaseModel):
    """Schema for DELETE /api/groups/{group_id}/members (CB-1990).

    Body shape: ``{issueIds: [str]}``. The schema dedupes duplicates within
    the request (so a doubled-up id is only classified once across the
    {removed, notFound} split) and enforces the same per-id length cap as
    IssueGroupMembersBulkAdd. ``min_length=1`` because an empty bulk-remove
    is a no-op the caller shouldn't be making — a 422 here surfaces the
    misuse instead of silently returning ``{removed:0, notFound:[]}``.

    Existence + membership checks live in the endpoint — only id-shape and
    list-cap are enforced here. Issues that don't exist at all and issues
    that exist but aren't members of this group are treated identically as
    `notFound` (the caller's request was "not a member"); the endpoint is
    therefore safe against a probing caller (no existence-oracle leak via
    differing error codes).
    """
    model_config = {"extra": "forbid"}

    issueIds: List[str] = Field(
        ...,
        min_length=1,
        max_length=_ISSUE_GROUP_MAX_INITIAL_MEMBERS,
    )

    @field_validator("issueIds")
    @classmethod
    def _validate_issue_ids(cls, v: List[str]) -> List[str]:
        deduped: List[str] = []
        seen: set[str] = set()
        for raw in v:
            if not isinstance(raw, str):
                raise ValueError("issueIds entries must be strings")
            issue_id = raw.strip()
            if not issue_id:
                raise ValueError("issueIds entries must be non-empty")
            if len(issue_id) > _ISSUE_GROUP_MAX_ISSUE_ID_LEN:
                raise ValueError(
                    f"issueId exceeds {_ISSUE_GROUP_MAX_ISSUE_ID_LEN} chars "
                    f"(got {len(issue_id)})"
                )
            if issue_id in seen:
                continue
            seen.add(issue_id)
            deduped.append(issue_id)
        return deduped


class IssueGroupMembersBulkRemoveResponse(BaseModel):
    """Response for DELETE /api/groups/{group_id}/members (CB-1990).

    `removed` is the actual number of GroupMember rows the DELETE wiped —
    sourced from the statement's rowcount, not ``len(notFound's complement)``,
    so a concurrent unmember between the membership-classification SELECT
    and the DELETE is reflected truthfully (the caller learns we removed
    fewer than they expected, instead of us claiming a phantom delete).

    `notFound` is the list of issueIds that were not members of the group
    at the moment of classification — covers (a) ids that point to
    nonexistent issues and (b) ids that point to issues belonging to a
    different group / no group / the same project but not this group.
    Lumping both cases under one bucket avoids leaking issue existence to
    a probing caller via differing response shapes (the endpoint has no
    project-level auth today, but the unified shape future-proofs against
    one being added later). Order preserves the deduped request order so
    the caller can correlate against their input array.

    Issues themselves are never deleted — only the GroupMember row is
    removed (FK on IssueGroupMember.issueId is RESTRICT-by-omission, but
    the DELETE here only touches IssueGroupMember rows, not Issue rows).
    """
    removed: int = Field(..., ge=0)
    notFound: List[str] = Field(default_factory=list)


# Bulk membership reorder (CB-2015 / drag-to-reorder).
#
# Why a single bulk-rewrite endpoint instead of a per-row PATCH /members/{id}:
#   * The drag-to-reorder UX moves one row but renumbers a contiguous range
#     (e.g. moving slot 3 → 1 shifts 1..2 down). A per-row PATCH would force
#     the client into N round-trips with a half-numbered intermediate state
#     visible on the wire, plus we'd need a temporary unique-violation
#     suspension. A single payload that asserts "this is the new full order"
#     is atomic, monotonically renumbers 1..N inside one transaction, and
#     can't leave gaps under crash or partial failure.
#   * The set-equality precondition (orderedIssueIds must equal the current
#     member set, no extras / no missing) closes the TOCTOU window where a
#     concurrent add/remove between the client's last GET and this PATCH
#     would silently demote or duplicate a member. The 400 surfaces the
#     diff so the caller can re-fetch and retry against fresh state.
class IssueGroupMembersReorder(BaseModel):
    """Schema for PATCH /api/groups/{group_id}/members/reorder (CB-2015).

    Body shape: ``{orderedIssueIds: [str]}`` — the COMPLETE membership of
    the group in the new desired order (1-based positions assigned in
    list order). The schema dedupes (silent dedup is a contract bug here:
    a duplicate would mean the caller's UI shows the same member twice,
    which we surface as VALIDATION_ERROR rather than collapsing) and caps
    at the same _ISSUE_GROUP_MAX_INITIAL_MEMBERS as create / bulk-add so
    the wire-payload budgets stay aligned.

    Cross-membership / existence / set-equality checks live in the endpoint
    — only id-shape, list cap, and within-request uniqueness are checked
    here. ``min_length=1`` because reordering an empty group is a no-op
    the caller shouldn't be making.
    """
    model_config = {"extra": "forbid"}

    orderedIssueIds: List[str] = Field(
        ...,
        min_length=1,
        max_length=_ISSUE_GROUP_MAX_INITIAL_MEMBERS,
    )

    @field_validator("orderedIssueIds")
    @classmethod
    def _validate_ordered_issue_ids(cls, v: List[str]) -> List[str]:
        # Unlike bulk-add (which silently dedupes — caller's "I asked twice
        # for the same op" is benign), reorder must reject duplicates: a
        # repeated id in the order list means the caller's frame of the
        # ordering is internally inconsistent. Surface as VALIDATION_ERROR
        # so the UI can re-derive the order from server state instead of
        # the schema picking an arbitrary winner. Same per-id length cap as
        # the sibling membership endpoints to keep one wire contract.
        seen: set[str] = set()
        cleaned: List[str] = []
        for raw in v:
            if not isinstance(raw, str):
                raise ValueError("orderedIssueIds entries must be strings")
            issue_id = raw.strip()
            if not issue_id:
                raise ValueError("orderedIssueIds entries must be non-empty")
            if len(issue_id) > _ISSUE_GROUP_MAX_ISSUE_ID_LEN:
                raise ValueError(
                    f"issueId exceeds {_ISSUE_GROUP_MAX_ISSUE_ID_LEN} chars "
                    f"(got {len(issue_id)})"
                )
            if issue_id in seen:
                raise ValueError(
                    f"orderedIssueIds contains duplicate id '{issue_id}' — "
                    "reorder requires a strict order with no repeats"
                )
            seen.add(issue_id)
            cleaned.append(issue_id)
        return cleaned


class IssueGroupMembersReorderResponse(BaseModel):
    """Response for PATCH /api/groups/{group_id}/members/reorder (CB-2015).

    `reordered` is the count of member rows the UPDATE re-positioned —
    sourced from the actual statement rowcount, so a no-op reorder (every
    position already matches) honestly reports 0 instead of len(payload).

    `members` is the post-update full member list (sorted by the new
    position 1..N) so the caller can prime its detail-page cache from the
    response without a follow-up GET. Mirrors the IssueGroupDetailResponse
    `members` shape (each entry includes the embedded IssueSummary
    projection) so the frontend can swap the cache atomically without a
    second round-trip.
    """
    reordered: int = Field(..., ge=0)
    members: List[IssueGroupMemberResponse] = Field(default_factory=list)


# Project schemas (for reading from frontend DB)
class ProjectResponse(BaseModel):
    id: str
    name: str
    path: str
    status: str
    description: Optional[str] = None
    type: Optional[str] = None
    version: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime

    @field_validator('createdAt', 'updatedAt', mode='before')
    @classmethod
    def convert_timestamp(cls, v):
        return ms_to_datetime(v)

    class Config:
        from_attributes = True


# List response with pagination
class PaginatedResponse(BaseModel):
    items: List[IssueResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int


# Status update batch
class BatchStatusUpdate(BaseModel):
    issueIds: List[str]
    status: IssueStatus


# Issue sequence
class IssueSequenceResponse(BaseModel):
    projectId: str
    prefix: str
    lastNumber: int

    class Config:
        from_attributes = True


# ============================================
# QA Board Schemas
# ============================================

# QA Enums
class QATaskStatus(str, Enum):
    NOT_DONE = "NOT_DONE"
    IN_PROGRESS = "IN_PROGRESS"
    PASS = "PASS"
    FAILED = "FAILED"


class QATaskType(str, Enum):
    AUTOMATED = "AUTOMATED"
    MANUAL = "MANUAL"


class QAPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# QA Task schemas
class QATaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    scenario: str = Field(..., min_length=1)  # Test steps
    expectedResult: str = Field(..., min_length=1)
    type: QATaskType = QATaskType.AUTOMATED
    priority: QAPriority = QAPriority.MEDIUM


class QATaskCreate(QATaskBase):
    """Schema for creating a new QA task"""
    linkedIssueIds: List[str] = []  # Issues this QA task tests


class QATaskUpdate(BaseModel):
    """Schema for updating a QA task - all fields optional"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    scenario: Optional[str] = None
    expectedResult: Optional[str] = None
    actualResult: Optional[str] = None
    status: Optional[QATaskStatus] = None
    type: Optional[QATaskType] = None
    priority: Optional[QAPriority] = None
    # Enhanced Linking
    linkedFeatureId: Optional[str] = None
    linkedEpicId: Optional[str] = None
    linkedStoryId: Optional[str] = None
    linkedTaskId: Optional[str] = None
    # Context
    testContext: Optional[str] = None
    failureContext: Optional[str] = None
    environmentDetails: Optional[str] = None


class QATaskResponse(QATaskBase):
    """Schema for QA task response"""
    id: str
    projectId: str
    key: str
    sequence: int
    actualResult: Optional[str] = None
    status: QATaskStatus
    executionHistory: Optional[str] = None  # JSON
    lastExecutedAt: Optional[datetime] = None
    bugIssueId: Optional[str] = None
    # Enhanced Linking
    linkedFeatureId: Optional[str] = None
    linkedEpicId: Optional[str] = None
    linkedStoryId: Optional[str] = None
    linkedTaskId: Optional[str] = None
    # Context
    testContext: Optional[str] = None
    failureContext: Optional[str] = None
    environmentDetails: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True


class QATaskWithIssues(QATaskResponse):
    """QA task with linked issue IDs"""
    linkedIssueIds: List[str] = []


# QA Execution schemas
class QAExecutionRequest(BaseModel):
    """Request to execute QA tasks"""
    qaTaskIds: List[str]
    executionMode: str = "sequential"  # "sequential" or "parallel"


class QAExecutionResult(BaseModel):
    """Result of executing a single QA task"""
    qaTaskId: str
    key: str
    status: QATaskStatus
    actualResult: Optional[str] = None
    executionTime: float  # seconds
    error: Optional[str] = None


# QA Plan Generation schemas
class QAPlanGenerateRequest(BaseModel):
    """Request to generate QA plan for an issue"""
    issueId: str
    customInstructions: Optional[str] = None


class QAPlanGenerateResponse(BaseModel):
    """Response after generating QA plan"""
    issueId: str
    qaTasksCreated: int
    qaTaskKeys: List[str]


# QA Settings schemas
class QASettingsUpdate(BaseModel):
    """Schema for updating QA settings"""
    passThreshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    autoCreateBugs: Optional[bool] = None


class QASettingsResponse(BaseModel):
    """Schema for QA settings response"""
    projectId: str
    passThreshold: float
    autoCreateBugs: bool

    class Config:
        from_attributes = True


# QA Summary
class QASummary(BaseModel):
    """Summary statistics for QA tasks"""
    totalTasks: int
    passedTasks: int
    failedTasks: int
    notDoneTasks: int
    inProgressTasks: int
    passRate: float
    isPassingThreshold: bool


# QA Evaluation Types
class AreaCoverage(BaseModel):
    """Coverage statistics for a test area"""
    area: str
    name: str
    total: int
    passed: int
    failed: int
    notDone: int
    passRate: float


class PriorityDistribution(BaseModel):
    """Distribution of tests by priority"""
    priority: str
    count: int
    passed: int
    failed: int
    percentage: float


class TypeDistribution(BaseModel):
    """Distribution of tests by type"""
    type: str
    count: int
    passed: int
    failed: int
    percentage: float


class QualityMetric(BaseModel):
    """Quality metric with score"""
    id: str
    label: str
    value: float
    maxValue: float
    status: str
    description: str


class Recommendation(BaseModel):
    """Actionable recommendation for test plan improvement"""
    id: str
    type: str
    severity: str
    title: str
    description: str
    action: Optional[str] = None
    affectedTaskIds: Optional[List[str]] = None


class ExecutionTrend(BaseModel):
    """Trend information for test executions"""
    trend: str  # 'up', 'down', 'stable'
    change: float


class QAEvaluation(BaseModel):
    """Comprehensive test plan evaluation data"""
    summary: QASummary
    areaCoverage: List[AreaCoverage]
    priorityDistribution: List[PriorityDistribution]
    typeDistribution: List[TypeDistribution]
    qualityMetrics: List[QualityMetric]
    overallScore: int
    recommendations: List[Recommendation]
    trend: ExecutionTrend
    flakyTestIds: List[str]


# ============================================
# Execution Summary Schemas
# ============================================

class ExecutionSummaryCreate(BaseModel):
    """Schema for creating an execution summary"""
    summary: str = Field(..., min_length=1)
    executedAt: datetime
    executionTime: float = Field(..., ge=0)
    provider: str = Field(..., min_length=1)
    model: Optional[str] = None
    exitCode: Optional[int] = None
    componentsModified: str = Field(default="[]")  # JSON array
    filesTouched: str = Field(default="[]")  # JSON array
    linesAdded: Optional[int] = Field(None, ge=0)
    linesRemoved: Optional[int] = Field(None, ge=0)
    architectureNotes: Optional[str] = None
    technicalNotes: Optional[str] = None
    challengesFaced: Optional[str] = None
    lessonsLearned: Optional[str] = None
    commitHashes: Optional[str] = None  # JSON array
    docFilePath: Optional[str] = None


class ExecutionSummaryResponse(ExecutionSummaryCreate):
    """Schema for execution summary response"""
    id: str
    issueId: str
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True


class ExecutionSummaryWithKeyResponse(ExecutionSummaryResponse):
    """ExecutionSummaryResponse enriched with the parent issue key.

    Used by the project-wide /documentation/summaries endpoint (CB-2087)
    so the frontend can display the CB-XXXX key without a second request.
    """
    issueKey: Optional[str] = None


# ============================================
# Feature Documentation Schemas
# ============================================

class FeatureDocumentationCreate(BaseModel):
    """Schema for creating feature documentation"""
    featureIssueId: str
    featureKey: str
    title: str = Field(..., min_length=1)
    overview: str
    requirements: str
    implementation: str
    architecture: str
    techStack: str  # JSON
    testingStrategy: str
    totalTasks: int = Field(default=0, ge=0)
    completedTasks: int = Field(default=0, ge=0)
    totalQATasks: int = Field(default=0, ge=0)
    passedQATasks: int = Field(default=0, ge=0)
    failedQATasks: int = Field(default=0, ge=0)
    mdFilePath: str
    embeddingId: Optional[str] = None


class FeatureDocumentationUpdate(BaseModel):
    """Schema for updating feature documentation"""
    title: Optional[str] = None
    overview: Optional[str] = None
    requirements: Optional[str] = None
    implementation: Optional[str] = None
    architecture: Optional[str] = None
    techStack: Optional[str] = None
    testingStrategy: Optional[str] = None
    totalTasks: Optional[int] = Field(None, ge=0)
    completedTasks: Optional[int] = Field(None, ge=0)
    totalQATasks: Optional[int] = Field(None, ge=0)
    passedQATasks: Optional[int] = Field(None, ge=0)
    failedQATasks: Optional[int] = Field(None, ge=0)
    mdFilePath: Optional[str] = None
    embeddingId: Optional[str] = None
    lastIndexedAt: Optional[datetime] = None


class FeatureDocumentationResponse(FeatureDocumentationCreate):
    """Schema for feature documentation response"""
    id: str
    projectId: str
    lastIndexedAt: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True


# ============================================
# Implementation Note Schemas
# ============================================


class NoteCategory(str, Enum):
    DECISION = "DECISION"
    APPROACH = "APPROACH"
    TRADEOFF = "TRADEOFF"
    DEPENDENCY = "DEPENDENCY"
    RISK = "RISK"
    LESSON = "LESSON"
    GENERAL = "GENERAL"


class NoteImportance(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# CB-2118 (F3): per-item caps + URL shape validation. Module-level constants
# (Pydantic v2 promotes leading-underscore class attributes to ModelPrivateAttr,
# which can't be used in arithmetic comparisons inside validators).
_IMPL_NOTE_MAX_TAGS = 50
_IMPL_NOTE_MAX_TAG_LEN = 200
_IMPL_NOTE_MAX_REFS = 50
_IMPL_NOTE_MAX_REF_LEN = 2_000
_IMPL_NOTE_UNSAFE_URL_SCHEMES = ("javascript:", "vbscript:", "data:", "file:")


class ImplementationNoteCreate(BaseModel):
    """Schema for creating an implementation note.

    `tags` and `references` are JSON-encoded strings (matching the storage
    model). The validators enforce "valid JSON array of strings" so
    downstream consumers can `json.loads` without try/except, and per-item
    caps + URL-scheme rejection on `references` close the dormant XSS path
    that existed when the only constraint was the outer `max_length` cap
    (the endpoint is unauthenticated — see security audit H1/H2).
    """
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1, max_length=100_000)
    category: NoteCategory = NoteCategory.GENERAL
    importance: NoteImportance = NoteImportance.MEDIUM
    tags: Optional[str] = Field(default=None, max_length=10_000)
    references: Optional[str] = Field(default=None, max_length=10_000)
    author: Optional[str] = Field(default="System", max_length=200)

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            parsed = json.loads(v)
        except json.JSONDecodeError as exc:
            raise ValueError(f"tags must be valid JSON: {exc.msg}") from None
        if not isinstance(parsed, list) or not all(isinstance(i, str) for i in parsed):
            raise ValueError("tags must be a JSON array of strings")
        if len(parsed) > _IMPL_NOTE_MAX_TAGS:
            raise ValueError(
                f"tags exceeds {_IMPL_NOTE_MAX_TAGS} items (got {len(parsed)})"
            )
        for tag in parsed:
            if len(tag) > _IMPL_NOTE_MAX_TAG_LEN:
                raise ValueError(
                    f"tag exceeds {_IMPL_NOTE_MAX_TAG_LEN} chars (got {len(tag)})"
                )
        return v

    @field_validator("references")
    @classmethod
    def _validate_references(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            parsed = json.loads(v)
        except json.JSONDecodeError as exc:
            raise ValueError(f"references must be valid JSON: {exc.msg}") from None
        if not isinstance(parsed, list) or not all(isinstance(i, str) for i in parsed):
            raise ValueError("references must be a JSON array of strings")
        if len(parsed) > _IMPL_NOTE_MAX_REFS:
            raise ValueError(
                f"references exceeds {_IMPL_NOTE_MAX_REFS} items (got {len(parsed)})"
            )
        for ref in parsed:
            if len(ref) > _IMPL_NOTE_MAX_REF_LEN:
                raise ValueError(
                    f"reference exceeds {_IMPL_NOTE_MAX_REF_LEN} chars (got {len(ref)})"
                )
            lower = ref.strip().lower()
            for scheme in _IMPL_NOTE_UNSAFE_URL_SCHEMES:
                if lower.startswith(scheme):
                    raise ValueError(
                        f"reference uses disallowed URL scheme: {scheme}"
                    )
        return v


class ImplementationNoteResponse(BaseModel):
    """Schema for implementation note response"""
    id: str
    issueId: str
    title: str
    content: str
    category: str
    author: str
    tags: Optional[str] = None
    references: Optional[str] = None
    importance: str
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True


# ============================================
# DocSettings (CB-2080 / T3.1.1) — singleton config for documentation pipeline
# ============================================

# Hard upper bounds. retentionDays caps to ~5 years; maxPerIssue caps at 1000
# (anything beyond that and the per-issue ExecutionSummary list becomes
# operationally meaningless).
_DOC_SETTINGS_MAX_RETENTION_DAYS = 1825
_DOC_SETTINGS_MAX_PER_ISSUE = 1000


class DocSettingsResponse(BaseModel):
    """Schema for DocSettings response."""
    key: str
    autoGenerate: bool
    retentionDays: int
    maxPerIssue: int
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True


class DocSettingsUpdate(BaseModel):
    """Schema for DocSettings PATCH — all fields optional."""
    autoGenerate: Optional[bool] = None
    retentionDays: Optional[int] = Field(
        default=None, ge=1, le=_DOC_SETTINGS_MAX_RETENTION_DAYS,
    )
    maxPerIssue: Optional[int] = Field(
        default=None, ge=1, le=_DOC_SETTINGS_MAX_PER_ISSUE,
    )


# ============================================
# AutoPilot Persistence (CB-1951)
# ============================================


class AutoPilotQueueStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_RESET = "waiting_reset"
    COMPLETED = "completed"
    ABORTED = "aborted"


class AutoPilotTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AutoPilotPauseReason(str, Enum):
    TOKEN_EXHAUSTION = "token_exhaustion"
    CRASH_RECOVERY = "crash_recovery"
    MANUAL = "manual"


class AutoPilotEventType(str, Enum):
    CREATED = "created"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    AUTO_PAUSED = "auto_paused"
    MANUAL_PAUSED = "manual_paused"
    RESUMED = "resumed"
    AUTO_RESUME_SCHEDULED = "auto_resume_scheduled"
    AUTO_RESUME_FIRED = "auto_resume_fired"
    ABORTED = "aborted"
    CRASH_RECOVERY_DETECTED = "crash_recovery_detected"


class AutoPilotTaskRecordResponse(BaseModel):
    id: str
    queueId: str
    sequence: int
    issueId: str
    status: AutoPilotTaskStatus
    attempts: int
    sessionId: Optional[str] = None
    startedAt: Optional[datetime] = None
    completedAt: Optional[datetime] = None
    failureReason: Optional[str] = None

    class Config:
        from_attributes = True


class AutoPilotEventResponse(BaseModel):
    id: str
    queueId: str
    type: AutoPilotEventType
    payload: str  # JSON string; callers can json.loads
    createdAt: datetime

    class Config:
        from_attributes = True


class AutoPilotQueueRecordResponse(BaseModel):
    id: str
    projectId: str
    featureId: Optional[str] = None
    status: AutoPilotQueueStatus
    currentIndex: int
    pauseReason: Optional[AutoPilotPauseReason] = None
    resetTime: Optional[datetime] = None
    config: str  # JSON string
    createdAt: datetime
    updatedAt: datetime
    completedAt: Optional[datetime] = None
    tasks: List[AutoPilotTaskRecordResponse] = []

    class Config:
        from_attributes = True


class AutoPilotRecoveryStatusResponse(BaseModel):
    """Returned by GET /api/execute/queue/recovery-status."""
    queues: List[AutoPilotQueueRecordResponse] = []
    recoveredCount: int = 0


class AutoPilotMetricsResponse(BaseModel):
    """Returned by GET /api/execute/queue/metrics."""
    pending: int = 0
    running: int = 0
    paused: int = 0
    waiting_reset: int = 0
    completed: int = 0
    aborted: int = 0
    autoPause24h: int = 0
    avgResetWaitSeconds: Optional[float] = None
