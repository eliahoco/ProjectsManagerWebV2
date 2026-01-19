#!/usr/bin/env python3
"""
Create GitHub Issues from the tracker database.
Uses the gh CLI to create issues with proper labels and milestones.
"""

import sqlite3
import subprocess
import json
import sys
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "implementation_tracker.db"
REPO = "eliahoco/ProjectsManagerWebV2"

# Rate limiting
DELAY_BETWEEN_ISSUES = 1  # seconds


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


def create_labels():
    """Create labels for the project."""
    labels = [
        # Epic labels
        ("epic:E1", "Epic 1: Project Setup", "7057ff"),
        ("epic:E2", "Epic 2: Database & API", "0052cc"),
        ("epic:E3", "Epic 3: CodeBoard UI", "008672"),
        ("epic:E4", "Epic 4: RAG Integration", "d93f0b"),
        ("epic:E5", "Epic 5: AI Engine", "e99695"),
        ("epic:E6", "Epic 6: Git Integration", "fbca04"),
        ("epic:E7", "Epic 7: Polish & Testing", "c5def5"),
        # Type labels
        ("type:epic", "Epic - Major feature", "7057ff"),
        ("type:story", "Story - User-facing feature", "0e8a16"),
        ("type:task", "Task - Development work", "1d76db"),
        # Priority labels
        ("priority:critical", "Critical priority", "b60205"),
        ("priority:high", "High priority", "d93f0b"),
        ("priority:medium", "Medium priority", "fbca04"),
        ("priority:low", "Low priority", "0e8a16"),
        # Status labels
        ("status:backlog", "In backlog", "ededed"),
        ("status:in-progress", "In progress", "fbca04"),
        ("status:done", "Completed", "0e8a16"),
    ]

    print("Creating labels...")
    for name, description, color in labels:
        result = run_gh_command([
            "label", "create", name,
            "--repo", REPO,
            "--description", description,
            "--color", color,
            "--force"
        ])
        if result is not None:
            print(f"  ✓ {name}")
        time.sleep(0.5)


def create_milestones():
    """Create milestones for each Epic."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, description FROM epics ORDER BY id")
    epics = cursor.fetchall()

    print("\nCreating milestones...")
    for epic_id, title, description in epics:
        result = run_gh_command([
            "api", f"repos/{REPO}/milestones",
            "-X", "POST",
            "-f", f"title={epic_id}: {title}",
            "-f", f"description={description or ''}"
        ])
        if result:
            print(f"  ✓ {epic_id}: {title}")
        time.sleep(0.5)

    conn.close()


def create_epic_issues():
    """Create GitHub Issues for each Epic."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT e.id, e.title, e.description, e.priority,
               COUNT(DISTINCT s.id) as stories,
               COUNT(DISTINCT t.id) as tasks
        FROM epics e
        LEFT JOIN stories s ON s.epic_id = e.id
        LEFT JOIN tasks t ON t.story_id = s.id
        GROUP BY e.id
        ORDER BY e.id
    """)
    epics = cursor.fetchall()

    print("\nCreating Epic issues...")
    for epic in epics:
        epic_id, title, description, priority, stories, tasks = epic

        body = f"""# {title}

## Description
{description or 'No description'}

## Scope
- Stories: {stories}
- Tasks: {tasks}

## Progress
Track progress in the implementation tracker:
```bash
python scripts/tracker.py show {epic_id}
```

---
*This issue tracks the overall Epic. Individual tasks have their own issues.*
"""

        labels = [
            "type:epic",
            f"epic:{epic_id}",
            f"priority:{priority.lower()}"
        ]

        result = run_gh_command([
            "issue", "create",
            "--repo", REPO,
            "--title", f"[{epic_id}] {title}",
            "--body", body,
            "--label", ",".join(labels)
        ])

        if result:
            # Extract issue number and update database
            issue_url = result
            issue_number = issue_url.split('/')[-1]
            cursor.execute(
                "UPDATE epics SET github_issue_number = ? WHERE id = ?",
                (issue_number, epic_id)
            )
            conn.commit()
            print(f"  ✓ {epic_id}: {title} -> #{issue_number}")

        time.sleep(DELAY_BETWEEN_ISSUES)

    conn.close()


def create_task_issues(epic_filter=None, limit=None):
    """Create GitHub Issues for tasks."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = """
        SELECT t.id, t.title, t.description, t.estimated_hours,
               s.id as story_id, s.title as story_title,
               e.id as epic_id, e.title as epic_title, e.priority
        FROM tasks t
        JOIN stories s ON t.story_id = s.id
        JOIN epics e ON s.epic_id = e.id
        WHERE t.github_issue_number IS NULL
    """
    params = []

    if epic_filter:
        query += " AND e.id = ?"
        params.append(epic_filter)

    query += " ORDER BY t.id"

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query, params)
    tasks = cursor.fetchall()

    print(f"\nCreating {len(tasks)} task issues...")

    created = 0
    for task in tasks:
        task_id, title, description, hours, story_id, story_title, epic_id, epic_title, priority = task

        # Get subtasks
        cursor.execute("SELECT title FROM subtasks WHERE task_id = ? ORDER BY id", (task_id,))
        subtasks = [row[0] for row in cursor.fetchall()]

        subtask_list = "\n".join([f"- [ ] {st}" for st in subtasks]) if subtasks else "No subtasks defined"

        body = f"""## {title}

**Epic:** {epic_id} - {epic_title}
**Story:** {story_id} - {story_title}
**Estimated:** {hours or 'TBD'} hours

### Description
{description or 'See detailed implementation plan.'}

### Subtasks
{subtask_list}

### Tracker
```bash
# Start working on this task
python scripts/tracker.py start {task_id}

# Mark as complete
python scripts/tracker.py done {task_id}
```

---
*See IMPLEMENTATION_PLAN_DETAILED.md for full technical details.*
"""

        labels = [
            "type:task",
            f"epic:{epic_id}",
            f"priority:{priority.lower()}"
        ]

        result = run_gh_command([
            "issue", "create",
            "--repo", REPO,
            "--title", f"[{task_id}] {title}",
            "--body", body,
            "--label", ",".join(labels)
        ])

        if result:
            issue_url = result
            issue_number = issue_url.split('/')[-1]
            cursor.execute(
                "UPDATE tasks SET github_issue_number = ? WHERE id = ?",
                (issue_number, task_id)
            )
            conn.commit()
            print(f"  ✓ {task_id}: {title[:40]}... -> #{issue_number}")
            created += 1

        time.sleep(DELAY_BETWEEN_ISSUES)

    print(f"\nCreated {created} issues")
    conn.close()


def sync_status():
    """Sync status between database and GitHub Issues."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get tasks with GitHub issue numbers
    cursor.execute("""
        SELECT id, status, github_issue_number
        FROM tasks
        WHERE github_issue_number IS NOT NULL
    """)
    tasks = cursor.fetchall()

    print(f"Syncing {len(tasks)} tasks...")

    for task_id, status, issue_number in tasks:
        # Remove old status labels and add new one
        status_label = f"status:{status.lower().replace('_', '-')}"

        # Get current labels
        result = run_gh_command([
            "issue", "view", str(issue_number),
            "--repo", REPO,
            "--json", "labels"
        ])

        if result:
            current = json.loads(result)
            current_labels = [l["name"] for l in current.get("labels", [])]

            # Remove old status labels
            for label in current_labels:
                if label.startswith("status:"):
                    run_gh_command([
                        "issue", "edit", str(issue_number),
                        "--repo", REPO,
                        "--remove-label", label
                    ])

            # Add new status label
            run_gh_command([
                "issue", "edit", str(issue_number),
                "--repo", REPO,
                "--add-label", status_label
            ])

            # Close if done
            if status == "DONE":
                run_gh_command([
                    "issue", "close", str(issue_number),
                    "--repo", REPO
                ])

            print(f"  ✓ {task_id} -> {status}")

        time.sleep(0.5)

    conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Create GitHub Issues from tracker')
    parser.add_argument('command', choices=['labels', 'milestones', 'epics', 'tasks', 'sync', 'all'],
                       help='What to create')
    parser.add_argument('--epic', '-e', help='Only create tasks for specific epic (e.g., E1)')
    parser.add_argument('--limit', '-l', type=int, help='Limit number of issues to create')

    args = parser.parse_args()

    if args.command == 'labels':
        create_labels()
    elif args.command == 'milestones':
        create_milestones()
    elif args.command == 'epics':
        create_epic_issues()
    elif args.command == 'tasks':
        create_task_issues(args.epic, args.limit)
    elif args.command == 'sync':
        sync_status()
    elif args.command == 'all':
        create_labels()
        create_milestones()
        create_epic_issues()
        print("\n⚠️  Task issues not created automatically.")
        print("Run: python scripts/create_github_issues.py tasks --epic E1")
        print("to create issues for one epic at a time.")


if __name__ == "__main__":
    main()
