# Multi-AI Support Roadmap

**Status:** Phase 1 Complete
**Decision:** Option C (Hybrid Approach), Local Only
**Last Updated:** 2026-01-20

---

## Chosen Approach: Hybrid (Local Only)

User preference: Keep everything local, no cloud API dependencies.

---

## Implementation Phases

### Phase 1 - External Launch Expansion ✅ COMPLETED
- [x] Add buttons for multiple AI tools (Claude Code, Cursor, VS Code)
- [x] Quick links to web-based AIs with project context copied to clipboard
- [x] UI: Provider selector dropdown in project card and detail page

**Implementation Details:**
- Created `lib/ai-providers.ts` - AI provider configuration
- Created `components/projects/ai-launcher.tsx` - Dropdown component
- Created `app/api/projects/[id]/open-ai/route.ts` - API endpoint
- Updated `lib/shell.ts` - Added `openInCursor()` and `openInVSCode()` functions
- Updated `components/projects/project-card.tsx` - Integrated AILauncher
- Updated `app/projects/[id]/page.tsx` - Integrated AILauncher
- Updated `app/page.tsx` - Updated handler for multi-AI support

**Supported Providers:**
| Provider | Type | Action |
|----------|------|--------|
| Claude Code | Local | Opens terminal with Claude CLI |
| Cursor | Local | Opens project in Cursor editor |
| VS Code | Local | Opens project in VS Code |
| ChatGPT | Web | Copies context, opens ChatGPT |
| Gemini | Web | Copies context, opens Gemini |
| Claude.ai | Web | Copies context, opens Claude.ai |

### Phase 2 - Local AI Integration
- [ ] Support Ollama for free, local AI
- [ ] Support LM Studio
- [ ] Basic chat interface in dashboard
- [ ] No API keys needed, runs on user's machine
- [ ] Store conversations locally in SQLite

### Phase 3 - Enhanced Features (Future)
- [ ] Context injection (send project files to AI)
- [ ] Conversation search
- [ ] Compare responses between models
- [ ] Project-specific AI memory/context

---

## Technical Notes

**Supported Local AI Tools:**
- Ollama (localhost:11434)
- LM Studio (localhost:1234)
- Other local inference servers

**Database Changes Needed:**
- AIProvider table (local providers config)
- Conversation table (message history)
- Settings for default provider per project

---

## Files Changed in Phase 1

```
lib/ai-providers.ts              # NEW - Provider definitions
lib/shell.ts                     # UPDATED - Added Cursor/VS Code launchers
components/projects/ai-launcher.tsx  # NEW - Dropdown component
app/api/projects/[id]/open-ai/route.ts  # NEW - API endpoint
components/projects/project-card.tsx    # UPDATED - Uses AILauncher
app/projects/[id]/page.tsx       # UPDATED - Uses AILauncher
app/page.tsx                     # UPDATED - handleOpenAI function
```

---

## Resume Point

Phase 1 is complete. Ready to start Phase 2 (Local AI Integration) when user requests.
