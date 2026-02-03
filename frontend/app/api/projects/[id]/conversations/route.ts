/**
 * Project Conversations API Route
 * GET /api/projects/[id]/conversations - List all Claude sessions
 * GET /api/projects/[id]/conversations?session=sessionId - Get conversation messages
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { readFile, stat } from 'fs/promises';
import path from 'path';
import os from 'os';

interface SessionEntry {
  sessionId: string;
  fullPath: string;
  fileMtime: number;
  firstPrompt: string;
  messageCount: number;
  created: string;
  modified: string;
  gitBranch: string;
  projectPath: string;
  isSidechain: boolean;
}

interface SessionIndex {
  version: number;
  entries: SessionEntry[];
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

// Convert project path to Claude's directory naming format
function getClaudeProjectDir(projectPath: string): string {
  // Claude uses path with slashes replaced by dashes, keeping the leading dash
  return projectPath.replace(/\//g, '-');
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const { searchParams } = new URL(request.url);
    const sessionId = searchParams.get('session');

    // Get project from database
    const project = await prisma.project.findUnique({
      where: { id },
    });

    if (!project) {
      return NextResponse.json(
        { success: false, error: 'Project not found' },
        { status: 404 }
      );
    }

    // Build path to Claude's project directory
    const claudeDir = path.join(
      os.homedir(),
      '.claude',
      'projects',
      getClaudeProjectDir(project.path)
    );

    // If a specific session is requested, return its messages
    if (sessionId) {
      const sessionFile = path.join(claudeDir, `${sessionId}.jsonl`);

      try {
        const content = await readFile(sessionFile, 'utf-8');
        const lines = content.trim().split('\n');
        const messages: Message[] = [];

        for (const line of lines) {
          if (!line.trim()) continue;

          try {
            const entry = JSON.parse(line);

            // Extract user messages (handle different formats)
            if (entry.type === 'user' || entry.type === 'human' || entry.role === 'user') {
              const text = entry.message?.content || entry.content;
              if (text && typeof text === 'string') {
                messages.push({
                  role: 'user',
                  content: text,
                  timestamp: entry.timestamp,
                });
              } else if (Array.isArray(text)) {
                // Handle array content (multimodal)
                const textContent = text.find((t: { type: string }) => t.type === 'text');
                if (textContent?.text) {
                  messages.push({
                    role: 'user',
                    content: textContent.text,
                    timestamp: entry.timestamp,
                  });
                }
              }
            }

            // Extract assistant messages
            if (entry.type === 'assistant' || entry.role === 'assistant') {
              const text = entry.message?.content || entry.content;
              if (text && typeof text === 'string') {
                messages.push({
                  role: 'assistant',
                  content: text,
                  timestamp: entry.timestamp,
                });
              } else if (Array.isArray(text)) {
                // Handle array content
                const textParts = text
                  .filter((t: { type: string }) => t.type === 'text')
                  .map((t: { text: string }) => t.text)
                  .join('\n');
                if (textParts) {
                  messages.push({
                    role: 'assistant',
                    content: textParts,
                    timestamp: entry.timestamp,
                  });
                }
              }
            }
          } catch {
            // Skip malformed JSON lines
          }
        }

        return NextResponse.json({
          success: true,
          data: {
            sessionId,
            messageCount: messages.length,
            messages,
          },
        });
      } catch {
        return NextResponse.json(
          { success: false, error: 'Session not found' },
          { status: 404 }
        );
      }
    }

    // List all sessions for this project
    const sessionsIndexPath = path.join(claudeDir, 'sessions-index.json');
    let sessions: SessionEntry[] = [];
    let useIndex = false;

    try {
      const indexContent = await readFile(sessionsIndexPath, 'utf-8');
      const index: SessionIndex = JSON.parse(indexContent);

      // Filter sessions that belong to this project
      sessions = index.entries.filter(
        (entry) => entry.projectPath === project.path
      );
      useIndex = true;
    } catch {
      // No sessions index, will scan directory
    }

    // If no index or empty, scan directory for .jsonl files
    if (!useIndex || sessions.length === 0) {
      try {
        const { readdir } = await import('fs/promises');
        const files = await readdir(claudeDir);
        const jsonlFiles = files.filter(
          (f) => f.endsWith('.jsonl') && !f.startsWith('agent-')
        );

        sessions = await Promise.all(
          jsonlFiles.map(async (file) => {
            const sessionId = file.replace('.jsonl', '');
            const filePath = path.join(claudeDir, file);
            const stats = await stat(filePath);

            // Read first few lines to get first prompt
            let firstPrompt = 'Session';
            let messageCount = 0;
            try {
              const content = await readFile(filePath, 'utf-8');
              const lines = content.trim().split('\n');
              messageCount = lines.length;

              for (const line of lines.slice(0, 20)) {
                try {
                  const entry = JSON.parse(line);
                  // Handle different JSONL formats
                  if (entry.type === 'user' || entry.type === 'human' || entry.role === 'user') {
                    const text = entry.message?.content || entry.content;
                    if (typeof text === 'string') {
                      // Clean up the prompt - remove system messages
                      const cleanPrompt = text.split('IMPORTANT:')[0].trim();
                      firstPrompt = cleanPrompt.substring(0, 200);
                      break;
                    } else if (Array.isArray(text)) {
                      const textContent = text.find((t: { type: string }) => t.type === 'text');
                      if (textContent?.text) {
                        const cleanPrompt = textContent.text.split('IMPORTANT:')[0].trim();
                        firstPrompt = cleanPrompt.substring(0, 200);
                        break;
                      }
                    }
                  }
                } catch {
                  // Skip malformed lines
                }
              }
            } catch {
              // Could not read file
            }

            return {
              sessionId,
              fullPath: filePath,
              fileMtime: stats.mtimeMs,
              firstPrompt,
              messageCount,
              created: stats.birthtime.toISOString(),
              modified: stats.mtime.toISOString(),
              gitBranch: 'main',
              projectPath: project.path,
              isSidechain: false,
            };
          })
        );
      } catch {
        // Could not scan directory
      }
    }

    // Sort by modified date, most recent first
    sessions.sort(
      (a, b) => new Date(b.modified).getTime() - new Date(a.modified).getTime()
    );

    // Get file sizes for each session
    const sessionsWithSize = await Promise.all(
      sessions.map(async (session) => {
        try {
          const stats = await stat(session.fullPath);
          return {
            ...session,
            fileSize: stats.size,
          };
        } catch {
          return {
            ...session,
            fileSize: 0,
          };
        }
      })
    );

    return NextResponse.json({
      success: true,
      data: {
        projectPath: project.path,
        claudeDir,
        sessionCount: sessionsWithSize.length,
        sessions: sessionsWithSize.map((s) => ({
          sessionId: s.sessionId,
          firstPrompt: s.firstPrompt,
          messageCount: s.messageCount,
          created: s.created,
          modified: s.modified,
          gitBranch: s.gitBranch,
          fileSize: s.fileSize,
        })),
      },
    });
  } catch (error) {
    console.error('Error fetching conversations:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to fetch conversations' },
      { status: 500 }
    );
  }
}
