#!/usr/bin/env python3
"""
Update GitHub Issues with detailed descriptions from implementation plan files.
Parses IMPLEMENTATION_PLAN_DETAILED*.md files and updates both the database
and GitHub issues with the full detailed content.
"""

import sqlite3
import subprocess
import re
import sys
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "implementation_tracker.db"
REPO = "eliahoco/ProjectsManagerWebV2"

# Implementation plan files
PLAN_FILES = [
    Path(__file__).parent.parent / "IMPLEMENTATION_PLAN_DETAILED.md",
    Path(__file__).parent.parent / "IMPLEMENTATION_PLAN_DETAILED_PART2.md",
    Path(__file__).parent.parent / "IMPLEMENTATION_PLAN_DETAILED_PART3.md",
    Path(__file__).parent.parent / "IMPLEMENTATION_PLAN_DETAILED_PART4.md",
]

def run_gh_command(args, input_text=None):
    """Run a gh CLI command and return the result."""
    cmd = ["gh"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            input=input_text
        )
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return None
        return result.stdout.strip()
    except FileNotFoundError:
        print("Error: gh CLI not found. Install with: brew install gh")
        sys.exit(1)


def parse_task_from_markdown(content, task_id):
    """Parse a task's detailed content from markdown."""
    # Pattern to find task section
    # Match ### Task T1.1.1: Title or ### Task T1.1.1 - Title
    pattern = rf"### Task {re.escape(task_id)}[:\-\s]+([^\n]+)\n(.*?)(?=\n### Task T|\n---\n### Task|\n## Story|\n# EPIC|\Z)"

    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return None

    title = match.group(1).strip()
    body = match.group(2).strip()

    return {
        "task_id": task_id,
        "title": title,
        "body": body
    }


def parse_story_from_markdown(content, story_id):
    """Parse a story's detailed content from markdown."""
    pattern = rf"## Story {re.escape(story_id)}[:\-\s]+([^\n]+)\n(.*?)(?=\n## Story|\n# EPIC|\Z)"

    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return None

    title = match.group(1).strip()
    body = match.group(2).strip()

    # Extract just the story description (before first task)
    task_start = re.search(r'\n### Task', body)
    if task_start:
        body = body[:task_start.start()].strip()

    return {
        "story_id": story_id,
        "title": title,
        "body": body
    }


def parse_epic_from_markdown(content, epic_id):
    """Parse an epic's detailed content from markdown."""
    pattern = rf"# EPIC \d+[:\-\s]+([^\n]+)\n.*?\*\*ID:\*\* {re.escape(epic_id)}(.*?)(?=\n# EPIC|\Z)"

    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return None

    title = match.group(1).strip()
    body = match.group(2).strip()

    # Extract just epic description (before first story)
    story_start = re.search(r'\n## Story', body)
    if story_start:
        body = body[:story_start.start()].strip()

    return {
        "epic_id": epic_id,
        "title": title,
        "body": body
    }


def load_all_plans():
    """Load and concatenate all implementation plan files."""
    content = ""
    for plan_file in PLAN_FILES:
        if plan_file.exists():
            print(f"Loading {plan_file.name}...")
            content += plan_file.read_text() + "\n\n"
        else:
            print(f"Warning: {plan_file.name} not found")
    return content


def update_database_descriptions(content):
    """Update task descriptions in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all tasks
    cursor.execute("SELECT id, title FROM tasks")
    tasks = cursor.fetchall()

    updated = 0
    for task_id, current_title in tasks:
        parsed = parse_task_from_markdown(content, task_id)
        if parsed and parsed["body"]:
            cursor.execute(
                "UPDATE tasks SET description = ? WHERE id = ?",
                (parsed["body"], task_id)
            )
            updated += 1

    conn.commit()
    print(f"Updated {updated} task descriptions in database")

    # Get all stories
    cursor.execute("SELECT id, title FROM stories")
    stories = cursor.fetchall()

    updated = 0
    for story_id, current_title in stories:
        parsed = parse_story_from_markdown(content, story_id)
        if parsed and parsed["body"]:
            cursor.execute(
                "UPDATE stories SET description = ? WHERE id = ?",
                (parsed["body"], story_id)
            )
            updated += 1

    conn.commit()
    print(f"Updated {updated} story descriptions in database")

    conn.close()


def update_github_issues(content, epic_filter=None):
    """Update GitHub issues with detailed descriptions."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Build query
    query = """
        SELECT t.id, t.title, t.github_issue_number,
               s.id as story_id, s.title as story_title,
               e.id as epic_id, e.title as epic_title
        FROM tasks t
        JOIN stories s ON t.story_id = s.id
        JOIN epics e ON s.epic_id = e.id
        WHERE t.github_issue_number IS NOT NULL
    """
    params = []

    if epic_filter:
        query += " AND e.id = ?"
        params.append(epic_filter)

    query += " ORDER BY t.id"

    cursor.execute(query, params)
    tasks = cursor.fetchall()

    print(f"\nUpdating {len(tasks)} GitHub issues with detailed descriptions...")

    updated = 0
    for task in tasks:
        task_id, title, issue_number, story_id, story_title, epic_id, epic_title = task

        parsed = parse_task_from_markdown(content, task_id)
        if not parsed:
            print(f"  ⚠ {task_id}: No detailed content found")
            continue

        # Get subtasks
        cursor.execute(
            "SELECT title FROM subtasks WHERE task_id = ? ORDER BY id",
            (task_id,)
        )
        subtasks = [row[0] for row in cursor.fetchall()]
        subtask_list = "\n".join([f"- [ ] {st}" for st in subtasks]) if subtasks else "No subtasks defined"

        # Build comprehensive issue body
        body = f"""## {title}

**Epic:** {epic_id} - {epic_title}
**Story:** {story_id} - {story_title}

---

{parsed["body"]}

---

### Subtasks Checklist
{subtask_list}

---

### Tracker Commands
```bash
# Start working on this task
python3 scripts/tracker.py start {task_id}

# Mark as complete
python3 scripts/tracker.py done {task_id}

# Sync to GitHub
python3 scripts/create_github_issues.py sync
```

---
*See IMPLEMENTATION_PLAN_DETAILED*.md for full technical context.*
"""

        # Update the issue
        result = run_gh_command([
            "issue", "edit", str(issue_number),
            "--repo", REPO,
            "--body", body
        ])

        if result is not None:
            print(f"  ✓ {task_id}: #{issue_number} updated")
            updated += 1
        else:
            print(f"  ✗ {task_id}: Failed to update #{issue_number}")

        time.sleep(0.5)  # Rate limiting

    print(f"\nUpdated {updated}/{len(tasks)} issues")
    conn.close()


def update_epic_issues(content):
    """Update epic issues with detailed descriptions."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, github_issue_number, description
        FROM epics
        WHERE github_issue_number IS NOT NULL
    """)
    epics = cursor.fetchall()

    print(f"\nUpdating {len(epics)} Epic issues...")

    for epic_id, title, issue_number, current_desc in epics:
        parsed = parse_epic_from_markdown(content, epic_id)

        # Get stats
        cursor.execute("""
            SELECT COUNT(DISTINCT s.id), COUNT(DISTINCT t.id),
                   SUM(CASE WHEN t.status = 'DONE' THEN 1 ELSE 0 END)
            FROM stories s
            LEFT JOIN tasks t ON t.story_id = s.id
            WHERE s.epic_id = ?
        """, (epic_id,))
        stories, tasks, done_tasks = cursor.fetchone()

        # Get stories list
        cursor.execute("""
            SELECT id, title FROM stories WHERE epic_id = ? ORDER BY id
        """, (epic_id,))
        story_list = cursor.fetchall()

        stories_md = "\n".join([f"- **{s[0]}**: {s[1]}" for s in story_list])

        body = f"""# {title}

## Overview
{parsed["body"] if parsed else current_desc or "No description"}

## Scope
- **Stories:** {stories}
- **Tasks:** {tasks}
- **Completed:** {done_tasks or 0}
- **Progress:** {(done_tasks or 0) * 100 // tasks if tasks else 0}%

## Stories in this Epic
{stories_md}

---

### Progress Tracking
```bash
# View epic progress
python3 scripts/tracker.py show {epic_id}

# List all tasks
python3 scripts/tracker.py list tasks --parent S{epic_id[1:]}.1
```

---
*This issue tracks the overall Epic. Individual tasks have their own issues.*
"""

        result = run_gh_command([
            "issue", "edit", str(issue_number),
            "--repo", REPO,
            "--body", body
        ])

        if result is not None:
            print(f"  ✓ {epic_id}: #{issue_number} updated")

        time.sleep(0.5)

    conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Update detailed descriptions')
    parser.add_argument('command', choices=['database', 'github', 'epics', 'all'],
                       help='What to update')
    parser.add_argument('--epic', '-e', help='Only update specific epic (e.g., E1)')

    args = parser.parse_args()

    # Load all plan content
    content = load_all_plans()

    if not content:
        print("Error: No implementation plan files found")
        sys.exit(1)

    if args.command == 'database':
        update_database_descriptions(content)
    elif args.command == 'github':
        update_github_issues(content, args.epic)
    elif args.command == 'epics':
        update_epic_issues(content)
    elif args.command == 'all':
        update_database_descriptions(content)
        update_epic_issues(content)
        update_github_issues(content, args.epic)


if __name__ == "__main__":
    main()
