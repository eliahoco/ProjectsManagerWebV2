# ProjectsManagerWebV2 - Detailed Implementation Plan (Part 3)

# EPIC 3: CodeBoard UI

**ID:** E3
**Priority:** High
**Status:** BACKLOG
**Description:** Build the complete CodeBoard user interface including Kanban board, list view, filter bar, issue detail modal, and create issue modal. This epic delivers the core visual experience of the application.

**Acceptance Criteria:**
- Kanban board with drag-and-drop status changes
- List view with sorting and pagination
- Comprehensive filter bar
- Full-featured issue detail view
- Issue creation modal with validation

---

## Story 3.1: Navigation & Layout

**ID:** S3.1
**Epic:** E3
**Priority:** High
**Description:** Add CodeBoard to the application navigation and create the base page layout.

---

### Task T3.1.1: Add CodeBoard Link to Sidebar

**ID:** T3.1.1
**Story:** S3.1
**Priority:** High
**Estimated Effort:** 15 minutes

**Description:**
Add a CodeBoard navigation link to the existing sidebar with an appropriate icon. The link should highlight when on any CodeBoard-related route.

**File: frontend/components/layout/sidebar.tsx (modification)**
```typescript
// Add to navigation items array
import { LayoutGrid } from 'lucide-react';

const navigationItems = [
  // ... existing items
  {
    name: 'CodeBoard',
    href: '/codeboard',
    icon: LayoutGrid,
    description: 'Issue tracking & task management',
  },
];

// In the sidebar component, add active state detection
const isCodeBoardActive = pathname.startsWith('/codeboard');
```

**Icon Options:**
- `LayoutGrid` - Grid/board layout icon
- `Kanban` - Explicit kanban icon (if available)
- `ListTodo` - Task list icon
- `ClipboardList` - Clipboard with list

**Acceptance Criteria:**
- [ ] CodeBoard link visible in sidebar
- [ ] Appropriate icon displayed
- [ ] Active state when on /codeboard routes
- [ ] Tooltip shows description on hover

**Sub-tasks:**
1. **Add navigation item** - CodeBoard with icon and href
2. **Add route matching** - Highlight when on /codeboard/*
3. **Test navigation** - Click navigates to /codeboard

---

### Task T3.1.2: Create /codeboard Page Layout

**ID:** T3.1.2
**Story:** S3.1
**Priority:** High
**Estimated Effort:** 45 minutes

**Description:**
Create the main CodeBoard page with header, project selector, view toggle (Kanban/List), and content area. This serves as the shell for all CodeBoard functionality.

**File: frontend/app/codeboard/page.tsx**
```typescript
'use client';

import { useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { LayoutGrid, List, Plus, RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { KanbanBoard } from '@/components/codeboard/kanban-board';
import { IssueList } from '@/components/codeboard/issue-list';
import { FilterBar } from '@/components/codeboard/filter-bar';
import { CreateIssueModal } from '@/components/codeboard/create-issue-modal';
import { useProjects } from '@/hooks/use-projects';
import { useIssues } from '@/hooks/use-issues';

type ViewMode = 'kanban' | 'list';

export default function CodeBoardPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // State
  const [viewMode, setViewMode] = useState<ViewMode>(
    (searchParams.get('view') as ViewMode) || 'kanban'
  );
  const [selectedProjectId, setSelectedProjectId] = useState<string>(
    searchParams.get('project') || ''
  );
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [filters, setFilters] = useState({
    type: [],
    status: [],
    priority: [],
    assignee: [],
    search: '',
  });

  // Data
  const { projects, isLoading: projectsLoading } = useProjects();
  const {
    issues,
    isLoading: issuesLoading,
    refetch: refetchIssues
  } = useIssues(selectedProjectId, filters);

  // Handlers
  const handleProjectChange = (projectId: string) => {
    setSelectedProjectId(projectId);
    router.push(`/codeboard?project=${projectId}&view=${viewMode}`);
  };

  const handleViewChange = (view: ViewMode) => {
    setViewMode(view);
    router.push(`/codeboard?project=${selectedProjectId}&view=${view}`);
  };

  const handleFilterChange = (newFilters: typeof filters) => {
    setFilters(newFilters);
  };

  const handleIssueCreated = () => {
    setIsCreateModalOpen(false);
    refetchIssues();
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold">CodeBoard</h1>

          {/* Project Selector */}
          <Select
            value={selectedProjectId}
            onValueChange={handleProjectChange}
          >
            <SelectTrigger className="w-[250px]">
              <SelectValue placeholder="Select a project" />
            </SelectTrigger>
            <SelectContent>
              {projects?.map((project) => (
                <SelectItem key={project.id} value={project.id}>
                  {project.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          {/* View Toggle */}
          <Tabs value={viewMode} onValueChange={(v) => handleViewChange(v as ViewMode)}>
            <TabsList>
              <TabsTrigger value="kanban" className="flex items-center gap-1">
                <LayoutGrid className="h-4 w-4" />
                Board
              </TabsTrigger>
              <TabsTrigger value="list" className="flex items-center gap-1">
                <List className="h-4 w-4" />
                List
              </TabsTrigger>
            </TabsList>
          </Tabs>

          {/* Refresh */}
          <Button variant="outline" size="icon" onClick={() => refetchIssues()}>
            <RefreshCw className="h-4 w-4" />
          </Button>

          {/* Create Issue */}
          <Button onClick={() => setIsCreateModalOpen(true)} disabled={!selectedProjectId}>
            <Plus className="h-4 w-4 mr-2" />
            Create Issue
          </Button>
        </div>
      </div>

      {/* Filter Bar */}
      <FilterBar
        filters={filters}
        onChange={handleFilterChange}
        disabled={!selectedProjectId}
      />

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {!selectedProjectId ? (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            Select a project to view issues
          </div>
        ) : issuesLoading ? (
          <div className="flex items-center justify-center h-full">
            <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : viewMode === 'kanban' ? (
          <KanbanBoard
            projectId={selectedProjectId}
            issues={issues}
            onIssueUpdate={refetchIssues}
          />
        ) : (
          <IssueList
            projectId={selectedProjectId}
            issues={issues}
            onIssueUpdate={refetchIssues}
          />
        )}
      </div>

      {/* Create Issue Modal */}
      <CreateIssueModal
        open={isCreateModalOpen}
        onOpenChange={setIsCreateModalOpen}
        projectId={selectedProjectId}
        onSuccess={handleIssueCreated}
      />
    </div>
  );
}
```

**Layout Structure:**
```
┌─────────────────────────────────────────────────────────────────┐
│ Header: Title | Project Selector | View Toggle | Actions        │
├─────────────────────────────────────────────────────────────────┤
│ Filter Bar: Type | Status | Priority | Assignee | Search        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                     Content Area                                │
│                  (Kanban or List)                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Acceptance Criteria:**
- [ ] Page renders at /codeboard route
- [ ] Project selector shows all projects
- [ ] View toggle switches between Kanban and List
- [ ] Create Issue button opens modal
- [ ] Filter bar is functional
- [ ] Empty state when no project selected

**Sub-tasks:**
1. **Create page component** - Main layout structure
2. **Add header section** - Title, project selector, actions
3. **Add project selector** - Dropdown with all projects
4. **Add view toggle** - Kanban/List tabs
5. **Add filter bar integration** - Pass filters to children
6. **Add content area** - Conditional Kanban or List
7. **Add create issue button** - Opens modal
8. **Handle URL params** - Persist project and view in URL

---

## Story 3.2: Kanban Board

**ID:** S3.2
**Epic:** E3
**Priority:** High
**Description:** Implement the Kanban board view with drag-and-drop functionality for status changes.

---

### Task T3.2.1: Create KanbanBoard Component

**ID:** T3.2.1
**Story:** S3.2
**Priority:** High
**Estimated Effort:** 45 minutes

**Description:**
Create the main Kanban board container that manages the overall board state and drag-and-drop context.

**File: frontend/components/codeboard/kanban-board.tsx**
```typescript
'use client';

import { useState, useCallback } from 'react';
import {
  DndContext,
  DragOverlay,
  closestCorners,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragStartEvent,
  DragEndEvent,
  DragOverEvent,
} from '@dnd-kit/core';
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable';

import { KanbanColumn } from './kanban-column';
import { IssueCard } from './issue-card';
import { Issue, IssueStatus } from '@/types/issue';
import { updateIssue } from '@/lib/api/issues';
import { toast } from '@/components/ui/use-toast';

// Status columns configuration
const COLUMNS: { id: IssueStatus; title: string; color: string }[] = [
  { id: 'BACKLOG', title: 'Backlog', color: 'bg-gray-100' },
  { id: 'TODO', title: 'To Do', color: 'bg-blue-100' },
  { id: 'IN_PROGRESS', title: 'In Progress', color: 'bg-yellow-100' },
  { id: 'IN_REVIEW', title: 'In Review', color: 'bg-purple-100' },
  { id: 'DONE', title: 'Done', color: 'bg-green-100' },
];

interface KanbanBoardProps {
  projectId: string;
  issues: Issue[];
  onIssueUpdate: () => void;
}

export function KanbanBoard({ projectId, issues, onIssueUpdate }: KanbanBoardProps) {
  const [activeIssue, setActiveIssue] = useState<Issue | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);

  // Group issues by status
  const issuesByStatus = COLUMNS.reduce((acc, column) => {
    acc[column.id] = issues.filter((issue) => issue.status === column.id);
    return acc;
  }, {} as Record<IssueStatus, Issue[]>);

  // Drag sensors
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // 8px movement required to start drag
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  // Drag handlers
  const handleDragStart = useCallback((event: DragStartEvent) => {
    const issue = issues.find((i) => i.id === event.active.id);
    setActiveIssue(issue || null);
  }, [issues]);

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveIssue(null);

    if (!over) return;

    const issueId = active.id as string;
    const newStatus = over.id as IssueStatus;

    // Find the issue
    const issue = issues.find((i) => i.id === issueId);
    if (!issue || issue.status === newStatus) return;

    // Optimistic update
    setIsUpdating(true);

    try {
      await updateIssue(issueId, { status: newStatus });
      toast({
        title: 'Issue updated',
        description: `Moved ${issue.key} to ${newStatus.replace('_', ' ')}`,
      });
      onIssueUpdate();
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to update issue status',
        variant: 'destructive',
      });
    } finally {
      setIsUpdating(false);
    }
  }, [issues, onIssueUpdate]);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-4 h-full overflow-x-auto pb-4">
        {COLUMNS.map((column) => (
          <KanbanColumn
            key={column.id}
            id={column.id}
            title={column.title}
            color={column.color}
            issues={issuesByStatus[column.id] || []}
            isUpdating={isUpdating}
          />
        ))}
      </div>

      {/* Drag Overlay - Shows dragged item */}
      <DragOverlay>
        {activeIssue && (
          <IssueCard issue={activeIssue} isDragging />
        )}
      </DragOverlay>
    </DndContext>
  );
}
```

**Acceptance Criteria:**
- [ ] Board renders 5 status columns
- [ ] Issues grouped by status
- [ ] Drag context set up correctly
- [ ] Active issue tracked during drag
- [ ] Overlay shows dragged card

**Sub-tasks:**
1. **Set up DndContext** - From @dnd-kit/core
2. **Configure sensors** - Pointer and keyboard
3. **Group issues by status** - Organize into columns
4. **Handle drag start** - Track active issue
5. **Handle drag end** - Update status via API
6. **Add drag overlay** - Visual feedback during drag

---

### Task T3.2.2: Create KanbanColumn Component

**ID:** T3.2.2
**Story:** S3.2
**Priority:** High
**Estimated Effort:** 30 minutes

**Description:**
Create the Kanban column component that serves as a drop target and displays issues in a specific status.

**File: frontend/components/codeboard/kanban-column.tsx**
```typescript
'use client';

import { useDroppable } from '@dnd-kit/core';
import { cn } from '@/lib/utils';
import { IssueCard } from './issue-card';
import { Issue, IssueStatus } from '@/types/issue';

interface KanbanColumnProps {
  id: IssueStatus;
  title: string;
  color: string;
  issues: Issue[];
  isUpdating: boolean;
}

export function KanbanColumn({
  id,
  title,
  color,
  issues,
  isUpdating,
}: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id,
  });

  return (
    <div
      className={cn(
        'flex flex-col w-[300px] min-w-[300px] rounded-lg',
        color
      )}
    >
      {/* Column Header */}
      <div className="flex items-center justify-between p-3 border-b">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-sm">{title}</h3>
          <span className="flex items-center justify-center w-6 h-6 text-xs font-medium bg-white rounded-full">
            {issues.length}
          </span>
        </div>
      </div>

      {/* Issue List (Drop Zone) */}
      <div
        ref={setNodeRef}
        className={cn(
          'flex-1 p-2 space-y-2 overflow-y-auto min-h-[200px] transition-colors',
          isOver && 'bg-primary/10 ring-2 ring-primary ring-inset',
          isUpdating && 'opacity-50 pointer-events-none'
        )}
      >
        {issues.length === 0 ? (
          <div className="flex items-center justify-center h-20 text-xs text-muted-foreground">
            No issues
          </div>
        ) : (
          issues.map((issue) => (
            <IssueCard key={issue.id} issue={issue} />
          ))
        )}
      </div>
    </div>
  );
}
```

**Acceptance Criteria:**
- [ ] Column renders with title and count
- [ ] Drop zone highlighted when dragging over
- [ ] Issues listed inside column
- [ ] Empty state when no issues
- [ ] Disabled state during updates

**Sub-tasks:**
1. **Create column container** - Fixed width, colored background
2. **Add column header** - Title and count badge
3. **Set up droppable zone** - useDroppable hook
4. **Add hover state** - Highlight when dragging over
5. **Render issue cards** - Map through issues
6. **Add empty state** - "No issues" message

---

### Task T3.2.3: Create IssueCard Component

**ID:** T3.2.3
**Story:** S3.2
**Priority:** High
**Estimated Effort:** 45 minutes

**Description:**
Create the issue card component displayed in the Kanban board with issue type icon, priority indicator, title, and key.

**File: frontend/components/codeboard/issue-card.tsx**
```typescript
'use client';

import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import {
  Layers,
  BookOpen,
  CheckSquare,
  ListTodo,
  Bug,
  ArrowUp,
  ArrowDown,
  Minus,
  User,
  Bot,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Issue, IssueType, Priority, Assignee } from '@/types/issue';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

// Issue type icons
const TYPE_ICONS: Record<IssueType, React.ComponentType<{ className?: string }>> = {
  EPIC: Layers,
  STORY: BookOpen,
  TASK: CheckSquare,
  SUBTASK: ListTodo,
  BUG: Bug,
};

// Type colors
const TYPE_COLORS: Record<IssueType, string> = {
  EPIC: 'text-purple-600',
  STORY: 'text-green-600',
  TASK: 'text-blue-600',
  SUBTASK: 'text-gray-600',
  BUG: 'text-red-600',
};

// Priority icons and colors
const PRIORITY_CONFIG: Record<Priority, { icon: React.ComponentType<{ className?: string }>; color: string }> = {
  HIGHEST: { icon: ArrowUp, color: 'text-red-600' },
  HIGH: { icon: ArrowUp, color: 'text-orange-600' },
  MEDIUM: { icon: Minus, color: 'text-yellow-600' },
  LOW: { icon: ArrowDown, color: 'text-blue-600' },
  LOWEST: { icon: ArrowDown, color: 'text-gray-400' },
};

interface IssueCardProps {
  issue: Issue;
  isDragging?: boolean;
  onClick?: () => void;
}

export function IssueCard({ issue, isDragging, onClick }: IssueCardProps) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({
    id: issue.id,
  });

  const style = transform
    ? {
        transform: CSS.Translate.toString(transform),
      }
    : undefined;

  const TypeIcon = TYPE_ICONS[issue.type];
  const PriorityIcon = PRIORITY_CONFIG[issue.priority].icon;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={cn(
        'bg-white rounded-lg border shadow-sm p-3 cursor-grab active:cursor-grabbing',
        'hover:border-primary/50 hover:shadow-md transition-all',
        isDragging && 'opacity-50 shadow-lg ring-2 ring-primary',
        onClick && 'cursor-pointer'
      )}
      onClick={onClick}
    >
      {/* Top Row: Type Icon + Key */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Tooltip>
            <TooltipTrigger>
              <TypeIcon className={cn('h-4 w-4', TYPE_COLORS[issue.type])} />
            </TooltipTrigger>
            <TooltipContent>{issue.type}</TooltipContent>
          </Tooltip>
          <span className="text-xs font-medium text-muted-foreground">
            {issue.key}
          </span>
        </div>

        {/* Priority */}
        <Tooltip>
          <TooltipTrigger>
            <PriorityIcon
              className={cn('h-4 w-4', PRIORITY_CONFIG[issue.priority].color)}
            />
          </TooltipTrigger>
          <TooltipContent>{issue.priority}</TooltipContent>
        </Tooltip>
      </div>

      {/* Title */}
      <h4 className="text-sm font-medium line-clamp-2 mb-2">
        {issue.title}
      </h4>

      {/* Bottom Row: Labels + Assignee */}
      <div className="flex items-center justify-between">
        {/* Labels */}
        <div className="flex gap-1 flex-wrap">
          {issue.labels?.split(',').slice(0, 2).map((label) => (
            <Badge key={label} variant="secondary" className="text-xs px-1 py-0">
              {label.trim()}
            </Badge>
          ))}
        </div>

        {/* Assignee */}
        <Tooltip>
          <TooltipTrigger>
            {issue.assignee === 'AI' ? (
              <Bot className="h-4 w-4 text-purple-600" />
            ) : issue.assignee === 'HUMAN' ? (
              <User className="h-4 w-4 text-blue-600" />
            ) : (
              <User className="h-4 w-4 text-gray-300" />
            )}
          </TooltipTrigger>
          <TooltipContent>
            {issue.assignee === 'UNASSIGNED' ? 'Unassigned' : `Assigned to ${issue.assignee}`}
          </TooltipContent>
        </Tooltip>
      </div>

      {/* Story Points (if set) */}
      {issue.storyPoints && (
        <div className="mt-2 pt-2 border-t">
          <span className="text-xs text-muted-foreground">
            {issue.storyPoints} pts
          </span>
        </div>
      )}
    </div>
  );
}
```

**Visual Design:**
```
┌─────────────────────────────────────┐
│ 📘 PM-123                      ⬆️   │
│                                     │
│ Implement user authentication       │
│                                     │
│ [auth] [security]              🤖   │
│─────────────────────────────────────│
│ 5 pts                               │
└─────────────────────────────────────┘
```

**Acceptance Criteria:**
- [ ] Card displays issue type icon with color
- [ ] Issue key shown prominently
- [ ] Priority indicator with icon
- [ ] Title with line clamp (2 lines)
- [ ] Labels shown as badges
- [ ] Assignee icon (AI/Human/Unassigned)
- [ ] Draggable with visual feedback
- [ ] Hover state with shadow

**Sub-tasks:**
1. **Set up draggable** - useDraggable hook
2. **Add type icon** - Colored by type
3. **Add priority icon** - Arrow up/down/minus
4. **Display title** - With truncation
5. **Show labels** - As small badges
6. **Show assignee** - AI/Human/Unassigned icon
7. **Add story points** - If set
8. **Style drag state** - Opacity, shadow, cursor

---

### Task T3.2.4: Implement Drag-and-Drop

**ID:** T3.2.4
**Story:** S3.2
**Priority:** High
**Estimated Effort:** 1 hour

**Description:**
Complete the drag-and-drop implementation using @dnd-kit library including smooth animations, visual feedback, and accessibility features.

**Dependencies:**
```bash
npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities
```

**Enhanced Implementation:**
```typescript
// Additional features for smooth DnD

// 1. Add smooth drop animation
import { defaultDropAnimation, DragOverlay } from '@dnd-kit/core';

const dropAnimation = {
  ...defaultDropAnimation,
  dragSourceOpacity: 0.5,
};

// 2. Add keyboard support
const keyboardCoordinateGetter = (
  event: KeyboardEvent,
  { currentCoordinates }
) => {
  const step = 25;
  switch (event.key) {
    case 'ArrowRight':
      return { x: currentCoordinates.x + step, y: currentCoordinates.y };
    case 'ArrowLeft':
      return { x: currentCoordinates.x - step, y: currentCoordinates.y };
    case 'ArrowDown':
      return { x: currentCoordinates.x, y: currentCoordinates.y + step };
    case 'ArrowUp':
      return { x: currentCoordinates.x, y: currentCoordinates.y - step };
    default:
      return undefined;
  }
};

// 3. Add touch support
const touchSensor = useSensor(TouchSensor, {
  activationConstraint: {
    delay: 250,
    tolerance: 5,
  },
});

// 4. Accessibility announcements
const announcements = {
  onDragStart({ active }) {
    return `Picked up issue ${active.data.current?.issue.key}`;
  },
  onDragOver({ active, over }) {
    if (over) {
      return `Issue ${active.data.current?.issue.key} is over ${over.id}`;
    }
    return `Issue ${active.data.current?.issue.key} is no longer over a droppable area`;
  },
  onDragEnd({ active, over }) {
    if (over) {
      return `Issue ${active.data.current?.issue.key} was dropped into ${over.id}`;
    }
    return `Issue ${active.data.current?.issue.key} was dropped`;
  },
  onDragCancel({ active }) {
    return `Dragging was cancelled. Issue ${active.data.current?.issue.key} was dropped.`;
  },
};
```

**Acceptance Criteria:**
- [ ] Drag starts after 8px movement
- [ ] Smooth animation on drop
- [ ] Visual overlay during drag
- [ ] Keyboard navigation support
- [ ] Touch device support
- [ ] Screen reader announcements
- [ ] Status updates on drop

**Sub-tasks:**
1. **Install @dnd-kit packages** - core, sortable, utilities
2. **Configure pointer sensor** - With activation constraint
3. **Configure keyboard sensor** - Arrow key navigation
4. **Configure touch sensor** - With delay for mobile
5. **Add drop animation** - Smooth transition
6. **Add accessibility announcements** - Screen reader support
7. **Test on mobile** - Touch drag works

---

### Task T3.2.5: Connect to API

**ID:** T3.2.5
**Story:** S3.2
**Priority:** High
**Estimated Effort:** 30 minutes

**Description:**
Create the useIssues hook and API functions to fetch issues and update status on drag-and-drop.

**File: frontend/hooks/use-issues.ts**
```typescript
'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Issue, IssueFilters, IssueListResponse } from '@/types/issue';
import { fetchIssues, updateIssue } from '@/lib/api/issues';

export function useIssues(projectId: string, filters?: IssueFilters) {
  const queryClient = useQueryClient();

  // Fetch issues
  const query = useQuery({
    queryKey: ['issues', projectId, filters],
    queryFn: () => fetchIssues(projectId, filters),
    enabled: !!projectId,
    staleTime: 30000, // 30 seconds
  });

  // Update issue mutation with optimistic updates
  const updateMutation = useMutation({
    mutationFn: ({ issueId, data }: { issueId: string; data: Partial<Issue> }) =>
      updateIssue(issueId, data),
    onMutate: async ({ issueId, data }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['issues', projectId] });

      // Snapshot previous value
      const previousIssues = queryClient.getQueryData<IssueListResponse>([
        'issues',
        projectId,
        filters,
      ]);

      // Optimistically update
      if (previousIssues) {
        queryClient.setQueryData<IssueListResponse>(
          ['issues', projectId, filters],
          {
            ...previousIssues,
            items: previousIssues.items.map((issue) =>
              issue.id === issueId ? { ...issue, ...data } : issue
            ),
          }
        );
      }

      return { previousIssues };
    },
    onError: (err, variables, context) => {
      // Rollback on error
      if (context?.previousIssues) {
        queryClient.setQueryData(
          ['issues', projectId, filters],
          context.previousIssues
        );
      }
    },
    onSettled: () => {
      // Refetch after mutation
      queryClient.invalidateQueries({ queryKey: ['issues', projectId] });
    },
  });

  return {
    issues: query.data?.items || [],
    total: query.data?.total || 0,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    updateIssue: updateMutation.mutate,
    isUpdating: updateMutation.isPending,
  };
}
```

**File: frontend/lib/api/issues.ts**
```typescript
import { Issue, IssueFilters, IssueListResponse, IssueCreate, IssueUpdate } from '@/types/issue';

const API_BASE = '/api/codeboard';

export async function fetchIssues(
  projectId: string,
  filters?: IssueFilters
): Promise<IssueListResponse> {
  const params = new URLSearchParams();

  if (filters?.type?.length) {
    filters.type.forEach((t) => params.append('type', t));
  }
  if (filters?.status?.length) {
    filters.status.forEach((s) => params.append('status', s));
  }
  if (filters?.priority?.length) {
    filters.priority.forEach((p) => params.append('priority', p));
  }
  if (filters?.assignee?.length) {
    filters.assignee.forEach((a) => params.append('assignee', a));
  }
  if (filters?.search) {
    params.set('search', filters.search);
  }

  const url = `${API_BASE}/projects/${projectId}/issues?${params.toString()}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error('Failed to fetch issues');
  }

  return response.json();
}

export async function createIssue(
  projectId: string,
  data: IssueCreate
): Promise<Issue> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/issues`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error('Failed to create issue');
  }

  return response.json();
}

export async function updateIssue(
  issueId: string,
  data: IssueUpdate
): Promise<Issue> {
  const response = await fetch(`${API_BASE}/issues/${issueId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error('Failed to update issue');
  }

  return response.json();
}

export async function deleteIssue(issueId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/issues/${issueId}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new Error('Failed to delete issue');
  }
}
```

**Acceptance Criteria:**
- [ ] useIssues hook fetches issues for project
- [ ] Filters passed as query parameters
- [ ] Optimistic updates on status change
- [ ] Rollback on error
- [ ] Cache invalidation after mutation

**Sub-tasks:**
1. **Create API functions** - fetch, create, update, delete
2. **Create useIssues hook** - With React Query
3. **Implement optimistic updates** - Instant UI feedback
4. **Add error rollback** - Revert on failure
5. **Add cache invalidation** - Refresh after changes

---

## Story 3.3: List View

**ID:** S3.3
**Epic:** E3
**Priority:** Medium
**Description:** Implement a table-based list view as an alternative to the Kanban board, with sorting and pagination capabilities.

---

### Task T3.3.1: Create IssueList Component

**ID:** T3.3.1
**Story:** S3.3
**Priority:** Medium
**Estimated Effort:** 2 hours

**Description:**
Create the main table-based list view component that displays issues in a sortable, paginated table format. This provides an alternative view to the Kanban board for users who prefer a traditional list interface.

**Technical Requirements:**
- Use shadcn/ui Table component
- Support column visibility toggle
- Fixed header with scroll body
- Responsive design with horizontal scroll on mobile

**File: frontend/components/codeboard/issue-list.tsx**
```typescript
'use client';

import { useState } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { IssueRow } from './issue-row';
import { Issue, SortConfig } from '@/types/codeboard';
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface IssueListProps {
  issues: Issue[];
  onIssueClick: (issue: Issue) => void;
  onStatusChange: (issueId: string, status: string) => void;
}

const columns = [
  { key: 'key', label: 'Key', sortable: true, width: '100px' },
  { key: 'type', label: 'Type', sortable: true, width: '80px' },
  { key: 'title', label: 'Summary', sortable: true },
  { key: 'status', label: 'Status', sortable: true, width: '120px' },
  { key: 'priority', label: 'Priority', sortable: true, width: '100px' },
  { key: 'assignee', label: 'Assignee', sortable: true, width: '120px' },
  { key: 'createdAt', label: 'Created', sortable: true, width: '100px' },
];

export function IssueList({ issues, onIssueClick, onStatusChange }: IssueListProps) {
  const [sortConfig, setSortConfig] = useState<SortConfig>({
    key: 'createdAt',
    direction: 'desc',
  });

  const handleSort = (key: string) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc',
    }));
  };

  const sortedIssues = [...issues].sort((a, b) => {
    const aVal = a[sortConfig.key as keyof Issue];
    const bVal = b[sortConfig.key as keyof Issue];
    const direction = sortConfig.direction === 'asc' ? 1 : -1;
    return aVal < bVal ? -direction : direction;
  });

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map(col => (
              <TableHead key={col.key} style={{ width: col.width }}>
                {col.sortable ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleSort(col.key)}
                    className="h-8 flex items-center gap-1"
                  >
                    {col.label}
                    {sortConfig.key === col.key ? (
                      sortConfig.direction === 'asc' ? <ArrowUp className="h-4 w-4" /> : <ArrowDown className="h-4 w-4" />
                    ) : (
                      <ArrowUpDown className="h-4 w-4 opacity-50" />
                    )}
                  </Button>
                ) : (
                  col.label
                )}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedIssues.map(issue => (
            <IssueRow
              key={issue.id}
              issue={issue}
              onClick={() => onIssueClick(issue)}
              onStatusChange={onStatusChange}
            />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

**Acceptance Criteria:**
- [ ] Table displays all issue columns
- [ ] Columns are sortable by clicking headers
- [ ] Sort direction indicator shows current sort
- [ ] Table scrolls horizontally on small screens
- [ ] Row click opens issue detail

**Sub-tasks:**
1. **Create table structure** - With proper column widths
2. **Add sort indicators** - Visual feedback for sort state
3. **Implement sort logic** - Client-side sorting
4. **Add responsive styles** - Mobile scroll support

---

### Task T3.3.2: Create IssueRow Component

**ID:** T3.3.2
**Story:** S3.3
**Priority:** Medium
**Estimated Effort:** 1.5 hours

**Description:**
Create the individual row component for the issue list table, displaying all issue fields with appropriate formatting and inline status editing.

**File: frontend/components/codeboard/issue-row.tsx**
```typescript
'use client';

import { TableCell, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Issue } from '@/types/codeboard';
import { formatDistanceToNow } from 'date-fns';
import { IssueTypeIcon } from './issue-type-icon';
import { PriorityBadge } from './priority-badge';
import { StatusDropdown } from './status-dropdown';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';

interface IssueRowProps {
  issue: Issue;
  onClick: () => void;
  onStatusChange: (issueId: string, status: string) => void;
}

export function IssueRow({ issue, onClick, onStatusChange }: IssueRowProps) {
  const handleStatusChange = (status: string) => {
    onStatusChange(issue.id, status);
  };

  return (
    <TableRow
      className="cursor-pointer hover:bg-muted/50"
      onClick={onClick}
    >
      <TableCell className="font-medium text-primary">
        {issue.key}
      </TableCell>
      <TableCell>
        <IssueTypeIcon type={issue.type} />
      </TableCell>
      <TableCell className="max-w-[300px] truncate">
        {issue.title}
      </TableCell>
      <TableCell onClick={e => e.stopPropagation()}>
        <StatusDropdown
          status={issue.status}
          onChange={handleStatusChange}
        />
      </TableCell>
      <TableCell>
        <PriorityBadge priority={issue.priority} />
      </TableCell>
      <TableCell>
        {issue.assignee ? (
          <div className="flex items-center gap-2">
            <Avatar className="h-6 w-6">
              <AvatarFallback className="text-xs">
                {issue.assignee === 'AI' ? '🤖' : issue.assignee[0]}
              </AvatarFallback>
            </Avatar>
            <span className="text-sm">{issue.assignee}</span>
          </div>
        ) : (
          <span className="text-muted-foreground text-sm">Unassigned</span>
        )}
      </TableCell>
      <TableCell className="text-muted-foreground text-sm">
        {formatDistanceToNow(new Date(issue.createdAt), { addSuffix: true })}
      </TableCell>
    </TableRow>
  );
}
```

**Acceptance Criteria:**
- [ ] Row displays all issue fields
- [ ] Issue key is clickable and styled as link
- [ ] Type shows appropriate icon
- [ ] Status has inline dropdown for quick change
- [ ] Priority shows color-coded badge
- [ ] Assignee shows avatar
- [ ] Date shows relative time

**Sub-tasks:**
1. **Create row layout** - With all columns
2. **Add type icon** - Visual type indicator
3. **Add inline status dropdown** - Quick status change
4. **Format dates** - Relative time display

---

### Task T3.3.3: Add Sorting Functionality

**ID:** T3.3.3
**Story:** S3.3
**Priority:** Medium
**Estimated Effort:** 1 hour

**Description:**
Implement full sorting functionality including multi-column sort, sort persistence, and server-side sort support for large datasets.

**Technical Requirements:**
- Default sort by created date descending
- Click column header to toggle sort
- Shift+click for secondary sort
- Persist sort preference in localStorage
- Support server-side sorting via query params

**Implementation:**
```typescript
// Sort configuration type
interface SortConfig {
  key: string;
  direction: 'asc' | 'desc';
}

// Hook for managing sort state
function useSortState(defaultSort: SortConfig) {
  const [sortConfig, setSortConfig] = useState<SortConfig>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('issue-list-sort');
      return saved ? JSON.parse(saved) : defaultSort;
    }
    return defaultSort;
  });

  useEffect(() => {
    localStorage.setItem('issue-list-sort', JSON.stringify(sortConfig));
  }, [sortConfig]);

  return [sortConfig, setSortConfig] as const;
}
```

**Acceptance Criteria:**
- [ ] Clicking column toggles sort direction
- [ ] Sort preference persists across sessions
- [ ] Multiple columns can be sorted
- [ ] Server-side sort params passed to API

**Sub-tasks:**
1. **Create sort hook** - With localStorage persistence
2. **Implement toggle logic** - Asc/desc switching
3. **Add to API calls** - Query param support

---

### Task T3.3.4: Add Pagination

**ID:** T3.3.4
**Story:** S3.3
**Priority:** Medium
**Estimated Effort:** 1.5 hours

**Description:**
Implement pagination for the issue list with page size selection and keyboard navigation.

**File: frontend/components/codeboard/pagination.tsx**
```typescript
'use client';

import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}

const pageSizeOptions = [10, 25, 50, 100];

export function Pagination({
  currentPage,
  totalPages,
  pageSize,
  totalItems,
  onPageChange,
  onPageSizeChange,
}: PaginationProps) {
  const startItem = (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalItems);

  return (
    <div className="flex items-center justify-between px-2 py-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Showing {startItem}-{endItem} of {totalItems}</span>
        <Select
          value={pageSize.toString()}
          onValueChange={(v) => onPageSizeChange(Number(v))}
        >
          <SelectTrigger className="w-[70px] h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {pageSizeOptions.map(size => (
              <SelectItem key={size} value={size.toString()}>
                {size}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span>per page</span>
      </div>

      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => onPageChange(1)}
          disabled={currentPage === 1}
        >
          <ChevronsLeft className="h-4 w-4" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage === 1}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="px-4 text-sm">
          Page {currentPage} of {totalPages}
        </span>
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage === totalPages}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => onPageChange(totalPages)}
          disabled={currentPage === totalPages}
        >
          <ChevronsRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
```

**Acceptance Criteria:**
- [ ] Page size selector with common options
- [ ] First/last page buttons
- [ ] Previous/next page buttons
- [ ] Current page indicator
- [ ] Disabled states at boundaries
- [ ] Keyboard navigation (arrow keys)

**Sub-tasks:**
1. **Create Pagination component** - Navigation buttons
2. **Add page size selector** - Dropdown with options
3. **Show item range** - "Showing 1-25 of 100"
4. **Add keyboard support** - Arrow key navigation

---

## Story 3.4: Filter Bar

**ID:** S3.4
**Epic:** E3
**Priority:** Medium
**Description:** Implement comprehensive filtering capabilities for issues including type, status, priority, assignee, and text search.

---

### Task T3.4.1: Create FilterBar Component

**ID:** T3.4.1
**Story:** S3.4
**Priority:** Medium
**Estimated Effort:** 1.5 hours

**Description:**
Create the main filter bar container component that holds all filter controls and manages filter state.

**File: frontend/components/codeboard/filter-bar.tsx**
```typescript
'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { X, SlidersHorizontal } from 'lucide-react';
import { TypeFilter } from './filters/type-filter';
import { StatusFilter } from './filters/status-filter';
import { PriorityFilter } from './filters/priority-filter';
import { AssigneeFilter } from './filters/assignee-filter';
import { SearchInput } from './filters/search-input';
import { IssueFilters } from '@/types/codeboard';

interface FilterBarProps {
  filters: IssueFilters;
  onFiltersChange: (filters: IssueFilters) => void;
}

export function FilterBar({ filters, onFiltersChange }: FilterBarProps) {
  const activeFilterCount = Object.values(filters).filter(v =>
    Array.isArray(v) ? v.length > 0 : v !== undefined && v !== ''
  ).length;

  const clearAllFilters = () => {
    onFiltersChange({
      types: [],
      statuses: [],
      priorities: [],
      assignee: undefined,
      search: '',
    });
  };

  return (
    <div className="flex flex-wrap items-center gap-2 p-4 border-b bg-muted/30">
      <SearchInput
        value={filters.search || ''}
        onChange={(search) => onFiltersChange({ ...filters, search })}
      />

      <div className="h-6 w-px bg-border" />

      <TypeFilter
        selected={filters.types || []}
        onChange={(types) => onFiltersChange({ ...filters, types })}
      />
      <StatusFilter
        selected={filters.statuses || []}
        onChange={(statuses) => onFiltersChange({ ...filters, statuses })}
      />
      <PriorityFilter
        selected={filters.priorities || []}
        onChange={(priorities) => onFiltersChange({ ...filters, priorities })}
      />
      <AssigneeFilter
        selected={filters.assignee}
        onChange={(assignee) => onFiltersChange({ ...filters, assignee })}
      />

      {activeFilterCount > 0 && (
        <>
          <div className="h-6 w-px bg-border" />
          <Button
            variant="ghost"
            size="sm"
            onClick={clearAllFilters}
            className="text-muted-foreground"
          >
            <X className="h-4 w-4 mr-1" />
            Clear all ({activeFilterCount})
          </Button>
        </>
      )}
    </div>
  );
}
```

**Acceptance Criteria:**
- [ ] Filter bar displays all filter controls
- [ ] Active filter count displayed
- [ ] Clear all button resets all filters
- [ ] Responsive layout on mobile
- [ ] Filters persist in URL query params

**Sub-tasks:**
1. **Create container layout** - Flex wrap design
2. **Add filter count badge** - Show active filters
3. **Implement clear all** - Reset all filters
4. **Add URL sync** - Query param persistence

---

### Task T3.4.2: Add Type Filter Dropdown

**ID:** T3.4.2
**Story:** S3.4
**Priority:** Medium
**Estimated Effort:** 45 minutes

**Description:**
Create a multi-select dropdown for filtering issues by type (Epic, Story, Task, Bug, Subtask).

**File: frontend/components/codeboard/filters/type-filter.tsx**
```typescript
'use client';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ChevronDown } from 'lucide-react';
import { IssueType } from '@/types/codeboard';
import { IssueTypeIcon } from '../issue-type-icon';

const issueTypes: IssueType[] = ['EPIC', 'STORY', 'TASK', 'BUG', 'SUBTASK'];

interface TypeFilterProps {
  selected: IssueType[];
  onChange: (types: IssueType[]) => void;
}

export function TypeFilter({ selected, onChange }: TypeFilterProps) {
  const handleToggle = (type: IssueType) => {
    if (selected.includes(type)) {
      onChange(selected.filter(t => t !== type));
    } else {
      onChange([...selected, type]);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-8">
          Type
          {selected.length > 0 && (
            <span className="ml-1 rounded-full bg-primary px-1.5 text-xs text-primary-foreground">
              {selected.length}
            </span>
          )}
          <ChevronDown className="ml-1 h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {issueTypes.map(type => (
          <DropdownMenuCheckboxItem
            key={type}
            checked={selected.includes(type)}
            onCheckedChange={() => handleToggle(type)}
          >
            <IssueTypeIcon type={type} className="mr-2" />
            {type.charAt(0) + type.slice(1).toLowerCase()}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

**Acceptance Criteria:**
- [ ] Dropdown shows all issue types
- [ ] Each type has its icon
- [ ] Multi-select with checkboxes
- [ ] Badge shows selected count
- [ ] Clicking outside closes dropdown

**Sub-tasks:**
1. **Create dropdown component** - Multi-select
2. **Add type icons** - Visual indicators
3. **Show selection count** - Badge on button

---

### Task T3.4.3: Add Status Filter Dropdown

**ID:** T3.4.3
**Story:** S3.4
**Priority:** Medium
**Estimated Effort:** 45 minutes

**Description:**
Create a multi-select dropdown for filtering issues by status with color-coded indicators.

**File: frontend/components/codeboard/filters/status-filter.tsx**
```typescript
'use client';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ChevronDown } from 'lucide-react';
import { IssueStatus } from '@/types/codeboard';

const statusConfig: Record<IssueStatus, { label: string; color: string }> = {
  BACKLOG: { label: 'Backlog', color: 'bg-gray-400' },
  TODO: { label: 'To Do', color: 'bg-blue-400' },
  IN_PROGRESS: { label: 'In Progress', color: 'bg-yellow-400' },
  IN_REVIEW: { label: 'In Review', color: 'bg-purple-400' },
  DONE: { label: 'Done', color: 'bg-green-400' },
};

interface StatusFilterProps {
  selected: IssueStatus[];
  onChange: (statuses: IssueStatus[]) => void;
}

export function StatusFilter({ selected, onChange }: StatusFilterProps) {
  const handleToggle = (status: IssueStatus) => {
    if (selected.includes(status)) {
      onChange(selected.filter(s => s !== status));
    } else {
      onChange([...selected, status]);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-8">
          Status
          {selected.length > 0 && (
            <span className="ml-1 rounded-full bg-primary px-1.5 text-xs text-primary-foreground">
              {selected.length}
            </span>
          )}
          <ChevronDown className="ml-1 h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {Object.entries(statusConfig).map(([status, config]) => (
          <DropdownMenuCheckboxItem
            key={status}
            checked={selected.includes(status as IssueStatus)}
            onCheckedChange={() => handleToggle(status as IssueStatus)}
          >
            <span className={`mr-2 h-2 w-2 rounded-full ${config.color}`} />
            {config.label}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

**Acceptance Criteria:**
- [ ] Dropdown shows all statuses
- [ ] Each status has color dot
- [ ] Multi-select with checkboxes
- [ ] Badge shows selected count

**Sub-tasks:**
1. **Create dropdown component** - Multi-select
2. **Add status colors** - Color-coded dots
3. **Show selection count** - Badge on button

---

### Task T3.4.4: Add Priority Filter Dropdown

**ID:** T3.4.4
**Story:** S3.4
**Priority:** Medium
**Estimated Effort:** 45 minutes

**Description:**
Create a multi-select dropdown for filtering issues by priority level.

**File: frontend/components/codeboard/filters/priority-filter.tsx**
```typescript
'use client';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ChevronDown } from 'lucide-react';
import { Priority } from '@/types/codeboard';
import { PriorityBadge } from '../priority-badge';

const priorities: Priority[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];

interface PriorityFilterProps {
  selected: Priority[];
  onChange: (priorities: Priority[]) => void;
}

export function PriorityFilter({ selected, onChange }: PriorityFilterProps) {
  const handleToggle = (priority: Priority) => {
    if (selected.includes(priority)) {
      onChange(selected.filter(p => p !== priority));
    } else {
      onChange([...selected, priority]);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-8">
          Priority
          {selected.length > 0 && (
            <span className="ml-1 rounded-full bg-primary px-1.5 text-xs text-primary-foreground">
              {selected.length}
            </span>
          )}
          <ChevronDown className="ml-1 h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {priorities.map(priority => (
          <DropdownMenuCheckboxItem
            key={priority}
            checked={selected.includes(priority)}
            onCheckedChange={() => handleToggle(priority)}
          >
            <PriorityBadge priority={priority} className="mr-2" />
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

**Acceptance Criteria:**
- [ ] Dropdown shows all priority levels
- [ ] Each priority has color-coded badge
- [ ] Multi-select with checkboxes
- [ ] Badge shows selected count

**Sub-tasks:**
1. **Create dropdown component** - Multi-select
2. **Add priority badges** - Color-coded
3. **Show selection count** - Badge on button

---

### Task T3.4.5: Add Assignee Filter

**ID:** T3.4.5
**Story:** S3.4
**Priority:** Medium
**Estimated Effort:** 45 minutes

**Description:**
Create a filter for assignee with special support for AI-assigned vs human-assigned issues.

**File: frontend/components/codeboard/filters/assignee-filter.tsx**
```typescript
'use client';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ChevronDown, Bot, User, Users } from 'lucide-react';

type AssigneeFilter = 'all' | 'ai' | 'human' | 'unassigned';

interface AssigneeFilterProps {
  selected?: AssigneeFilter;
  onChange: (assignee: AssigneeFilter | undefined) => void;
}

export function AssigneeFilter({ selected, onChange }: AssigneeFilterProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-8">
          Assignee
          {selected && selected !== 'all' && (
            <span className="ml-1 rounded-full bg-primary px-1.5 text-xs text-primary-foreground">
              1
            </span>
          )}
          <ChevronDown className="ml-1 h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuRadioGroup
          value={selected || 'all'}
          onValueChange={(v) => onChange(v === 'all' ? undefined : v as AssigneeFilter)}
        >
          <DropdownMenuRadioItem value="all">
            <Users className="mr-2 h-4 w-4" />
            All
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="ai">
            <Bot className="mr-2 h-4 w-4" />
            AI Assigned
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="human">
            <User className="mr-2 h-4 w-4" />
            Human Assigned
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="unassigned">
            <span className="mr-2 h-4 w-4 opacity-50">—</span>
            Unassigned
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

**Acceptance Criteria:**
- [ ] Radio selection (single choice)
- [ ] Options: All, AI, Human, Unassigned
- [ ] Icons for each option
- [ ] Badge when filtered

**Sub-tasks:**
1. **Create radio dropdown** - Single select
2. **Add AI/Human options** - Special filtering
3. **Add icons** - Visual distinction

---

### Task T3.4.6: Add Text Search

**ID:** T3.4.6
**Story:** S3.4
**Priority:** Medium
**Estimated Effort:** 1 hour

**Description:**
Implement debounced text search input for filtering issues by title and description.

**File: frontend/components/codeboard/filters/search-input.tsx**
```typescript
'use client';

import { useState, useEffect } from 'react';
import { Input } from '@/components/ui/input';
import { Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export function SearchInput({ value, onChange, placeholder = 'Search issues...' }: SearchInputProps) {
  const [localValue, setLocalValue] = useState(value);

  // Debounce the search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localValue !== value) {
        onChange(localValue);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [localValue, value, onChange]);

  // Sync external value changes
  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  const handleClear = () => {
    setLocalValue('');
    onChange('');
  };

  return (
    <div className="relative flex-1 max-w-xs">
      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
      <Input
        type="text"
        placeholder={placeholder}
        value={localValue}
        onChange={(e) => setLocalValue(e.target.value)}
        className="pl-8 pr-8 h-8"
      />
      {localValue && (
        <Button
          variant="ghost"
          size="icon"
          className="absolute right-1 top-1/2 -translate-y-1/2 h-6 w-6"
          onClick={handleClear}
        >
          <X className="h-3 w-3" />
        </Button>
      )}
    </div>
  );
}
```

**Acceptance Criteria:**
- [ ] Search icon in input
- [ ] 300ms debounce on typing
- [ ] Clear button when has value
- [ ] Placeholder text
- [ ] Keyboard shortcut (/) to focus

**Sub-tasks:**
1. **Create input component** - With search icon
2. **Implement debounce** - 300ms delay
3. **Add clear button** - Reset search
4. **Add keyboard shortcut** - "/" to focus

---

## Story 3.5: Issue Detail View

**ID:** S3.5
**Epic:** E3
**Priority:** High
**Description:** Create the full issue detail view with description editing, activity log, linked items, and comments.

---

### Task T3.5.1: Create IssueDetail Component

**ID:** T3.5.1
**Story:** S3.5
**Priority:** High
**Estimated Effort:** 2 hours

**Description:**
Create the main issue detail component that displays full issue information in a modal or slide-over panel.

**File: frontend/components/codeboard/issue-detail.tsx**
```typescript
'use client';

import { useState } from 'react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Issue } from '@/types/codeboard';
import { IssueTypeIcon } from './issue-type-icon';
import { StatusDropdown } from './status-dropdown';
import { PriorityDropdown } from './priority-dropdown';
import { DescriptionSection } from './description-section';
import { ActivityLog } from './activity-log';
import { LinkedItems } from './linked-items';
import { CommentsSection } from './comments-section';
import { X, Link2, MessageSquare, History } from 'lucide-react';

interface IssueDetailProps {
  issue: Issue | null;
  open: boolean;
  onClose: () => void;
  onUpdate: (issueId: string, updates: Partial<Issue>) => void;
}

export function IssueDetail({ issue, open, onClose, onUpdate }: IssueDetailProps) {
  if (!issue) return null;

  const handleStatusChange = (status: string) => {
    onUpdate(issue.id, { status: status as Issue['status'] });
  };

  const handlePriorityChange = (priority: string) => {
    onUpdate(issue.id, { priority: priority as Issue['priority'] });
  };

  const handleDescriptionSave = (description: string) => {
    onUpdate(issue.id, { description });
  };

  return (
    <Sheet open={open} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-[600px] sm:max-w-[600px] overflow-y-auto">
        <SheetHeader className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <IssueTypeIcon type={issue.type} size="lg" />
              <Badge variant="outline">{issue.key}</Badge>
            </div>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <SheetTitle className="text-xl font-semibold">
            {issue.title}
          </SheetTitle>
          <div className="flex items-center gap-4">
            <StatusDropdown status={issue.status} onChange={handleStatusChange} />
            <PriorityDropdown priority={issue.priority} onChange={handlePriorityChange} />
          </div>
        </SheetHeader>

        <div className="mt-6">
          <Tabs defaultValue="details">
            <TabsList>
              <TabsTrigger value="details">Details</TabsTrigger>
              <TabsTrigger value="activity">
                <History className="h-4 w-4 mr-1" />
                Activity
              </TabsTrigger>
              <TabsTrigger value="links">
                <Link2 className="h-4 w-4 mr-1" />
                Links
              </TabsTrigger>
              <TabsTrigger value="comments">
                <MessageSquare className="h-4 w-4 mr-1" />
                Comments
              </TabsTrigger>
            </TabsList>

            <TabsContent value="details" className="mt-4">
              <DescriptionSection
                description={issue.description}
                onSave={handleDescriptionSave}
              />
            </TabsContent>

            <TabsContent value="activity" className="mt-4">
              <ActivityLog issueId={issue.id} />
            </TabsContent>

            <TabsContent value="links" className="mt-4">
              <LinkedItems issue={issue} />
            </TabsContent>

            <TabsContent value="comments" className="mt-4">
              <CommentsSection issueId={issue.id} />
            </TabsContent>
          </Tabs>
        </div>
      </SheetContent>
    </Sheet>
  );
}
```

**Acceptance Criteria:**
- [ ] Slide-over panel with issue details
- [ ] Issue key and type displayed
- [ ] Inline status and priority editing
- [ ] Tab navigation for sections
- [ ] Close button and escape key close

**Sub-tasks:**
1. **Create Sheet component** - Slide-over panel
2. **Add header section** - Key, type, title
3. **Add status/priority dropdowns** - Inline editing
4. **Implement tabs** - Details, Activity, Links, Comments

---

### Task T3.5.2: Create DescriptionSection

**ID:** T3.5.2
**Story:** S3.5
**Priority:** High
**Estimated Effort:** 1.5 hours

**Description:**
Create the description section with Markdown rendering and inline editing capabilities.

**File: frontend/components/codeboard/description-section.tsx**
```typescript
'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Edit2, Check, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

interface DescriptionSectionProps {
  description?: string;
  onSave: (description: string) => void;
}

export function DescriptionSection({ description, onSave }: DescriptionSectionProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(description || '');

  const handleSave = () => {
    onSave(editValue);
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditValue(description || '');
    setIsEditing(false);
  };

  if (isEditing) {
    return (
      <div className="space-y-2">
        <Textarea
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          placeholder="Add a description..."
          className="min-h-[200px] font-mono text-sm"
        />
        <div className="flex gap-2">
          <Button size="sm" onClick={handleSave}>
            <Check className="h-4 w-4 mr-1" />
            Save
          </Button>
          <Button size="sm" variant="outline" onClick={handleCancel}>
            <X className="h-4 w-4 mr-1" />
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="group relative">
      <Button
        variant="ghost"
        size="icon"
        className="absolute right-0 top-0 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={() => setIsEditing(true)}
      >
        <Edit2 className="h-4 w-4" />
      </Button>
      {description ? (
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown>{description}</ReactMarkdown>
        </div>
      ) : (
        <p
          className="text-muted-foreground cursor-pointer hover:text-foreground"
          onClick={() => setIsEditing(true)}
        >
          Click to add a description...
        </p>
      )}
    </div>
  );
}
```

**Acceptance Criteria:**
- [ ] Markdown rendering for description
- [ ] Edit button on hover
- [ ] Full textarea editor
- [ ] Save and cancel buttons
- [ ] Empty state placeholder

**Sub-tasks:**
1. **Add Markdown rendering** - react-markdown
2. **Create edit mode** - Textarea with controls
3. **Add save/cancel** - With keyboard shortcuts

---

### Task T3.5.3: Create ActivityLog Component

**ID:** T3.5.3
**Story:** S3.5
**Priority:** Medium
**Estimated Effort:** 1.5 hours

**Description:**
Create an activity timeline showing all changes and events for an issue.

**File: frontend/components/codeboard/activity-log.tsx**
```typescript
'use client';

import { useQuery } from '@tanstack/react-query';
import { formatDistanceToNow } from 'date-fns';
import { Activity } from '@/types/codeboard';
import { Skeleton } from '@/components/ui/skeleton';
import { ArrowRight, MessageSquare, GitCommit, Edit2, Plus } from 'lucide-react';

const activityIcons: Record<Activity['type'], React.ReactNode> = {
  STATUS_CHANGE: <ArrowRight className="h-4 w-4" />,
  COMMENT: <MessageSquare className="h-4 w-4" />,
  COMMIT: <GitCommit className="h-4 w-4" />,
  DESCRIPTION_CHANGE: <Edit2 className="h-4 w-4" />,
  CREATED: <Plus className="h-4 w-4" />,
};

interface ActivityLogProps {
  issueId: string;
}

export function ActivityLog({ issueId }: ActivityLogProps) {
  const { data: activities, isLoading } = useQuery({
    queryKey: ['activities', issueId],
    queryFn: () => fetchActivities(issueId),
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="flex gap-3">
            <Skeleton className="h-8 w-8 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/4" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {activities?.map((activity) => (
        <div key={activity.id} className="flex gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
            {activityIcons[activity.type]}
          </div>
          <div className="flex-1">
            <p className="text-sm">
              <span className="font-medium">{activity.actor}</span>
              {' '}
              {activity.description}
            </p>
            <p className="text-xs text-muted-foreground">
              {formatDistanceToNow(new Date(activity.createdAt), { addSuffix: true })}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

async function fetchActivities(issueId: string): Promise<Activity[]> {
  const res = await fetch(`/api/codeboard/issues/${issueId}/activities`);
  return res.json();
}
```

**Acceptance Criteria:**
- [ ] Timeline layout with icons
- [ ] Different icons per activity type
- [ ] Relative timestamps
- [ ] Loading skeleton
- [ ] Actor name displayed

**Sub-tasks:**
1. **Create timeline layout** - Vertical list
2. **Add activity icons** - Per type
3. **Fetch activities** - React Query
4. **Add loading state** - Skeleton UI

---

### Task T3.5.4: Create LinkedItems Component

**ID:** T3.5.4
**Story:** S3.5
**Priority:** Medium
**Estimated Effort:** 1.5 hours

**Description:**
Create a component showing parent/children hierarchy, related issues, and linked commits.

**File: frontend/components/codeboard/linked-items.tsx**
```typescript
'use client';

import { Issue } from '@/types/codeboard';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { IssueTypeIcon } from './issue-type-icon';
import { Plus, ArrowUp, ArrowDown, Link2 } from 'lucide-react';

interface LinkedItemsProps {
  issue: Issue;
}

export function LinkedItems({ issue }: LinkedItemsProps) {
  return (
    <div className="space-y-6">
      {/* Parent */}
      {issue.parentId && (
        <div>
          <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
            <ArrowUp className="h-4 w-4" />
            Parent
          </h4>
          <LinkedIssueCard issueId={issue.parentId} />
        </div>
      )}

      {/* Children */}
      {issue.children && issue.children.length > 0 && (
        <div>
          <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
            <ArrowDown className="h-4 w-4" />
            Child Issues ({issue.children.length})
          </h4>
          <div className="space-y-2">
            {issue.children.map(child => (
              <LinkedIssueCard key={child.id} issue={child} />
            ))}
          </div>
        </div>
      )}

      {/* Related */}
      {issue.relatedIssues && issue.relatedIssues.length > 0 && (
        <div>
          <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
            <Link2 className="h-4 w-4" />
            Related Issues
          </h4>
          <div className="space-y-2">
            {issue.relatedIssues.map(related => (
              <LinkedIssueCard key={related.id} issue={related} />
            ))}
          </div>
        </div>
      )}

      <Button variant="outline" size="sm" className="w-full">
        <Plus className="h-4 w-4 mr-2" />
        Link Issue
      </Button>
    </div>
  );
}

function LinkedIssueCard({ issue, issueId }: { issue?: Issue; issueId?: string }) {
  // If only issueId provided, fetch the issue
  // For simplicity, assuming issue is passed

  if (!issue) return null;

  return (
    <div className="flex items-center gap-2 p-2 rounded border hover:bg-muted cursor-pointer">
      <IssueTypeIcon type={issue.type} />
      <Badge variant="outline" className="text-xs">{issue.key}</Badge>
      <span className="text-sm truncate flex-1">{issue.title}</span>
      <Badge variant="secondary" className="text-xs">{issue.status}</Badge>
    </div>
  );
}
```

**Acceptance Criteria:**
- [ ] Shows parent issue if exists
- [ ] Lists child issues
- [ ] Lists related/linked issues
- [ ] Link issue button
- [ ] Click navigates to issue

**Sub-tasks:**
1. **Create section layout** - Parent, children, related
2. **Create LinkedIssueCard** - Compact issue display
3. **Add link issue button** - Opens linking modal

---

### Task T3.5.5: Create CommentsSection

**ID:** T3.5.5
**Story:** S3.5
**Priority:** Medium
**Estimated Effort:** 1.5 hours

**Description:**
Create the comments section with a list of comments and a new comment form.

**File: frontend/components/codeboard/comments-section.tsx**
```typescript
'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { formatDistanceToNow } from 'date-fns';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Skeleton } from '@/components/ui/skeleton';
import { Send } from 'lucide-react';

interface Comment {
  id: string;
  author: string;
  content: string;
  createdAt: string;
}

interface CommentsSectionProps {
  issueId: string;
}

export function CommentsSection({ issueId }: CommentsSectionProps) {
  const [newComment, setNewComment] = useState('');
  const queryClient = useQueryClient();

  const { data: comments, isLoading } = useQuery({
    queryKey: ['comments', issueId],
    queryFn: () => fetchComments(issueId),
  });

  const addComment = useMutation({
    mutationFn: (content: string) => postComment(issueId, content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments', issueId] });
      setNewComment('');
    },
  });

  const handleSubmit = () => {
    if (newComment.trim()) {
      addComment.mutate(newComment);
    }
  };

  return (
    <div className="space-y-4">
      {/* Comment list */}
      <div className="space-y-4 max-h-[400px] overflow-y-auto">
        {isLoading ? (
          [1, 2].map(i => (
            <div key={i} className="flex gap-3">
              <Skeleton className="h-8 w-8 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-1/4" />
                <Skeleton className="h-12 w-full" />
              </div>
            </div>
          ))
        ) : comments?.length === 0 ? (
          <p className="text-center text-muted-foreground py-8">
            No comments yet. Be the first to comment!
          </p>
        ) : (
          comments?.map(comment => (
            <div key={comment.id} className="flex gap-3">
              <Avatar className="h-8 w-8">
                <AvatarFallback>{comment.author[0]}</AvatarFallback>
              </Avatar>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{comment.author}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatDistanceToNow(new Date(comment.createdAt), { addSuffix: true })}
                  </span>
                </div>
                <p className="text-sm mt-1">{comment.content}</p>
              </div>
            </div>
          ))
        )}
      </div>

      {/* New comment form */}
      <div className="flex gap-2">
        <Textarea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add a comment..."
          className="min-h-[80px]"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && e.metaKey) {
              handleSubmit();
            }
          }}
        />
      </div>
      <div className="flex justify-end">
        <Button
          onClick={handleSubmit}
          disabled={!newComment.trim() || addComment.isPending}
        >
          <Send className="h-4 w-4 mr-2" />
          {addComment.isPending ? 'Posting...' : 'Comment'}
        </Button>
      </div>
    </div>
  );
}

async function fetchComments(issueId: string): Promise<Comment[]> {
  const res = await fetch(`/api/codeboard/issues/${issueId}/comments`);
  return res.json();
}

async function postComment(issueId: string, content: string): Promise<Comment> {
  const res = await fetch(`/api/codeboard/issues/${issueId}/comments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  return res.json();
}
```

**Acceptance Criteria:**
- [ ] List existing comments
- [ ] Author avatar and name
- [ ] Relative timestamps
- [ ] New comment textarea
- [ ] Submit button with loading state
- [ ] Cmd+Enter to submit

**Sub-tasks:**
1. **Create comment list** - With avatars
2. **Add new comment form** - Textarea and button
3. **Implement submit** - With optimistic update
4. **Add keyboard shortcut** - Cmd+Enter

---

## Story 3.6: Create Issue Modal

**ID:** S3.6
**Epic:** E3
**Priority:** High
**Description:** Implement the issue creation modal with all required fields and validation.

---

### Task T3.6.1: Create CreateIssueModal Component

**ID:** T3.6.1
**Story:** S3.6
**Priority:** High
**Estimated Effort:** 1.5 hours

**Description:**
Create the modal wrapper for issue creation with proper form handling.

**File: frontend/components/codeboard/create-issue-modal.tsx**
```typescript
'use client';

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { IssueForm } from './issue-form';
import { CreateIssueInput } from '@/types/codeboard';

interface CreateIssueModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: CreateIssueInput) => Promise<void>;
  projectId: string;
  defaultType?: string;
  defaultParentId?: string;
}

export function CreateIssueModal({
  open,
  onClose,
  onSubmit,
  projectId,
  defaultType,
  defaultParentId,
}: CreateIssueModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (data: CreateIssueInput) => {
    setIsSubmitting(true);
    try {
      await onSubmit({ ...data, projectId });
      onClose();
    } catch (error) {
      console.error('Failed to create issue:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Create Issue</DialogTitle>
        </DialogHeader>
        <IssueForm
          onSubmit={handleSubmit}
          isSubmitting={isSubmitting}
          defaultType={defaultType}
          defaultParentId={defaultParentId}
        />
      </DialogContent>
    </Dialog>
  );
}
```

**Acceptance Criteria:**
- [ ] Modal opens with form
- [ ] Close button and escape key close
- [ ] Submit shows loading state
- [ ] Closes on successful submit
- [ ] Error state on failure

**Sub-tasks:**
1. **Create Dialog wrapper** - With header
2. **Add form component** - Separate for reuse
3. **Handle submit state** - Loading indicator

---

### Task T3.6.2: Add Form Fields

**ID:** T3.6.2
**Story:** S3.6
**Priority:** High
**Estimated Effort:** 1.5 hours

**Description:**
Create the form fields for issue creation including title, type, priority, and description.

**File: frontend/components/codeboard/issue-form.tsx**
```typescript
'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { IssueTypeIcon } from './issue-type-icon';
import { PriorityBadge } from './priority-badge';
import { CreateIssueInput } from '@/types/codeboard';

const issueSchema = z.object({
  title: z.string().min(1, 'Title is required').max(200),
  type: z.enum(['EPIC', 'STORY', 'TASK', 'BUG', 'SUBTASK']),
  priority: z.enum(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']),
  description: z.string().optional(),
  parentId: z.string().optional(),
});

interface IssueFormProps {
  onSubmit: (data: CreateIssueInput) => void;
  isSubmitting: boolean;
  defaultType?: string;
  defaultParentId?: string;
}

export function IssueForm({
  onSubmit,
  isSubmitting,
  defaultType = 'TASK',
  defaultParentId,
}: IssueFormProps) {
  const form = useForm<z.infer<typeof issueSchema>>({
    resolver: zodResolver(issueSchema),
    defaultValues: {
      title: '',
      type: defaultType as any,
      priority: 'MEDIUM',
      description: '',
      parentId: defaultParentId,
    },
  });

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="type"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Type</FormLabel>
              <Select onValueChange={field.onChange} defaultValue={field.value}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {['EPIC', 'STORY', 'TASK', 'BUG', 'SUBTASK'].map(type => (
                    <SelectItem key={type} value={type}>
                      <div className="flex items-center gap-2">
                        <IssueTypeIcon type={type as any} />
                        {type.charAt(0) + type.slice(1).toLowerCase()}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="title"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Title</FormLabel>
              <FormControl>
                <Input placeholder="Enter issue title..." {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="priority"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Priority</FormLabel>
              <Select onValueChange={field.onChange} defaultValue={field.value}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map(priority => (
                    <SelectItem key={priority} value={priority}>
                      <PriorityBadge priority={priority as any} />
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Description</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="Describe the issue..."
                  className="min-h-[100px]"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex justify-end gap-2 pt-4">
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Creating...' : 'Create Issue'}
          </Button>
        </div>
      </form>
    </Form>
  );
}
```

**Acceptance Criteria:**
- [ ] Type selector with icons
- [ ] Title input with validation
- [ ] Priority selector with badges
- [ ] Description textarea
- [ ] Form validation with error messages

**Sub-tasks:**
1. **Create form schema** - Zod validation
2. **Add type selector** - With icons
3. **Add priority selector** - With badges
4. **Add title and description** - With validation

---

### Task T3.6.3: Add Parent Selector

**ID:** T3.6.3
**Story:** S3.6
**Priority:** Medium
**Estimated Effort:** 1 hour

**Description:**
Add a parent issue selector for creating subtasks and child issues.

**Implementation:**
```typescript
// Add to issue-form.tsx
import { ParentSelector } from './parent-selector';

// In form:
{form.watch('type') !== 'EPIC' && (
  <FormField
    control={form.control}
    name="parentId"
    render={({ field }) => (
      <FormItem>
        <FormLabel>Parent Issue (Optional)</FormLabel>
        <FormControl>
          <ParentSelector
            value={field.value}
            onChange={field.onChange}
            excludeTypes={['SUBTASK']}
          />
        </FormControl>
        <FormMessage />
      </FormItem>
    )}
  />
)}
```

**File: frontend/components/codeboard/parent-selector.tsx**
```typescript
'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { Check, ChevronsUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { IssueTypeIcon } from './issue-type-icon';

interface ParentSelectorProps {
  value?: string;
  onChange: (value: string | undefined) => void;
  excludeTypes?: string[];
}

export function ParentSelector({ value, onChange, excludeTypes = [] }: ParentSelectorProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');

  const { data: issues } = useQuery({
    queryKey: ['issues', 'parent-selector', search],
    queryFn: () => searchIssues(search, excludeTypes),
  });

  const selectedIssue = issues?.find(i => i.id === value);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          className="w-full justify-between"
        >
          {selectedIssue ? (
            <div className="flex items-center gap-2">
              <IssueTypeIcon type={selectedIssue.type} />
              <span>{selectedIssue.key}</span>
              <span className="truncate text-muted-foreground">{selectedIssue.title}</span>
            </div>
          ) : (
            'Select parent issue...'
          )}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[400px] p-0">
        <Command>
          <CommandInput
            placeholder="Search issues..."
            value={search}
            onValueChange={setSearch}
          />
          <CommandEmpty>No issues found.</CommandEmpty>
          <CommandGroup className="max-h-[300px] overflow-auto">
            {issues?.map(issue => (
              <CommandItem
                key={issue.id}
                onSelect={() => {
                  onChange(issue.id === value ? undefined : issue.id);
                  setOpen(false);
                }}
              >
                <Check
                  className={cn(
                    'mr-2 h-4 w-4',
                    value === issue.id ? 'opacity-100' : 'opacity-0'
                  )}
                />
                <IssueTypeIcon type={issue.type} className="mr-2" />
                <span className="font-medium">{issue.key}</span>
                <span className="ml-2 truncate text-muted-foreground">{issue.title}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

async function searchIssues(query: string, excludeTypes: string[]) {
  const params = new URLSearchParams({ q: query });
  excludeTypes.forEach(t => params.append('excludeType', t));
  const res = await fetch(`/api/codeboard/issues/search?${params}`);
  return res.json();
}
```

**Acceptance Criteria:**
- [ ] Combobox with search
- [ ] Shows issue type, key, and title
- [ ] Filters by search text
- [ ] Excludes subtasks from options
- [ ] Can clear selection

**Sub-tasks:**
1. **Create combobox** - With search
2. **Fetch issues** - Debounced search
3. **Display issue details** - Type, key, title

---

### Task T3.6.4: Form Validation and Submission

**ID:** T3.6.4
**Story:** S3.6
**Priority:** High
**Estimated Effort:** 1 hour

**Description:**
Implement comprehensive form validation and error handling for issue submission.

**Technical Requirements:**
- Title required, max 200 chars
- Type required
- Priority required
- Parent validation (can't parent to subtask, Epic can't have parent)
- API error handling with toast notifications

**Implementation:**
```typescript
// Enhanced validation
const issueSchema = z.object({
  title: z.string()
    .min(1, 'Title is required')
    .max(200, 'Title must be less than 200 characters'),
  type: z.enum(['EPIC', 'STORY', 'TASK', 'BUG', 'SUBTASK']),
  priority: z.enum(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']),
  description: z.string().max(10000, 'Description too long').optional(),
  parentId: z.string().optional(),
}).refine(data => {
  // Epic can't have parent
  if (data.type === 'EPIC' && data.parentId) {
    return false;
  }
  return true;
}, {
  message: "Epics cannot have a parent issue",
  path: ['parentId'],
});

// Error handling in form
const handleSubmit = async (data: CreateIssueInput) => {
  try {
    await onSubmit(data);
    toast({ title: 'Issue created successfully' });
  } catch (error) {
    if (error instanceof Error) {
      toast({
        title: 'Failed to create issue',
        description: error.message,
        variant: 'destructive',
      });
    }
  }
};
```

**Acceptance Criteria:**
- [ ] All required fields validated
- [ ] Character limits enforced
- [ ] Parent validation rules applied
- [ ] API errors shown in toast
- [ ] Form resets on successful submit

**Sub-tasks:**
1. **Add Zod validation** - All field rules
2. **Add custom refinements** - Business rules
3. **Add error toasts** - API error display
4. **Add success handling** - Reset and close

---

# See IMPLEMENTATION_PLAN_DETAILED_PART4.md for Epics 4-7
