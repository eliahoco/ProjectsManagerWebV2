/**
 * GitHub Connect API Route
 * POST /api/github/connect - Create GitHub repo and connect project
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { execCommand, getGitStatus } from '@/lib/shell';
import path from 'path';

interface ConnectRequest {
  projectId: string;
}

export async function POST(request: NextRequest) {
  try {
    const body: ConnectRequest = await request.json();
    const { projectId } = body;

    // Get project from database
    const project = await prisma.project.findUnique({
      where: { id: projectId },
    });

    if (!project) {
      return NextResponse.json(
        { success: false, error: 'Project not found' },
        { status: 404 }
      );
    }

    // Check current git status
    const gitStatus = await getGitStatus(project.path);

    if (!gitStatus.hasGit) {
      // Initialize git if needed
      await execCommand('git init', { cwd: project.path, timeout: 10000 });
    }

    if (gitStatus.hasRemote) {
      return NextResponse.json({
        success: false,
        error: 'Project already has a remote configured',
      });
    }

    // Get project name for repo name (sanitize it)
    const repoName = path.basename(project.path)
      .replace(/[^a-zA-Z0-9-_]/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '');

    // Check if gh CLI is available
    const ghCheck = await execCommand('which gh', { timeout: 5000 });
    if (ghCheck.exitCode !== 0) {
      return NextResponse.json({
        success: false,
        error: 'GitHub CLI (gh) not installed. Install it with: brew install gh',
      });
    }

    // Check if authenticated
    const authCheck = await execCommand('gh auth status', { timeout: 10000 });
    if (authCheck.exitCode !== 0) {
      return NextResponse.json({
        success: false,
        error: 'Not authenticated with GitHub. Run: gh auth login',
      });
    }

    // Add .gitignore entries for common files
    const gitignoreAdditions = `
# macOS resource forks
._*

# Environment files
.env
.env.local
`;
    await execCommand(`echo '${gitignoreAdditions}' >> .gitignore`, {
      cwd: project.path,
      timeout: 5000,
    });

    // Stage all files
    await execCommand('git add -A', { cwd: project.path, timeout: 30000 });

    // Check if there's anything to commit
    const statusCheck = await execCommand('git status --porcelain', {
      cwd: project.path,
      timeout: 10000,
    });

    if (statusCheck.stdout.trim()) {
      // Create initial commit
      const commitResult = await execCommand(
        'git commit -m "Initial commit"',
        { cwd: project.path, timeout: 30000 }
      );

      if (commitResult.exitCode !== 0 && !commitResult.stderr.includes('nothing to commit')) {
        return NextResponse.json({
          success: false,
          error: `Failed to create commit: ${commitResult.stderr}`,
        });
      }
    }

    // Create GitHub repo (private by default)
    const createResult = await execCommand(
      `gh repo create ${repoName} --private --source=. --remote=origin --push`,
      { cwd: project.path, timeout: 120000 }
    );

    if (createResult.exitCode !== 0) {
      // Check if repo already exists
      if (createResult.stderr.includes('already exists')) {
        return NextResponse.json({
          success: false,
          error: `Repository '${repoName}' already exists on GitHub. Choose a different name or delete the existing repo.`,
        });
      }
      return NextResponse.json({
        success: false,
        error: createResult.stderr || 'Failed to create GitHub repository',
      });
    }

    // Get updated status
    const newStatus = await getGitStatus(project.path);

    return NextResponse.json({
      success: true,
      data: {
        output: createResult.stdout || `Repository created: ${repoName}`,
        repoName,
        gitStatus: newStatus,
      },
    });
  } catch (error) {
    console.error('Error connecting to GitHub:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to connect to GitHub' },
      { status: 500 }
    );
  }
}
