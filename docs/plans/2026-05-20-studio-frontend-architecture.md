# Studio Frontend Architecture
## Next.js 16 App Router — Component Design for Workspace, Studio, Backlog, Crew Map

**Date:** 2026-05-20
**Author:** React Specialist (AI)
**Status:** DESIGN APPROVED — ready for implementation sprint
**Supersedes:** component sketch sections in `2026-05-07-ai-project-workspace-master-plan.md`
**Source context:** CB-2384, master plan v2.0, CandleKeep v1.1 patterns

---

## 1. Route Structure

### App Router layout tree

```
frontend/app/
├── layout.tsx                          (existing root — sidebar + providers)
│
└── workspace/
    ├── layout.tsx                      (SERVER) WorkspaceLayout
    │   Renders: WorkspaceShell, workspace-switcher, nav tabs
    │   Reads: workspaceId from cookies/session (tenant context)
    │
    ├── page.tsx                        (redirect → /workspace/[id]/studio)
    │
    └── [id]/
        ├── layout.tsx                  (CLIENT) WorkspaceTenantLayout
        │   Resolves workspace, injects TenantContext, renders nav
        │
        ├── studio/
        │   └── page.tsx               (CLIENT) StudioPage
        │
        ├── backlog/
        │   └── page.tsx               (CLIENT) BacklogPage
        │
        └── crew-map/
            └── page.tsx               (CLIENT) CrewMapPage
```

### Route conventions

| Route | Params preserved in URL | Notes |
|---|---|---|
| `/workspace` | — | Redirect to last visited or default workspace |
| `/workspace/[id]/studio` | `?conv=<convId>&tab=<n>` | Active conversation + tab index |
| `/workspace/[id]/backlog` | `?status=&priority=&tag=&sort=` | Filter/sort state |
| `/workspace/[id]/crew-map` | `?project=&feature=&agent=&status=` | Graph filter state |

### Workspace switcher placement

The switcher lives inside `WorkspaceTenantLayout` as a top-bar slot — visible across all three views. It is a `<select>` (or custom popover) that reads the tenant list from `GET /api/workspaces` and triggers `router.replace('/workspace/[newId]/studio')` on change. **It never lives in sidebar** — workspace is a horizontal concern above the view tabs.

```
┌─────────────────────────────────────────────────────────┐
│  [Workspace: PMv2 Production ▾]  Studio | Backlog | Map │
└─────────────────────────────────────────────────────────┘
```

### Tenant context in every API call

A `TenantContext` (React Context) holds `{ workspaceId, tenantHeaders }`. All React Query keys are prefixed with `['workspace', workspaceId, ...]` so caches are scoped per tenant and do not bleed across workspace switches.

```ts
// lib/api/workspace-client.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8401';

export function workspaceFetch<T>(
  path: string,
  workspaceId: string,
  init?: RequestInit,
): Promise<T> {
  return apiFetch<T>(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'X-Workspace-Id': workspaceId,
      ...init?.headers,
    },
  });
}
```

No `localhost` hardcodes anywhere in new code — all URLs derive from `process.env.NEXT_PUBLIC_API_URL`.

---

## 2. Component Trees

### 2a. WorkspaceTenantLayout (shared by all three views)

```
WorkspaceTenantLayout                   CLIENT — [id]/layout.tsx
  TenantProvider                        Context: workspaceId, workspace metadata
    WorkspaceTopBar                     CLIENT — workspace switcher + view tabs
      WorkspaceSwitcher                 CLIENT — popover select
      WorkspaceNavTabs                  CLIENT — Studio / Backlog / Crew Map
    {children}                          the active view page
    AutoPilotFloatingBar                existing — already in providers.tsx (z-70)
```

`WorkspaceTenantLayout` is a **Client Component** because it reads the `[id]` param via `useParams()` to hydrate `TenantContext`. The `WorkspaceTopBar` is always visible, full-width, above the view content.

### 2b. Studio view

```
StudioPage                              CLIENT — studio/page.tsx
  Suspense fallback=<StudioSkeleton />
    StudioShell                         CLIENT — overall grid
      ConversationTabBar                CLIENT — tab strip
        ConversationTab[]               CLIENT — one per open conversation
          TabLiveIndicator              CLIENT — pulse dot (CSS keyframe)
        NewConversationButton           CLIENT
      ChatPanel                         CLIENT — left 60%
        Chat.Provider                   Context: convId, messages, agentStatus
          Chat.MessageList              CLIENT — virtualized list
            ChatMessage[]               CLIENT — per message
              RoleBadge                 CLIENT — user / Jonny / skill
              StreamingTextContent      CLIENT — ref-buffered SSE token render
              AgentInvocationCard       CLIENT — collapsible "calling architect…"
              ArtifactAnchor            CLIENT — "View artifact →" trigger
            ChatMessageSkeleton         loading placeholder
          Chat.AgentStatus             CLIENT — live crew panel
            AgentStatusRow[]           CLIENT — idle/thinking/tool-use/done
          Chat.Input                   CLIENT — textarea + slash commands
          Chat.Actions                 CLIENT — Send / Backlog / Pause / Save
      PreviewPane                       CLIENT — right 40%, slides in on artifact
        PreviewPaneTabs                CLIENT — MD / Mermaid / Code / HTML
        MarkdownPreview                CLIENT — rehype-pretty-code
        MermaidPreview                 CLIENT — dynamic import mermaid.js
        CodePreview                    CLIENT — shiki or Monaco-lite
        HtmlPreview                    CLIENT — sandboxed iframe
        ResizeHandle                   CLIENT — role="separator", drag + keyboard
      SendToBacklogModal               CLIENT — confirm + edit before send
```

**5 hard components in Studio:**

| Component | Why hard |
|---|---|
| `StreamingTextContent` | `useRef` token buffer + 50ms flush, `content-visibility: auto`, `aria-live="polite"` |
| `AgentInvocationCard` | Collapsible with animated expand, SSE-driven tool-use badge, chain-depth display |
| `PreviewPane` | CSS transition enter/exit timing (250ms/150ms), keyboard-operable resize handle, focus management on reveal/close |
| `MermaidPreview` | Dynamic import (no SSR), Mermaid v10 async API, error boundary |
| `ConversationTabBar` | Multi-tab state model (see section 6), `startTransition` on switch, right-click context menu, URL sync |

### 2c. Backlog view

```
BacklogPage                             CLIENT — backlog/page.tsx
  Suspense fallback=<BacklogSkeleton />
    BacklogShell
      BacklogFilterBar                  CLIENT — project/status/priority/tag (URL state)
        FilterPill[]                    CLIENT — border-radius:9999px pills
        SortDropdown                    CLIENT
      BacklogList                       CLIENT — drag-orderable list
        DragDropContext                 (dnd-kit SortableContext)
          BacklogCard[]                 CLIENT — sortable
            PriorityBadge              CLIENT — Linear-style, border-radius:2px
            StatusPill                 CLIENT
            ScheduleIndicator          CLIENT — "next firing" preview, tnum font
            TagList                    CLIENT
            CardActions                CLIENT — Edit / Studio / Send / Schedule
      BacklogEmptyState                CLIENT
      NewFeatureButton                 CLIENT
    BacklogEditModal                   CLIENT — Dialog portal
      PriorityPicker                   CLIENT — pill group
      StatusPicker                     CLIENT — pill group
      TagMultiSelect                   CLIENT — combobox
      OwnerPicker                      CLIENT
      SchedulePicker                   CLIENT — radio + date/cron
        OneShotDatePicker              CLIENT
        CronInput                      CLIENT — expression + human preview
    SendToCodeBoardModal               CLIENT — confirmation + hierarchy preview
      HierarchyPreview                CLIENT — tree display before promotion
```

**5 hard components in Backlog:**

| Component | Why hard |
|---|---|
| `BacklogList` | dnd-kit drag-reorder, optimistic mutation on drop, `<400ms Doherty rule` for all interactions |
| `SchedulePicker` | One-shot/recurring/unscheduled radio, cron expression parser, live human-readable preview |
| `SendToCodeBoardModal` | Blueprint state machine UI — validates, shows AI-generated hierarchy, user edits, then fires promote pipeline |
| `BacklogCard` | Drag handle, multi-action row, schedule indicator with `font-feature-settings: "tnum"`, source link to Studio |
| `CronInput` | Cron string validation feedback, real-time "next firing" calculation without layout thrash |

### 2d. Crew Map view

```
CrewMapPage                             CLIENT — crew-map/page.tsx
  Suspense fallback=<CrewMapSkeleton />
    CrewMapShell
      CrewMapFilterBar                  CLIENT — project/feature/agent/status (URL state)
      ReactFlowCanvas                   CLIENT — react-flow wrapper
        Suspense fallback=<GraphLoadingSkeleton />
          ProjectNode                  CLIENT — custom react-flow node
          FeatureNode                  CLIENT — color-by-priority
          OrchestratorNode             CLIENT — crown icon, gold border
          SkillNode                    CLIENT — pulse if active
          ConversationNode             CLIENT — diamond, Studio deep-link
          ActiveEdge                   CLIENT — animated dashes for live data flow
          PastEdge                     CLIENT — dashed, inactive
        GraphMiniMap                   CLIENT — react-flow MiniMap
        GraphControls                  CLIENT — zoom/pan/fit
      NodeDetailPanel                  CLIENT — slide-in right panel on click
        ProjectDetail                  variant
        FeatureDetail                  variant
        OrchestratorDetail             variant
        AgentDetail                    variant
        ConversationDetail             variant
      CrewMapSearchBar                 CLIENT — fuzzy node search
```

**5 hard components in Crew Map:**

| Component | Why hard |
|---|---|
| `ReactFlowCanvas` | 1000-node performance budget (see section 5), SSE live updates via state reducer, force-directed layout with viewport persistence |
| `SkillNode` | CSS keyframe pulse (2Hz) with `@media (prefers-reduced-motion)` fallback, active/idle/done state variants |
| `ActiveEdge` | SVG animated dash via CSS `stroke-dashoffset` — not `@keyframes` on `width` (GPU-only rule) |
| `NodeDetailPanel` | CSS transition 250ms/150ms enter/exit, deep-link routing, focus management |
| `CrewMapFilterBar` | Subgraph filtering drives `visibleNodes`/`visibleEdges` as derived state, URL-synced, reset-view action |

---

## 3. State Management

### Decision table

| State type | Home | Why |
|---|---|---|
| Server state (conversations, backlog items, graph nodes) | React Query | Cache invalidation, deduplication, background refetch |
| Chat draft (textarea content per conversation) | Zustand `useStudioStore` | Survives tab switches, no server round-trip needed |
| Active tab index + open conversation IDs | Zustand `useStudioStore` | Preserved across navigation, multi-tab model |
| Panel sizes (chat:preview split ratio) | Zustand `useStudioStore` | User preference, localStorage-persisted |
| Streaming token buffer | `useRef` (not state) | Avoids re-render per token; flushed to state every 50ms |
| Agent activity (SSE-driven) | `useReducer` inside `Chat.Provider` | Event-sourced reducer, predictable transitions |
| Backlog filter/sort | URL search params | Shareable, bookmark-able, back/forward navigation |
| Crew Map filter/selected node | URL search params + `useState` | Filter is shareable; selected node is ephemeral |
| Graph viewport position | `useRef` + `localStorage` | Persisted per project, not URL (too large) |
| Workspace/tenant identity | React Context (`TenantContext`) | Stable for entire workspace session |

### Zustand store shape (Studio)

```ts
// stores/useStudioStore.ts
interface StudioStore {
  // Multi-tab model
  openConversationIds: string[];          // ordered list of open tab IDs
  activeConversationId: string | null;    // which tab is in focus
  conversationDrafts: Record<string, string>; // textarea draft per conv
  panelSplitRatio: number;               // 0.6 default (chat:preview)

  // Actions
  openConversation: (id: string) => void;
  closeConversation: (id: string) => void;
  setActive: (id: string) => void;
  setDraft: (convId: string, text: string) => void;
  setPanelSplitRatio: (ratio: number) => void;
}
```

`panelSplitRatio` is persisted to `localStorage` via Zustand's `persist` middleware (key: `studio-panel-v1`). Draft text is session-only (no persist — intentional).

### React Query key conventions

```ts
// All keys tenant-scoped:
['workspace', workspaceId, 'conversations']
['workspace', workspaceId, 'conversation', convId, 'messages']
['workspace', workspaceId, 'backlog']
['workspace', workspaceId, 'backlog', featureRequestId]
['workspace', workspaceId, 'crew-map', projectId]
```

This ensures that switching workspace invalidates nothing from the previous workspace and avoids stale data cross-contamination.

### Context vs. Zustand decision boundary

Use **Context** when: data is stable and scoped to a subtree (e.g., `TenantContext`, `Chat.Provider` per conversation).
Use **Zustand** when: data must survive unmount/remount (e.g., tab strip, drafts, panel sizes).
Use **URL state** when: the state should be shareable or bookmarked (filters, active node).

---

## 4. Streaming UX

### Chat token streaming

```
Backend SSE channel:
  GET /api/studio/sessions/{convId}/events
  Content-Type: text/event-stream

Event types:
  data: {"type": "token", "delta": "text chunk"}
  data: {"type": "tool_start", "tool": "architect", "inTool": true}
  data: {"type": "tool_end", "tool": "architect", "inTool": false}
  data: {"type": "artifact", "kind": "markdown|mermaid|code|html", "payload": "..."}
  data: {"type": "message_done", "role": "assistant"}
  data: {"type": "agent_status", "agentName": "architect", "status": "active|idle|done"}
```

**Frontend wiring pattern (`useConversationStream.ts`):**

```ts
// hooks/useConversationStream.ts
export function useConversationStream(convId: string, workspaceId: string) {
  const tokenBufferRef = useRef('');
  const [displayedContent, setDisplayedContent] = useState('');
  const [agentStatuses, dispatch] = useReducer(agentStatusReducer, {});
  const esRef = useRef<EventSource | null>(null);
  const flushIntervalRef = useRef<ReturnType<typeof setInterval>>();
  const reconnectDelayRef = useRef(1000); // exponential backoff

  useEffect(() => {
    function connect() {
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? '';
      const url = `${apiBase}/api/studio/sessions/${convId}/events?workspaceId=${workspaceId}`;
      const es = new EventSource(url);
      esRef.current = es;

      es.onopen = () => { reconnectDelayRef.current = 1000; };

      es.onmessage = (e) => {
        const event = JSON.parse(e.data);
        if (event.type === 'token') {
          tokenBufferRef.current += event.delta;  // accumulate in ref — no re-render
        }
        if (event.type === 'tool_start' || event.type === 'tool_end') {
          dispatch({ type: 'AGENT_STATUS', agentName: event.tool, inTool: event.inTool });
        }
        if (event.type === 'artifact') {
          // Triggers preview pane reveal
          queryClient.setQueryData(['artifact', convId], event);
        }
      };

      es.onerror = () => {
        es.close();
        // Exponential backoff reconnect — 1s → 2s → 4s → cap 30s
        const delay = Math.min(reconnectDelayRef.current, 30_000);
        reconnectDelayRef.current = delay * 2;
        setTimeout(connect, delay);
      };
    }

    // 50ms flush interval — batches token buffer into React state
    flushIntervalRef.current = setInterval(() => {
      if (tokenBufferRef.current) {
        setDisplayedContent(prev => prev + tokenBufferRef.current);
        tokenBufferRef.current = '';
      }
    }, 50);

    connect();

    return () => {
      esRef.current?.close();
      clearInterval(flushIntervalRef.current);
    };
  }, [convId, workspaceId]);

  return { displayedContent, agentStatuses };
}
```

**Key choices:**
- `tokenBufferRef` accumulates deltas without re-renders (prevents 20+ renders/second during fast streaming)
- 50ms interval flushes to state — one render per 50ms maximum
- Exponential backoff on `onerror` handles network blips transparently
- `es.close()` on cleanup prevents memory leaks on tab switch

### Agent activity feed (`agentStatusReducer`)

```ts
type AgentStatusState = Record<string, 'idle' | 'thinking' | 'tool-use' | 'done'>;

function agentStatusReducer(state: AgentStatusState, action: AgentAction): AgentStatusState {
  switch (action.type) {
    case 'AGENT_STATUS':
      return {
        ...state,
        [action.agentName]: action.inTool ? 'tool-use' : 'thinking',
      };
    case 'AGENT_DONE':
      return { ...state, [action.agentName]: 'done' };
    case 'AGENT_IDLE':
      return { ...state, [action.agentName]: 'idle' };
    default:
      return state;
  }
}
```

### Backlog live sync

Backlog does not need SSE. It uses React Query with a 10-second polling interval as the primary mechanism, supplemented by an SSE channel for "promote pipeline" progress events:

```ts
// Polling for list view
useQuery({
  queryKey: ['workspace', workspaceId, 'backlog'],
  queryFn: () => workspaceFetch('/api/feature-backlog', workspaceId),
  refetchInterval: 10_000,
});

// SSE for promote pipeline progress (one-shot while modal is open)
// GET /api/feature-backlog/{id}/promote/events
```

### Skeleton / loading states

Every data-dependent region wraps in `<Suspense>` with a skeleton fallback:

| Region | Skeleton component |
|---|---|
| Studio tab strip | `<StudioTabSkeleton />` — 3–4 animated gray tab bars |
| Chat message list | `<ChatMessageSkeleton />` — alternating wide/narrow shimmer rows |
| Agent status panel | `<AgentStatusSkeleton />` — 4 gray icon+label rows |
| Preview pane | `<PreviewPaneSkeleton />` — full-width shimmer block |
| Backlog list | `<BacklogCardSkeleton />` — 5 card outlines |
| Crew map | `<GraphLoadingSkeleton />` — canvas with placeholder node circles |

All skeletons use Tailwind `animate-pulse` with `@media (prefers-reduced-motion)` → `opacity-60` static fallback.

---

## 5. Crew Map Graph — Library Recommendation

### Recommended: React Flow (v12)

**Why React Flow:**
- React-native: nodes and edges are React components — custom renderers slot in naturally
- Built-in zoom/pan, minimap, controls
- MIT license, ~80kb gz (verified in master plan)
- Viewport persistence via `onNodesChange` → `localStorage` per project
- Tested with Next.js 16 (pin to `@xyflow/react@12.x`)

**Why not Cytoscape.js:** More raw graph power but not React-native — requires imperative DOM wiring. Custom node renderers are significantly harder. Edge routing is more complex to theme.

**Why not Sigma.js:** Designed for very large graphs (10,000+ nodes). Overkill here, and its rendering model (WebGL canvas) makes custom node components impossible without hacks.

### Performance budget for 1000 nodes

React Flow renders nodes as DOM elements. At 1000 nodes with full DOM rendering, frame time degrades to ~100ms+ — unacceptable.

**Mitigation strategy (two layers):**

**Layer 1 — Viewport culling (built-in React Flow):**
React Flow only renders nodes that intersect the viewport. At typical zoom levels (~70% of 1000 nodes are offscreen), effective DOM node count drops to ~150–300.

**Layer 2 — On-demand subgraph loading:**
Default load: project-level nodes only (projects + features). Agent/skill nodes load on-demand when a feature node is expanded/clicked.

```ts
// hooks/useCrewMapGraph.ts
export function useCrewMapGraph(workspaceId: string, projectId: string) {
  const [expandedFeatureIds, setExpandedFeatureIds] = useState<Set<string>>(new Set());

  // Base query: project + feature nodes only
  const baseQuery = useQuery({
    queryKey: ['workspace', workspaceId, 'crew-map', projectId, 'base'],
    queryFn: () => workspaceFetch(`/api/crew-map?projectId=${projectId}&depth=feature`, workspaceId),
  });

  // Per-feature subgraph — fires when feature node is expanded
  const subgraphQueries = useQueries({
    queries: Array.from(expandedFeatureIds).map(featureId => ({
      queryKey: ['workspace', workspaceId, 'crew-map', 'feature', featureId],
      queryFn: () => workspaceFetch(`/api/crew-map/feature/${featureId}`, workspaceId),
    })),
  });

  // Merge base + subgraphs into React Flow nodes/edges arrays
  const { nodes, edges } = useMemo(() => mergeGraphData(baseQuery.data, subgraphQueries), [baseQuery.data, subgraphQueries]);

  return { nodes, edges, expandFeature: (id: string) => setExpandedFeatureIds(prev => new Set(prev).add(id)) };
}
```

**Layer 3 — Force layout in Web Worker (future optimization, not MVP):**
If the full graph loads and layout computation stalls the main thread, `d3-force` layout calculations move to a Web Worker via `comlink`. The worker emits position updates that React Flow applies incrementally. This is explicitly a Phase 2 concern (risk register item: "Crew Map graph performance with >100 nodes").

**Performance target:**
- Initial render (base graph, ~20–40 nodes): < 200ms
- Expand feature to show skills (~10 new nodes): < 100ms
- Full 1000-node graph with viewport culling: < 50ms per frame during pan/zoom

---

## 6. Multi-Tab Studio Sessions

### Tab state model

Each tab corresponds to one `StudioConversation` record in the database. The tab strip state lives in Zustand:

```ts
// In useStudioStore:
openConversationIds: string[]   // ordered — the tab strip order
activeConversationId: string | null

// Encoded in URL:
?conv=<activeConversationId>&tabs=<convId1>,<convId2>,<convId3>
```

URL encoding of open tabs ensures that hard-refresh or browser back/forward restores the exact tab configuration. The `tabs=` param is comma-separated conversation IDs. Max 8 tabs enforced client-side (matches SSE channel limit from risk register).

### Tab lifecycle

```
[New Conv button]
      ↓
POST /api/studio/conversations → { id, title }
      ↓
openConversationIds.push(id)
activeConversationId = id
URL updated: ?conv=<id>&tabs=...,<id>
      ↓
SSE channel opened: GET /api/studio/sessions/<id>/events
      ↓
[User navigates away — tab stays open]
activeConversationId = new conv
SSE channel remains open (EventSource persists in useConversationStream)
      ↓
[User returns to tab]
activeConversationId = old conv
Chat.MessageList renders from React Query cache (no refetch needed)
SSE stream resumes (was still open)
      ↓
[Tab close (X button)]
openConversationIds.remove(id)
EventSource.close() called
URL updated
      ↓
[30min idle → hibernate]
Backend closes subprocess
Frontend shows "Hibernated" badge on tab
On tab click → POST /api/studio/sessions/<id>/resume
                → Backend re-spawns, replays last 5 messages
```

### Independent chats

Each tab maintains its own `useConversationStream` instance, keyed by `convId`. Multiple tabs can be streaming simultaneously — each has its own EventSource connection. The `Chat.Provider` context boundary ensures message state does not leak between tabs.

```tsx
// In StudioShell:
{openConversationIds.map(convId => (
  <Chat.Provider key={convId} convId={convId} workspaceId={workspaceId}>
    {/* Only the active tab is mounted visibly; others remain mounted for SSE continuity */}
    <div className={convId === activeConversationId ? 'block' : 'hidden'}>
      <Chat.MessageList />
      <Chat.AgentStatus />
      <Chat.Input />
      <Chat.Actions />
    </div>
  </Chat.Provider>
))}
```

**Important:** tabs are hidden with `className="hidden"`, not unmounted. Unmounting would close the EventSource and lose streaming state. This is the same pattern as browser tabs — the DOM persists but is visually hidden.

### Tab persistence across navigation

When user navigates to Backlog or Crew Map and back, the Zustand store (persisted to `sessionStorage`) retains `openConversationIds` and `activeConversationId`. The `StudioPage` re-renders with the same tabs and reconnects to SSE via `useConversationStream` on mount.

---

## 7. Design System Extensions

### New UI primitives needed

The following new primitives belong in `components/ui/`. They are distinct enough from existing primitives that they need dedicated files. None duplicate existing primitives.

| Primitive | File | Reuse basis | Key behaviour |
|---|---|---|---|
| `ChatBubble` | `ui/chat-bubble.tsx` | `cn()` only | Role-aware styling (user/assistant/skill), streaming shimmer slot |
| `ArtifactPreviewTabs` | `ui/artifact-preview-tabs.tsx` | extends `ui/tabs.tsx` | MD/Mermaid/Code/HTML tab switcher with icon per type |
| `AgentStatusRow` | `ui/agent-status-row.tsx` | `cn()` only | Icon + label + status badge with CSS-transition state changes |
| `PriorityBadge` | `ui/priority-badge.tsx` | `ui/badge.tsx` (new) | Linear-style, `border-radius: 2px`, 5 tiers, Inter weight 510 |
| `FilterPill` | `ui/filter-pill.tsx` | `ui/badge.tsx` | `border-radius: 9999px`, clearable, active state |
| `DragHandle` | `ui/drag-handle.tsx` | new | Vertical grip dots, `cursor-grab`, `aria-roledescription="draggable"` |
| `ResizablePanels` | `ui/resizable-panels.tsx` | new | CSS flex + pointer events resize, `role="separator"`, keyboard nav |
| `GraphMiniMapOverlay` | `ui/graph-mini-map.tsx` | wraps ReactFlow `MiniMap` | Themed to Linear-dark palette |
| `ScheduleIndicator` | `ui/schedule-indicator.tsx` | `cn()` only | Clock icon + human text + `font-feature-settings: "tnum"` for dates |
| `CronInput` | `ui/cron-input.tsx` | extends `ui/textarea.tsx` | Cron string input + validation + human-readable preview beneath |

### Existing primitives reused as-is

| Existing | Used for |
|---|---|
| `ui/modal.tsx` | BacklogEditModal, SendToBacklogModal, SendToCodeBoardModal |
| `ui/button.tsx` | All action buttons across all three views |
| `ui/tabs.tsx` | ArtifactPreviewTabs extends this |
| `ui/skeleton.tsx` | All skeleton loading states |
| `ui/toast.tsx` | All feedback toasts (promote success, save, error) |
| `ui/error-boundary.tsx` | Wrapping PreviewPane (Mermaid can throw), ReactFlowCanvas |

### Design token extensions (Tailwind config)

Add to `tailwind.config.ts` (or inline via CSS vars in `globals.css`):

```css
/* globals.css additions for Studio */
:root {
  --color-canvas:      #08090a;
  --color-panel:       #0f1011;
  --color-card:        rgba(255,255,255,0.02);
  --color-card-border: rgba(255,255,255,0.08);
  --color-accent:      #7170ff;
  --color-status-green: #27a644;
  --color-text-active:  #f7f8f8;
  --color-text-muted:   #8a8f98;
  font-feature-settings: "tnum";  /* tabular numerals for timestamps */
}

/* Inter Variable weight 510 — applied to tab labels, priority pills, agent badges */
.font-studio {
  font-variation-settings: 'wght' 510;
}

/* GPU-only animation guard */
.animate-studio-reveal {
  transition: transform 250ms ease-out, opacity 250ms ease-out;
}
.animate-studio-dismiss {
  transition: transform 150ms ease-in, opacity 150ms ease-in;
}

/* Active agent pulse — keyframe (looping one-shot only) */
@keyframes agent-pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 4px var(--color-status-green); }
  50% { opacity: 0.6; box-shadow: 0 0 8px var(--color-status-green); }
}
.animate-agent-pulse {
  animation: agent-pulse 500ms ease-in-out infinite; /* 2Hz */
}
@media (prefers-reduced-motion: reduce) {
  .animate-agent-pulse { animation: none; opacity: 0.7; }
  .animate-studio-reveal, .animate-studio-dismiss { transition: none; }
}
```

### Accessibility iron rules (non-negotiable for all new components)

1. `<div role="status" aria-live="polite">` wraps `StreamingTextContent` (not `assertive`)
2. `PreviewPane` — focus moves in on reveal, returns to `ArtifactAnchor` on close
3. `ResizablePanels` — resize handle is `role="separator"` + `aria-valuenow={ratio}` + `ArrowLeft`/`ArrowRight` keyboard navigation
4. `:focus-visible` outlines only (2px solid `#7170ff`, offset 2px) — no mouse focus rings
5. All `animate-agent-pulse` respects `prefers-reduced-motion`
6. At 200% browser zoom, split pane collapses to single column (flex-direction: column threshold at ~640px)
7. `DragHandle` announces `aria-roledescription="draggable item"` + `aria-describedby` with position info

---

## 8. Day-One MVP Slice

The MVP ships the minimum surface that delivers real value and de-risks the hardest technical bets. It maps to Phase B of the master plan rollout (weeks 2–3).

### MVP scope (ships first)

**Studio — chat only (no preview pane)**
- `WorkspaceTenantLayout` + `WorkspaceTopBar` with switcher
- `ConversationTabBar` with up to 8 tabs, URL sync, live indicator dots
- `Chat.MessageList` with token streaming (ref-buffered SSE), role badges
- `Chat.AgentStatus` panel (status rows, no animation polish yet)
- `Chat.Input` + `Chat.Actions` (Send, Pause, Save — no "Send to Backlog" yet)
- `useConversationStream` with exponential-backoff reconnect
- Tenant-scoped React Query keys + `workspaceFetch`
- `WorkspaceSwitcher` connecting to `GET /api/workspaces`

**Backlog — list + edit (no drag reorder, no scheduler)**
- `BacklogPage` shell
- `BacklogCard` with priority badge, status pill, tags, source link
- `BacklogFilterBar` with project/status/priority filter (URL state)
- `BacklogEditModal` — title, description, priority, status, tags (no cron scheduler yet)
- React Query CRUD hooks for `/api/feature-backlog`
- 10-second polling for live sync

**Bridge (Studio → Backlog)**
- `SendToBacklogModal` — transcript → structured payload → POST `/api/feature-backlog`
- "Send to Backlog" button in `Chat.Actions`
- Deep link "Open in Studio" from `BacklogCard`

### Not in MVP (Phase C / D)

| Deferred | Reason |
|---|---|
| `PreviewPane` (MD/Mermaid/Code/HTML) | High complexity, standalone value — Phase C |
| Crew Map (`crew-map/`) | Depends on `CrewAssignment` data model being populated — Phase D |
| Backlog drag-reorder | dnd-kit adds ~40KB; defer until list is validated |
| Cron scheduler in BacklogEditModal | Scheduler service (E6) must ship first |
| "Send to CodeBoard + AutoPilot" | Requires promote pipeline (E5) — Phase C |
| Hibernation/resume | Requires backend subprocess management — Phase C |
| Animation polish | After functional correctness is confirmed |

### MVP component count

- New files: ~22 components + 4 hooks + 2 stores + 1 context
- Modified files: `components/layout/sidebar.tsx` (add Studio/Backlog/Crew Map nav items), `components/providers.tsx` (wrap with `WorkspaceProvider` if needed)
- Zero changes to existing CodeBoard components — Studio links into CodeBoard (issue clicks trigger `router.push('/codeboard')`) but does not modify it

### CodeBoard integration points (non-destructive)

| Studio action | CodeBoard side |
|---|---|
| "Open in CodeBoard" from BacklogCard | `router.push('/codeboard?issue=<key>')` |
| "Send to CodeBoard + AutoPilot" | POST to existing `/api/projects/{id}/issues` + `/api/execute/queue` |
| `GlobalAgentStatusBar` | Unchanged — already mounted in providers.tsx |
| `AutoPilotFloatingBar` | Unchanged — already at z-70, stays on all pages |

---

## Appendix A — File Map (new files only)

```
frontend/
├── app/workspace/
│   ├── layout.tsx                      WorkspaceLayout (server redirect)
│   └── [id]/
│       ├── layout.tsx                  WorkspaceTenantLayout (client)
│       ├── studio/page.tsx             StudioPage
│       ├── backlog/page.tsx            BacklogPage
│       └── crew-map/page.tsx           CrewMapPage
│
├── components/
│   ├── workspace/
│   │   ├── WorkspaceTopBar.tsx
│   │   ├── WorkspaceSwitcher.tsx
│   │   └── WorkspaceNavTabs.tsx
│   ├── studio/
│   │   ├── StudioShell.tsx
│   │   ├── ConversationTabBar.tsx
│   │   ├── ConversationTab.tsx
│   │   ├── TabLiveIndicator.tsx
│   │   ├── chat/
│   │   │   ├── Chat.Provider.tsx
│   │   │   ├── Chat.MessageList.tsx
│   │   │   ├── Chat.AgentStatus.tsx
│   │   │   ├── Chat.Input.tsx
│   │   │   ├── Chat.Actions.tsx
│   │   │   ├── ChatMessage.tsx
│   │   │   ├── RoleBadge.tsx
│   │   │   ├── StreamingTextContent.tsx
│   │   │   ├── AgentInvocationCard.tsx
│   │   │   └── ArtifactAnchor.tsx
│   │   ├── preview/
│   │   │   ├── PreviewPane.tsx
│   │   │   ├── PreviewPaneTabs.tsx
│   │   │   ├── MarkdownPreview.tsx
│   │   │   ├── MermaidPreview.tsx
│   │   │   ├── CodePreview.tsx
│   │   │   └── HtmlPreview.tsx
│   │   └── SendToBacklogModal.tsx
│   ├── backlog/
│   │   ├── BacklogShell.tsx
│   │   ├── BacklogFilterBar.tsx
│   │   ├── BacklogList.tsx
│   │   ├── BacklogCard.tsx
│   │   ├── CardActions.tsx
│   │   ├── BacklogEditModal.tsx
│   │   ├── PriorityPicker.tsx
│   │   ├── SchedulePicker.tsx
│   │   ├── CronInput.tsx            (also in ui/)
│   │   ├── TagMultiSelect.tsx
│   │   └── SendToCodeBoardModal.tsx
│   └── crew-map/
│       ├── CrewMapShell.tsx
│       ├── CrewMapFilterBar.tsx
│       ├── ReactFlowCanvas.tsx
│       ├── NodeDetailPanel.tsx
│       ├── nodes/
│       │   ├── ProjectNode.tsx
│       │   ├── FeatureNode.tsx
│       │   ├── OrchestratorNode.tsx
│       │   ├── SkillNode.tsx
│       │   └── ConversationNode.tsx
│       └── edges/
│           ├── ActiveEdge.tsx
│           └── PastEdge.tsx
│
├── hooks/
│   ├── useConversationStream.ts       SSE + exponential backoff
│   ├── useStudio.ts                   React Query CRUD for conversations
│   ├── useBacklog.ts                  React Query CRUD for feature requests
│   └── useCrewMap.ts                  React Query + subgraph expansion
│
├── stores/
│   ├── useStudioStore.ts              Zustand — tabs, drafts, panel ratio
│   └── useWorkspaceStore.ts           Zustand — last visited workspace
│
├── contexts/
│   └── TenantContext.tsx              workspaceId + tenantHeaders
│
└── lib/api/
    └── workspace-client.ts            workspaceFetch() + tenant headers
```

---

## Appendix B — Integration with Existing Sidebar

Add to `components/layout/sidebar.tsx` navigation array (after CodeBoard, before Projects):

```ts
{ name: 'Studio', href: '/workspace', icon: MessageSquare },
```

The `/workspace` route immediately redirects to `/workspace/[lastId]/studio` using the last visited workspace from `useWorkspaceStore`. This creates a single sidebar entry that serves as the front door to the entire Workspace layer.

---

## Appendix C — SSE Reconnect Spec

| Scenario | Behaviour |
|---|---|
| Clean disconnect (server close) | Reconnect immediately (0ms delay) |
| Network blip (`onerror` fires) | Backoff: 1s → 2s → 4s → 8s → 16s → cap 30s |
| Tab hidden for >30min (hibernation) | EventSource stays open; backend may close subprocess. Resume call re-opens. |
| Workspace switch | Old EventSource closed immediately on route change. New one opens for new workspace. |
| Max 8 concurrent SSE connections | Enforced client-side: opening a 9th tab closes the oldest idle tab's EventSource. |
| Auth error (401 from SSE endpoint) | Do not retry. Show "Session expired" toast + prompt re-login. |

---

## Appendix D — Cloud-Friendliness Checklist

- [x] All API URLs read from `process.env.NEXT_PUBLIC_API_URL` — no `localhost` in new code
- [x] Workspace ID in `X-Workspace-Id` header on every request via `workspaceFetch()`
- [x] SSE auto-reconnect with exponential backoff
- [x] React Query keys tenant-scoped — no cross-workspace cache pollution
- [x] `localStorage` keys namespaced by `workspaceId` (e.g., `studio-panel-v1-${workspaceId}`)
- [x] Feature flag `WORKSPACE_ENABLED=true` env var gates `/workspace` routes (from E8.S3)
- [x] No hardcoded ports in frontend code — backend URL is a single env var
- [x] `AutoPilotFloatingBar` unchanged — already cloud-ready (reads from context, not hardcoded URL)
