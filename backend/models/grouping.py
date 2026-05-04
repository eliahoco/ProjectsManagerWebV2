"""
SQLAlchemy models for Issue Grouping (CB-1955 / Epic CB-1956 / Story CB-1961).

IssueGroup: named cluster of N issues belonging to a single project. No stored
status field — aggregate status is computed on read in v1 (see CB-1958
compute_group_status helper).

IssueGroupMember: association object linking an issue to a group. Mirrors the
QATaskIssueLink shape: small, indexed, unique on (groupId, issueId).

FK semantics:
  IssueGroup.projectId  -> Project.id   ondelete=RESTRICT
      (refuse to drop a project while groups still reference it; protects the
      audit trail from silent data loss)
  IssueGroupMember.groupId -> IssueGroup.id  ondelete=CASCADE
      (deleting a group drops its membership rows)
  IssueGroupMember.issueId -> Issue.id   ondelete=CASCADE
      (deleting an issue drops its membership rows)
"""

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    ForeignKey,
    Index,
    UniqueConstraint,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.database import Base


class IssueGroup(Base):
    """Named cluster of issues within a project."""
    __tablename__ = "IssueGroup"

    id = Column(String, primary_key=True)
    projectId = Column(
        String,
        ForeignKey("Project.id", ondelete="RESTRICT"),
        nullable=False,
    )

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    members = relationship(
        "IssueGroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
        passive_deletes=True,
        # Secondary sort on `id` makes the order deterministic when two
        # members share a `position` (see the race documented on
        # `next_member_position`). Without it, ties fall back to whatever
        # SQLite chooses, which is not part of the API contract.
        order_by="(IssueGroupMember.position, IssueGroupMember.id)",
    )

    __table_args__ = (
        Index("IssueGroup_projectId_idx", "projectId"),
    )


class IssueGroupMember(Base):
    """Association row linking an Issue to an IssueGroup."""
    __tablename__ = "IssueGroupMember"

    id = Column(String, primary_key=True)
    groupId = Column(
        String,
        ForeignKey("IssueGroup.id", ondelete="CASCADE"),
        nullable=False,
    )
    issueId = Column(
        String,
        ForeignKey("Issue.id", ondelete="CASCADE"),
        nullable=False,
    )

    # CB-1965: 1-based ordinal within a group. Service layer assigns the
    # next slot via `next_member_position` (COALESCE(MAX(position), 0) + 1)
    # at insert time.
    #   * server_default="0" handles legacy rows added under the CB-1964
    #     shape: when the ALTER ADD COLUMN pass runs, those pre-existing
    #     rows take 0.
    #   * default=0 (Python-side) means a bare `IssueGroupMember(...)`
    #     instance has `position == 0` before flush — important so
    #     IssueGroupMemberResponse can validate ORM rows that haven't yet
    #     gone through `next_member_position`.
    position = Column(Integer, nullable=False, default=0, server_default="0")

    createdAt = Column(DateTime, server_default=func.now(), nullable=False)

    group = relationship("IssueGroup", back_populates="members", passive_deletes=True)
    # Read-only projection used by group endpoint summaries to surface
    # ({id, key, title, status}) without an extra round-trip. Mirrors the
    # CB-1960 IssueLink pattern: never written through; lazy="raise_on_sql"
    # forces explicit eager loading via selectinload at the call site.
    issue = relationship("Issue", foreign_keys=[issueId], lazy="raise_on_sql")

    __table_args__ = (
        Index("IssueGroupMember_groupId_idx", "groupId"),
        Index("IssueGroupMember_issueId_idx", "issueId"),
        UniqueConstraint(
            "groupId", "issueId",
            name="IssueGroupMember_groupId_issueId_key",
        ),
    )


async def next_member_position(session: AsyncSession, group_id: str) -> int:
    """Return the next 1-based position for a new member of `group_id`.

    Implements CB-1965's contract: ``COALESCE(MAX(position), 0) + 1`` within a
    group. An empty group returns 1; otherwise one past the highest existing
    slot. The aggregate runs against the indexed `groupId` column so it stays
    O(rows-in-group), not O(table).

    Service layer call site:
        position = await next_member_position(session, group_id)
        session.add(IssueGroupMember(..., position=position))

    Same-session loop note: this helper reads what the database currently
    sees, not the session's pending state. A loop like
        for issue_id in ids:
            pos = await next_member_position(session, group_id)
            session.add(IssueGroupMember(..., position=pos))
        await session.commit()
    will assign every member the same `pos` because none of the inserts
    have flushed yet. Either flush between calls
    (``await session.flush()``) or compute the base once and increment in
    Python: ``base = await next_member_position(...); for i, ...: pos =
    base + i``.

    Cross-session concurrency note: two concurrent appenders against the
    same group can compute the same `position`. That's tolerated today
    because (groupId, issueId) is UNIQUE, so the second insert fails fast
    on a different invariant; the only observable artefact is two members
    sharing a `position`, which the relationship's secondary sort on `id`
    (see IssueGroup.members) makes deterministic on read. If/when a
    drag-to-reorder endpoint lands (CB-1965's stated future use case), it
    must use a transaction-scoped lock or a `RETURNING`-based reservation —
    not this helper — to keep positions strictly unique.
    """
    result = await session.execute(
        select(func.coalesce(func.max(IssueGroupMember.position), 0))
        .where(IssueGroupMember.groupId == group_id)
    )
    return int(result.scalar_one()) + 1
