"""
Import API - Import from implementation_tracker.db into CodeBoard
"""

import sqlite3
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from models import get_db, Issue, IssueSequence

router = APIRouter(prefix="/import")


class ImportStats(BaseModel):
    """Import statistics"""
    epics: int = 0
    stories: int = 0
    tasks: int = 0
    subtasks: int = 0
    total: int = 0
    errors: List[str] = []


class ImportResponse(BaseModel):
    """Import response"""
    success: bool
    message: str
    stats: ImportStats
    project_id: str


def map_status(status: str) -> str:
    """Map tracker status to CodeBoard status"""
    status_map = {
        'BACKLOG': 'BACKLOG',
        'TODO': 'TODO',
        'IN_PROGRESS': 'IN_PROGRESS',
        'IN PROGRESS': 'IN_PROGRESS',
        'DONE': 'DONE',
        'COMPLETED': 'DONE',
    }
    return status_map.get(status.upper() if status else 'BACKLOG', 'BACKLOG')


def map_priority(priority: str) -> str:
    """Map tracker priority to CodeBoard priority"""
    priority_map = {
        'CRITICAL': 'CRITICAL',
        'HIGH': 'HIGH',
        'MEDIUM': 'MEDIUM',
        'LOW': 'LOW',
    }
    return priority_map.get(priority.upper() if priority else 'MEDIUM', 'MEDIUM')


async def get_next_key(db: AsyncSession, project_id: str, project_key: str) -> tuple[str, int]:
    """Get next issue key and update sequence"""
    result = await db.execute(
        select(IssueSequence).where(IssueSequence.projectId == project_id)
    )
    sequence = result.scalar_one_or_none()

    if sequence:
        next_num = sequence.lastNumber + 1
        sequence.lastNumber = next_num
    else:
        next_num = 1
        sequence = IssueSequence(
            id=str(uuid.uuid4()),
            projectId=project_id,
            prefix=project_key,
            lastNumber=next_num
        )
        db.add(sequence)

    return f"{project_key}-{next_num}", next_num


@router.get("/tracker/preview")
async def preview_import(
    tracker_path: str = Query(
        default="./implementation_tracker.db",
        description="Path to implementation_tracker.db"
    )
):
    """
    Preview what will be imported from the tracker database.
    """
    try:
        conn = sqlite3.connect(tracker_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Count items
        epics = cursor.execute("SELECT COUNT(*) FROM epics").fetchone()[0]
        stories = cursor.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
        tasks = cursor.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        subtasks = cursor.execute("SELECT COUNT(*) FROM subtasks").fetchone()[0]

        # Get epic summaries
        epic_list = cursor.execute("""
            SELECT id, title, status, progress FROM epics ORDER BY id
        """).fetchall()

        conn.close()

        return {
            "tracker_path": tracker_path,
            "counts": {
                "epics": epics,
                "stories": stories,
                "tasks": tasks,
                "subtasks": subtasks,
                "total": epics + stories + tasks + subtasks
            },
            "epics": [dict(e) for e in epic_list]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading tracker: {str(e)}")


@router.post("/tracker/{project_id}", response_model=ImportResponse)
async def import_from_tracker(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    tracker_path: str = Query(
        default="./implementation_tracker.db",
        description="Path to implementation_tracker.db"
    ),
    clear_existing: bool = Query(
        default=False,
        description="Clear existing issues before import"
    )
):
    """
    Import all epics, stories, tasks, and subtasks from implementation_tracker.db
    into CodeBoard as issues with proper parent-child relationships.
    """
    stats = ImportStats()
    id_map: Dict[str, str] = {}  # Maps tracker IDs to CodeBoard issue IDs

    try:
        # Connect to tracker database
        tracker_conn = sqlite3.connect(tracker_path)
        tracker_conn.row_factory = sqlite3.Row
        tracker = tracker_conn.cursor()

        # Optionally clear existing issues
        if clear_existing:
            await db.execute(delete(Issue).where(Issue.projectId == project_id))
            await db.commit()

        # Get project key for issue keys
        project_key = "CB"  # Default

        # 1. Import Epics
        epics = tracker.execute("""
            SELECT id, title, description, status, priority, progress
            FROM epics ORDER BY id
        """).fetchall()

        for epic in epics:
            try:
                key, seq = await get_next_key(db, project_id, project_key)
                issue_id = str(uuid.uuid4())

                issue = Issue(
                    id=issue_id,
                    projectId=project_id,
                    key=key,
                    sequence=seq,
                    title=epic['title'],
                    description=epic['description'] or '',
                    type='EPIC',
                    status=map_status(epic['status']),
                    priority=map_priority(epic['priority'] if 'priority' in epic.keys() else 'HIGH'),
                    storyPoints=None,
                    parentId=None,
                    createdAt=datetime.utcnow(),
                    updatedAt=datetime.utcnow()
                )
                db.add(issue)
                await db.flush()
                id_map[epic['id']] = issue_id
                stats.epics += 1
            except Exception as e:
                stats.errors.append(f"Epic {epic['id']}: {str(e)}")

        # 2. Import Stories
        stories = tracker.execute("""
            SELECT id, epic_id, title, description, status, priority
            FROM stories ORDER BY id
        """).fetchall()

        for story in stories:
            try:
                parent_id = id_map.get(story['epic_id'])
                key, seq = await get_next_key(db, project_id, project_key)
                issue_id = str(uuid.uuid4())

                issue = Issue(
                    id=issue_id,
                    projectId=project_id,
                    key=key,
                    sequence=seq,
                    title=story['title'],
                    description=story['description'] or '',
                    type='STORY',
                    status=map_status(story['status']),
                    priority=map_priority(story['priority']),
                    storyPoints=None,
                    parentId=parent_id,
                    createdAt=datetime.utcnow(),
                    updatedAt=datetime.utcnow()
                )
                db.add(issue)
                await db.flush()
                id_map[story['id']] = issue_id
                stats.stories += 1
            except Exception as e:
                stats.errors.append(f"Story {story['id']}: {str(e)}")

        # 3. Import Tasks
        tasks = tracker.execute("""
            SELECT id, story_id, title, description, status
            FROM tasks ORDER BY id
        """).fetchall()

        for task in tasks:
            try:
                parent_id = id_map.get(task['story_id'])
                key, seq = await get_next_key(db, project_id, project_key)
                issue_id = str(uuid.uuid4())

                issue = Issue(
                    id=issue_id,
                    projectId=project_id,
                    key=key,
                    sequence=seq,
                    title=task['title'],
                    description=task['description'] or '',
                    type='TASK',
                    status=map_status(task['status']),
                    priority='MEDIUM',
                    storyPoints=2,
                    parentId=parent_id,
                    createdAt=datetime.utcnow(),
                    updatedAt=datetime.utcnow()
                )
                db.add(issue)
                await db.flush()
                id_map[task['id']] = issue_id
                stats.tasks += 1
            except Exception as e:
                stats.errors.append(f"Task {task['id']}: {str(e)}")

        # 4. Import Subtasks
        subtasks = tracker.execute("""
            SELECT id, task_id, title, status
            FROM subtasks ORDER BY id
        """).fetchall()

        for subtask in subtasks:
            try:
                parent_id = id_map.get(subtask['task_id'])
                key, seq = await get_next_key(db, project_id, project_key)
                issue_id = str(uuid.uuid4())

                issue = Issue(
                    id=issue_id,
                    projectId=project_id,
                    key=key,
                    sequence=seq,
                    title=subtask['title'],
                    description='',
                    type='SUBTASK',
                    status=map_status(subtask['status']),
                    priority='MEDIUM',
                    storyPoints=1,
                    parentId=parent_id,
                    createdAt=datetime.utcnow(),
                    updatedAt=datetime.utcnow()
                )
                db.add(issue)
                await db.flush()
                id_map[subtask['id']] = issue_id
                stats.subtasks += 1
            except Exception as e:
                stats.errors.append(f"Subtask {subtask['id']}: {str(e)}")

        # Commit all changes
        await db.commit()
        tracker_conn.close()

        stats.total = stats.epics + stats.stories + stats.tasks + stats.subtasks

        return ImportResponse(
            success=True,
            message=f"Successfully imported {stats.total} items",
            stats=stats,
            project_id=project_id
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.post("/json/{project_id}")
async def import_from_json(
    project_id: str,
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    clear_existing: bool = Query(default=False)
):
    """
    Import from JSON structure. Expected format:
    {
        "epics": [
            {
                "title": "Epic Title",
                "description": "...",
                "stories": [
                    {
                        "title": "Story Title",
                        "tasks": [
                            {"title": "Task", "priority": "HIGH", "storyPoints": 3}
                        ]
                    }
                ]
            }
        ]
    }
    """
    stats = ImportStats()
    project_key = "CB"

    try:
        if clear_existing:
            await db.execute(delete(Issue).where(Issue.projectId == project_id))
            await db.commit()

        for epic_data in data.get('epics', []):
            # Create epic
            key, seq = await get_next_key(db, project_id, project_key)
            epic_id = str(uuid.uuid4())

            epic = Issue(
                id=epic_id,
                projectId=project_id,
                key=key,
                sequence=seq,
                title=epic_data['title'],
                description=epic_data.get('description', ''),
                type='EPIC',
                status=epic_data.get('status', 'BACKLOG'),
                priority=epic_data.get('priority', 'HIGH'),
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow()
            )
            db.add(epic)
            await db.flush()
            stats.epics += 1

            for story_data in epic_data.get('stories', []):
                # Create story
                key, seq = await get_next_key(db, project_id, project_key)
                story_id = str(uuid.uuid4())

                story = Issue(
                    id=story_id,
                    projectId=project_id,
                    key=key,
                    sequence=seq,
                    title=story_data['title'],
                    description=story_data.get('description', ''),
                    type='STORY',
                    status=story_data.get('status', 'BACKLOG'),
                    priority=story_data.get('priority', 'MEDIUM'),
                    parentId=epic_id,
                    createdAt=datetime.utcnow(),
                    updatedAt=datetime.utcnow()
                )
                db.add(story)
                await db.flush()
                stats.stories += 1

                for task_data in story_data.get('tasks', []):
                    # Create task
                    key, seq = await get_next_key(db, project_id, project_key)
                    task_id = str(uuid.uuid4())

                    task = Issue(
                        id=task_id,
                        projectId=project_id,
                        key=key,
                        sequence=seq,
                        title=task_data['title'],
                        description=task_data.get('description', ''),
                        type='TASK',
                        status=task_data.get('status', 'BACKLOG'),
                        priority=task_data.get('priority', 'MEDIUM'),
                        storyPoints=task_data.get('storyPoints', 2),
                        parentId=story_id,
                        createdAt=datetime.utcnow(),
                        updatedAt=datetime.utcnow()
                    )
                    db.add(task)
                    await db.flush()
                    stats.tasks += 1

        await db.commit()
        stats.total = stats.epics + stats.stories + stats.tasks

        return ImportResponse(
            success=True,
            message=f"Successfully imported {stats.total} items from JSON",
            stats=stats,
            project_id=project_id
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"JSON import failed: {str(e)}")
