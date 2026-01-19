#!/usr/bin/env python3
"""
Implementation Tracker CLI
Query and update task status in the tracker database.
"""

import sqlite3
import sys
import argparse
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "implementation_tracker.db"

# ANSI colors
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    PURPLE = '\033[0;35m'
    CYAN = '\033[0;36m'
    WHITE = '\033[1;37m'
    NC = '\033[0m'  # No Color

STATUS_COLORS = {
    'BACKLOG': Colors.WHITE,
    'TODO': Colors.BLUE,
    'IN_PROGRESS': Colors.YELLOW,
    'DONE': Colors.GREEN,
}

STATUS_ICONS = {
    'BACKLOG': '⬚',
    'TODO': '☐',
    'IN_PROGRESS': '🔄',
    'DONE': '✅',
}


def get_connection():
    """Get database connection."""
    if not DB_PATH.exists():
        print(f"{Colors.RED}Error: Database not found at {DB_PATH}{Colors.NC}")
        print(f"Run: python scripts/create_tracker_db.py")
        sys.exit(1)
    return sqlite3.connect(DB_PATH)


def show_progress():
    """Show overall progress dashboard."""
    conn = get_connection()
    cursor = conn.cursor()

    # Overall progress
    cursor.execute("SELECT * FROM overall_progress")
    p = cursor.fetchone()

    task_pct = p[8] if p[8] else 0
    filled = int(task_pct / 5)
    bar = '█' * filled + '░' * (20 - filled)

    print(f"""
{Colors.CYAN}╔══════════════════════════════════════════════════════════════════════════╗
║           ProjectsManagerWebV2 - Implementation Progress                   ║
╠══════════════════════════════════════════════════════════════════════════╣{Colors.NC}
║  Overall: [{Colors.GREEN}{bar}{Colors.NC}] {task_pct:.1f}% ({p[5]}/{p[4]} tasks)
╠══════════════════════════════════════════════════════════════════════════╣
║  EPICS:                                                                    ║""")

    # Epic progress
    cursor.execute("SELECT * FROM epic_progress")
    epics = cursor.fetchall()

    for epic in epics:
        id, title, status, priority, total_stories, done_stories, total_tasks, done_tasks, pct = epic
        icon = STATUS_ICONS.get(status, '?')
        color = STATUS_COLORS.get(status, Colors.NC)
        pct_str = f"{pct:.0f}%" if pct else "0%"

        # Truncate title
        title_display = title[:40] if len(title) > 40 else title
        print(f"║  {icon} {color}{id}: {title_display:<40}{Colors.NC} [{status}] {pct_str:>4}")

    print(f"{Colors.CYAN}╠══════════════════════════════════════════════════════════════════════════╣{Colors.NC}")

    # Current work
    cursor.execute("SELECT * FROM current_work")
    current = cursor.fetchall()

    if current:
        print("║  CURRENT WORK:                                                             ║")
        for item in current[:3]:
            type, id, title, status, parent, epic, hours = item
            title_short = title[:50] if len(title) > 50 else title
            print(f"║  📋 {id}: {title_short}")
    else:
        print("║  No tasks currently in progress                                            ║")

    print(f"{Colors.CYAN}╚══════════════════════════════════════════════════════════════════════════╝{Colors.NC}")

    conn.close()


def list_items(item_type, parent_id=None, status_filter=None):
    """List items of a specific type."""
    conn = get_connection()
    cursor = conn.cursor()

    table = item_type + 's'  # epics, stories, tasks, subtasks
    parent_col = {
        'stories': 'epic_id',
        'tasks': 'story_id',
        'subtasks': 'task_id',
    }.get(table)

    query = f"SELECT id, title, status, priority FROM {table}"
    params = []

    conditions = []
    if parent_id and parent_col:
        conditions.append(f"{parent_col} = ?")
        params.append(parent_id)
    if status_filter:
        conditions.append("status = ?")
        params.append(status_filter)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY id"

    cursor.execute(query, params)
    items = cursor.fetchall()

    print(f"\n{Colors.CYAN}{table.upper()}:{Colors.NC}")
    print("-" * 80)

    for item in items:
        id, title, status, priority = item[:4]
        icon = STATUS_ICONS.get(status, '?')
        color = STATUS_COLORS.get(status, Colors.NC)
        print(f"{icon} {color}{id:<10}{Colors.NC} {title[:60]:<60} [{status}]")

    print(f"\nTotal: {len(items)} {table}")
    conn.close()


def update_status(item_id, new_status):
    """Update the status of an item."""
    conn = get_connection()
    cursor = conn.cursor()

    # Determine table from ID prefix
    # E1 = epic, S1.1 = story, T1.1.1 = task (2 dots), T1.1.1.1 = subtask (3 dots)
    if item_id.startswith('E') and '.' not in item_id:
        table = 'epics'
    elif item_id.startswith('S'):
        table = 'stories'
    elif item_id.count('.') >= 3:
        table = 'subtasks'
    elif item_id.startswith('T'):
        table = 'tasks'
    else:
        print(f"{Colors.RED}Cannot determine item type from ID: {item_id}{Colors.NC}")
        return

    # Get current status
    cursor.execute(f"SELECT title, status FROM {table} WHERE id = ?", (item_id,))
    result = cursor.fetchone()

    if not result:
        print(f"{Colors.RED}Item not found: {item_id}{Colors.NC}")
        return

    old_status = result[1]
    title = result[0]

    if old_status == new_status:
        print(f"Status already {new_status}")
        return

    # Update status
    now = datetime.now().isoformat()
    if new_status == 'IN_PROGRESS' and old_status == 'BACKLOG':
        cursor.execute(f"UPDATE {table} SET status = ?, started_at = ? WHERE id = ?",
                      (new_status, now, item_id))
    elif new_status == 'DONE':
        cursor.execute(f"UPDATE {table} SET status = ?, completed_at = ? WHERE id = ?",
                      (new_status, now, item_id))
    else:
        cursor.execute(f"UPDATE {table} SET status = ? WHERE id = ?",
                      (new_status, item_id))

    conn.commit()
    conn.close()

    print(f"{Colors.GREEN}✓ Updated {item_id}: {old_status} → {new_status}{Colors.NC}")
    print(f"  {title}")


def start_task(task_id):
    """Mark a task as IN_PROGRESS."""
    update_status(task_id, 'IN_PROGRESS')


def complete_task(task_id):
    """Mark a task as DONE."""
    update_status(task_id, 'DONE')


def show_task(task_id):
    """Show details of a specific task."""
    conn = get_connection()
    cursor = conn.cursor()

    # Get task
    cursor.execute("""
        SELECT t.id, t.title, t.description, t.status, t.estimated_hours,
               t.actual_hours, t.started_at, t.completed_at,
               s.title as story_title, e.title as epic_title
        FROM tasks t
        JOIN stories s ON t.story_id = s.id
        JOIN epics e ON s.epic_id = e.id
        WHERE t.id = ?
    """, (task_id,))
    task = cursor.fetchone()

    if not task:
        print(f"{Colors.RED}Task not found: {task_id}{Colors.NC}")
        return

    id, title, desc, status, est_hrs, act_hrs, started, completed, story, epic = task

    icon = STATUS_ICONS.get(status, '?')
    color = STATUS_COLORS.get(status, Colors.NC)

    print(f"""
{Colors.CYAN}{'='*80}{Colors.NC}
{icon} {color}{id}{Colors.NC}: {title}
{Colors.CYAN}{'='*80}{Colors.NC}

Status:      {color}{status}{Colors.NC}
Epic:        {epic}
Story:       {story}
Estimated:   {est_hrs or 'N/A'} hours
Actual:      {act_hrs or 'N/A'} hours
Started:     {started or 'Not started'}
Completed:   {completed or 'Not completed'}

Description:
{desc or 'No description'}
""")

    # Get subtasks
    cursor.execute("""
        SELECT id, title, status FROM subtasks WHERE task_id = ? ORDER BY id
    """, (task_id,))
    subtasks = cursor.fetchall()

    if subtasks:
        print(f"\n{Colors.CYAN}Subtasks:{Colors.NC}")
        for st in subtasks:
            st_icon = STATUS_ICONS.get(st[2], '?')
            st_color = STATUS_COLORS.get(st[2], Colors.NC)
            print(f"  {st_icon} {st_color}{st[0]}{Colors.NC}: {st[1]}")

    conn.close()


def export_for_github():
    """Export tasks in a format for GitHub Issues creation."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT t.id, t.title, t.description, t.estimated_hours,
               s.id as story_id, s.title as story_title,
               e.id as epic_id, e.title as epic_title
        FROM tasks t
        JOIN stories s ON t.story_id = s.id
        JOIN epics e ON s.epic_id = e.id
        ORDER BY t.id
    """)
    tasks = cursor.fetchall()

    print("# GitHub Issues Export")
    print(f"# Generated: {datetime.now().isoformat()}")
    print(f"# Total tasks: {len(tasks)}")
    print()

    for task in tasks:
        id, title, desc, hours, story_id, story_title, epic_id, epic_title = task
        labels = f"epic:{epic_id},story:{story_id}"
        if hours:
            labels += f",estimate:{hours}h"

        print(f"## {id}: {title}")
        print(f"Labels: {labels}")
        print(f"Epic: {epic_title}")
        print(f"Story: {story_title}")
        print()

    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Implementation Tracker CLI')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Progress command
    subparsers.add_parser('progress', help='Show progress dashboard')
    subparsers.add_parser('p', help='Show progress dashboard (short)')

    # List command
    list_parser = subparsers.add_parser('list', help='List items')
    list_parser.add_argument('type', choices=['epics', 'stories', 'tasks', 'subtasks'])
    list_parser.add_argument('--parent', '-p', help='Filter by parent ID')
    list_parser.add_argument('--status', '-s', choices=['BACKLOG', 'TODO', 'IN_PROGRESS', 'DONE'])

    # Show command
    show_parser = subparsers.add_parser('show', help='Show item details')
    show_parser.add_argument('id', help='Item ID (e.g., T1.1.1)')

    # Start command
    start_parser = subparsers.add_parser('start', help='Start a task (set IN_PROGRESS)')
    start_parser.add_argument('id', help='Task ID')

    # Done command
    done_parser = subparsers.add_parser('done', help='Complete a task (set DONE)')
    done_parser.add_argument('id', help='Task ID')

    # Update command
    update_parser = subparsers.add_parser('update', help='Update item status')
    update_parser.add_argument('id', help='Item ID')
    update_parser.add_argument('status', choices=['BACKLOG', 'TODO', 'IN_PROGRESS', 'DONE'])

    # Export command
    subparsers.add_parser('export', help='Export for GitHub Issues')

    args = parser.parse_args()

    if args.command in ['progress', 'p', None]:
        show_progress()
    elif args.command == 'list':
        list_items(args.type[:-1], args.parent, args.status)  # Remove 's' from type
    elif args.command == 'show':
        show_task(args.id)
    elif args.command == 'start':
        start_task(args.id)
    elif args.command == 'done':
        complete_task(args.id)
    elif args.command == 'update':
        update_status(args.id, args.status)
    elif args.command == 'export':
        export_for_github()


if __name__ == "__main__":
    main()
