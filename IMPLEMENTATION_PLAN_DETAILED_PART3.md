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

## Story 3.3-3.6: Additional UI Components

*(Due to document length, Stories 3.3-3.6 follow the same detailed pattern with:)*

**Story 3.3: List View**
- T3.3.1: Create IssueList component - Table with columns
- T3.3.2: Create IssueRow component - Row with all fields
- T3.3.3: Add sorting functionality - Click column headers
- T3.3.4: Add pagination - Page navigation

**Story 3.4: Filter Bar**
- T3.4.1: Create FilterBar component - Container with filters
- T3.4.2-5: Add filter dropdowns - Type, Status, Priority, Assignee
- T3.4.6: Add text search - Debounced input

**Story 3.5: Issue Detail View**
- T3.5.1: Create IssueDetail component - Full issue view
- T3.5.2: Create DescriptionSection - Markdown with edit
- T3.5.3: Create ActivityLog component - Timeline
- T3.5.4: Create LinkedItems component - Related issues
- T3.5.5: Create CommentsSection - Comment thread

**Story 3.6: Create Issue Modal**
- T3.6.1: Create CreateIssueModal component - Modal wrapper
- T3.6.2: Add form fields - All issue fields
- T3.6.3: Add parent selector - Hierarchy selection
- T3.6.4: Form validation and submission - With error handling

---

# See IMPLEMENTATION_PLAN_DETAILED_PART4.md for Epics 4-7
