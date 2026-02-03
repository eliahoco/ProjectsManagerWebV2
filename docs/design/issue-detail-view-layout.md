# Issue Detail View Layout Design

**Task:** CB-459
**Story:** CB-21: Issue Detail View
**Last Updated:** 2026-01-23

## Overview

This document defines the visual layout and structure of the Issue Detail View page. The application provides two complementary views for issue details:

1. **Full Page View** - Comprehensive detail page for deep work
2. **Slide-over Panel** - Quick preview for context while browsing

---

## 1. Full Page View Layout

**Route:** `/codeboard/issues/[id]`

### Visual Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              HEADER BAR                                      │
│  ┌────┐  Project Name > ⚡ KEY-123                    [Execute] [✏️] [🗑️] [X]│
│  │ ← │                                                                       │
│  └────┘                                                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────┐  ┌────────────────────────┐│
│  │           MAIN CONTENT (2/3)                │  │    SIDEBAR (1/3)       ││
│  │                                             │  │                        ││
│  │  ┌─────────────────────────────────────┐   │  │  ┌────────────────────┐││
│  │  │         TITLE & DESCRIPTION         │   │  │  │   STATUS CARD      │││
│  │  │                                     │   │  │  │                    │││
│  │  │  [Title - Large, semibold]          │   │  │  │  Status: [Dropdown]│││
│  │  │                                     │   │  │  │  Priority: [Dropdown││
│  │  │  [Description - prose, zinc-400]    │   │  │  │  Type: [Dropdown]  │││
│  │  │                                     │   │  │  │  Story Points: [#] │││
│  │  └─────────────────────────────────────┘   │  │  └────────────────────┘││
│  │                                             │  │                        ││
│  │  ┌─────────────────────────────────────┐   │  │  ┌────────────────────┐││
│  │  │              TAB BAR                │   │  │  │   PEOPLE CARD      │││
│  │  │  [Details] [Activity] [Comments]    │   │  │  │                    │││
│  │  └─────────────────────────────────────┘   │  │  │  👤 Assignee       │││
│  │                                             │  │  │  👤 Reporter       │││
│  │  ┌─────────────────────────────────────┐   │  │  └────────────────────┘││
│  │  │           TAB CONTENT               │   │  │                        ││
│  │  │                                     │   │  │  ┌────────────────────┐││
│  │  │  DETAILS TAB:                       │   │  │  │   DATES CARD       │││
│  │  │  • Child Issues (for Epic/Story)    │   │  │  │                    │││
│  │  │  • Linked Commits                   │   │  │  │  📅 Created        │││
│  │  │  • Related Commits (fallback)       │   │  │  │  🕐 Started        │││
│  │  │                                     │   │  │  │  ✓ Completed       │││
│  │  │  ACTIVITY TAB:                      │   │  │  │  📅 Due Date       │││
│  │  │  • Timeline of events               │   │  │  └────────────────────┘││
│  │  │                                     │   │  │                        ││
│  │  │  COMMENTS TAB:                      │   │  │  ┌────────────────────┐││
│  │  │  • Comment input                    │   │  │  │   LABELS CARD      │││
│  │  │  • Comments list                    │   │  │  │  [label] [label]   │││
│  │  │                                     │   │  │  └────────────────────┘││
│  │  └─────────────────────────────────────┘   │  │                        ││
│  │                                             │  │  ┌────────────────────┐││
│  └─────────────────────────────────────────────┘  │  │   PARENT LINK      │││
│                                                    │  │  > View Parent     │││
│                                                    │  └────────────────────┘││
│                                                    └────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Breakdown

#### Header Bar
- **Back Button**: Left-aligned, returns to CodeBoard
- **Breadcrumb**: Project name > Issue type icon + Issue key (monospace, cyan)
- **Actions**: Execute button, Edit icon, Delete icon, Close/External link

#### Main Content Area (2/3 width)
- **Title**: 2xl font, semibold
- **Description**: prose styling, zinc-400 color, pre-wrap whitespace
- **Tab Navigation**: Details | Activity | Comments with cyan underline indicator

#### Sidebar (1/3 width)
Cards stacked vertically with `space-y-6` gap:

1. **Status Card** - Dropdowns for Status, Priority, Type, Story Points display
2. **People Card** - Assignee and Reporter with User icons
3. **Dates Card** - Created, Started, Completed, Due Date with conditional display
4. **Labels Card** - Flex-wrapped label chips (conditional)
5. **Parent Link Card** - Link to parent issue (conditional)

---

## 2. Slide-over Panel Layout

**Component:** `IssueDetail.tsx`

### Visual Structure

```
                                              ┌────────────────────────────────┐
                                              │          HEADER                │
     Backdrop (40% black)                     │  ⚡ KEY-123 ↗  [▶][✏️][🗑️][X] │
     Click to close                           ├────────────────────────────────┤
                                              │                                │
                                              │  ┌────────────────────────────┐│
                                              │  │     PARENT BREADCRUMB      ││
                                              │  │  Part of: ⚡ EPIC-1 > Title ││
                                              │  └────────────────────────────┘│
                                              │                                │
                                              │  [Title - xl, semibold]        │
                                              │  [Description - zinc-400]      │
                                              │                                │
                                              │  ┌────────────────────────────┐│
                                              │  │    PROPERTIES GRID (2x2)   ││
                                              │  │  Status    │  Priority     ││
                                              │  │  [Dropdown]│  [Dropdown]   ││
                                              │  │  Type      │  Story Points ││
                                              │  │  [Dropdown]│  [Display]    ││
                                              │  └────────────────────────────┘│
                                              │                                │
                                              │  ┌────────────────────────────┐│
                                              │  │         PEOPLE             ││
                                              │  │  👤 Assignee: Name         ││
                                              │  │  👤 Reporter: Name         ││
                                              │  └────────────────────────────┘│
                                              │                                │
                                              │  ┌────────────────────────────┐│
                                              │  │          DATES             ││
                                              │  │  📅 Created: date          ││
                                              │  │  🕐 Started: date          ││
                                              │  │  ✓ Completed: date         ││
                                              │  │  📅 Due: date              ││
                                              │  └────────────────────────────┘│
                                              │                                │
                                              │  ┌────────────────────────────┐│
                                              │  │     LINKED COMMITS         ││
                                              │  │  [hash] message    [type]  ││
                                              │  └────────────────────────────┘│
                                              │                                │
                                              │  ┌────────────────────────────┐│
                                              │  │    CHILD ISSUES            ││
                                              │  │  [☐] ✓ KEY Title   [status]││
                                              │  │  [☑] ✓ KEY Title   [status]││
                                              │  │                            ││
                                              │  │  [▶ Execute 2 Selected]    ││
                                              │  └────────────────────────────┘│
                                              │                                │
                                              │  ┌────────────────────────────┐│
                                              │  │  [✨ AI Breakdown]         ││
                                              │  └────────────────────────────┘│
                                              └────────────────────────────────┘
```

### Key Differences from Full Page

| Aspect | Full Page | Slide-over |
|--------|-----------|------------|
| Width | max-w-5xl centered | max-w-xl right-side |
| Layout | 3-column grid | Single column scroll |
| Navigation | Tabs for content | Linear scroll |
| Child Selection | Read-only links | Checkboxes + batch execute |
| AI Features | None | AI Breakdown button |

---

## 3. Design Tokens

### Colors (Dark Theme)

| Element | Color Class |
|---------|-------------|
| Background | `bg-zinc-900` |
| Cards | `bg-zinc-800/50` |
| Borders | `border-zinc-800` (light), `border-zinc-700` (medium) |
| Primary Text | `text-white` / `text-zinc-100` |
| Secondary Text | `text-zinc-400` |
| Muted Text | `text-zinc-500` |
| Accent | `text-cyan-500` (links, keys) |
| Focus Ring | `focus:border-cyan-500` |

### Status Colors

| Status | Background | Text |
|--------|------------|------|
| Backlog | `bg-zinc-700` | `text-zinc-400` |
| Todo | `bg-yellow-900/30` | `text-yellow-400` |
| In Progress | `bg-blue-900/30` | `text-blue-400` |
| In Review | `bg-purple-900/30` | `text-purple-400` |
| Done | `bg-green-900/30` | `text-green-400` |
| Cancelled | `bg-red-900/30` | `text-red-400` |

### Issue Type Colors

| Type | Border Color | Icon |
|------|--------------|------|
| Epic | `border-l-purple-500` | ⚡ |
| Story | `border-l-green-500` / `border-l-blue-500` | 📖 |
| Task | `border-l-blue-500` | ✓ |
| Bug | `border-l-red-500` | 🐛 |
| Subtask | `border-l-cyan-500` | ○ |

### Spacing

| Context | Value |
|---------|-------|
| Page padding | `px-6 py-4` (header), `px-6 py-8` (content) |
| Card padding | `p-4` |
| Section gaps | `space-y-6` |
| Item gaps | `space-y-2` to `space-y-4` |
| Grid gaps | `gap-4` to `gap-8` |

### Typography

| Element | Classes |
|---------|---------|
| Page Title | `text-2xl font-semibold` |
| Panel Title | `text-xl font-semibold` |
| Section Header | `text-sm font-medium text-zinc-400` |
| Labels | `text-xs font-medium text-zinc-500` |
| Body Text | `text-sm` |
| Issue Key | `font-mono text-cyan-500` |
| Commit Hash | `font-mono text-xs text-cyan-500` |

---

## 4. Interactive States

### Buttons

```css
/* Primary */
bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50

/* Destructive */
text-zinc-500 hover:text-red-400 hover:bg-zinc-800

/* Ghost */
text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800

/* Success */
bg-green-600 hover:bg-green-500

/* Feature (AI) */
bg-purple-600 hover:bg-purple-500
```

### Form Inputs

```css
/* Base */
px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm

/* Focus */
focus:outline-none focus:border-cyan-500

/* Status-aware border */
issue.status === 'DONE' && 'border-green-600'
issue.status === 'IN_PROGRESS' && 'border-blue-600'
```

### Cards

```css
/* Hover */
bg-zinc-800/50 hover:bg-zinc-800 transition-colors

/* Selected (checkboxes) */
ring-1 ring-cyan-500/50 bg-cyan-900/10
```

---

## 5. Responsive Considerations

### Breakpoints

- **Mobile (< 768px)**: Stack sidebar below main content
- **Tablet (768px - 1024px)**: Keep 3-column but reduce spacing
- **Desktop (> 1024px)**: Full layout as designed

### Mobile Adaptations

1. Full page becomes single column
2. Sidebar cards become inline sections
3. Tabs remain but may become scrollable
4. Slide-over panel width becomes `max-w-full`

---

## 6. Accessibility

### Keyboard Navigation

- **Tab order**: Header actions → Main content → Tab bar → Tab content → Sidebar
- **Escape**: Close slide-over panel
- **Enter**: Submit forms, confirm actions

### ARIA

```html
<!-- Tab navigation -->
<nav role="tablist">
  <button role="tab" aria-selected="true">Details</button>
  <button role="tab" aria-selected="false">Activity</button>
</nav>

<!-- Slide-over -->
<div role="dialog" aria-modal="true" aria-labelledby="issue-title">
```

### Screen Reader

- Issue key read as "Key: PROJECT-123"
- Status badges include full status name
- Icons have title attributes

---

## 7. Component Hierarchy

```
IssueDetailPage (Full Page)
├── Header
│   ├── BackButton
│   ├── Breadcrumb (Project > Issue)
│   └── ActionButtons (Execute, Edit, Delete, Close)
├── MainContent
│   ├── TitleSection
│   │   ├── Title (editable)
│   │   └── Description (editable)
│   ├── TabNavigation
│   │   └── Tab[] (Details, Activity, Comments)
│   └── TabContent
│       ├── DetailsTab
│       │   ├── ChildIssues[]
│       │   ├── LinkedCommits[]
│       │   └── GitCommits[]
│       ├── ActivityTab
│       │   └── ActivityTimeline
│       └── CommentsTab
│           ├── CommentInput
│           └── CommentsList
└── Sidebar
    ├── StatusCard (Status, Priority, Type, StoryPoints)
    ├── PeopleCard (Assignee, Reporter)
    ├── DatesCard (Created, Started, Completed, Due)
    ├── LabelsCard (conditional)
    └── ParentLinkCard (conditional)

IssueDetail (Slide-over)
├── Header
│   ├── IssueKey (with external link)
│   └── ActionButtons (Execute, Edit, Delete, Close)
└── Content (scrollable)
    ├── ParentBreadcrumb (conditional)
    ├── TitleSection (editable)
    ├── PropertiesGrid (2x2)
    ├── PeopleSection
    ├── DatesSection
    ├── LinkedCommitsSection
    ├── ChildIssuesSection
    │   ├── SelectionHeader
    │   ├── IssueList (with checkboxes)
    │   └── BatchExecuteButton
    └── AIBreakdownButton (conditional)
```

---

## 8. Future Enhancements

### Planned Features

1. **Attachments Section** - File uploads and previews
2. **Time Tracking** - Log work hours, remaining estimate
3. **Watchers** - Subscribe to issue updates
4. **Custom Fields** - User-defined metadata
5. **Rich Text Editor** - Markdown with preview for description
6. **Inline Comments** - Comment on specific parts of description
7. **Related Issues** - Links to blocked/blocking issues
8. **Sprint Info** - Sprint assignment and burndown context

### Layout Expansion

```
┌──────────────────────────────────────────────────────────────────┐
│                         HEADER                                    │
├──────────────────────────────────────────────────────────────────┤
│  MAIN (2/3)                         │  SIDEBAR (1/3)             │
│                                     │                             │
│  Title & Description                │  Status Card                │
│                                     │  People Card                │
│  [Details] [Activity] [Comments]    │  Dates Card                 │
│  [Attachments] [Time] [Links]       │  Sprint Card (NEW)          │
│                                     │  Labels Card                │
│  Tab Content                        │  Custom Fields (NEW)        │
│  • Attachments grid                 │  Watchers Card (NEW)        │
│  • Time log entries                 │  Parent Link                │
│  • Issue links (blocks/blocked by)  │                             │
└──────────────────────────────────────────────────────────────────┘
```

---

## Implementation Notes

- Both views share the same data hooks (`useIssue`, `useLinkedCommits`, etc.)
- Mutations use React Query with optimistic updates
- Edit mode is local state, not a separate route
- Child issue selection in slide-over enables batch AI execution
- Activity timeline is constructed from issue timestamps (future: API history)
- Comments are placeholder pending backend implementation
