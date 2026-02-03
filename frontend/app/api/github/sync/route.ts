/**
 * GitHub Sync API Route
 * POST /api/github/sync - Sync project to GitHub (commit and push)
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { execCommand, syncToGitHub, getGitStatus, configureGitCredentials } from '@/lib/shell';

interface SyncRequest {
  projectId: string;
  message?: string;
  action: 'push' | 'pull' | 'status';
}

/**
 * Auto-configure git credentials if enabled in settings
 */
async function autoConfigureGit(): Promise<void> {
  try {
    // Check if auto-connect is enabled
    const autoConnectSetting = await prisma.setting.findUnique({
      where: { key: 'githubAutoConnect' },
    });

    if (autoConnectSetting?.value !== 'true') {
      return;
    }

    // Get saved credentials
    const usernameSetting = await prisma.setting.findUnique({
      where: { key: 'githubUsername' },
    });
    const emailSetting = await prisma.setting.findUnique({
      where: { key: 'githubEmail' },
    });
    const tokenSetting = await prisma.setting.findUnique({
      where: { key: 'githubToken' },
    });

    if (usernameSetting?.value && emailSetting?.value) {
      await configureGitCredentials(
        usernameSetting.value,
        emailSetting.value,
        tokenSetting?.value
      );
    }
  } catch (error) {
    console.error('Auto-configure git failed:', error);
  }
}

export async function POST(request: NextRequest) {
  try {
    const body: SyncRequest = await request.json();
    const { projectId, message, action } = body;

    // Auto-configure git credentials before operations
    await autoConfigureGit();

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

    // Check git status first
    const gitStatus = await getGitStatus(project.path);

    if (!gitStatus.hasGit) {
      return NextResponse.json(
        { success: false, error: 'Project is not a git repository' },
        { status: 400 }
      );
    }

    if (action === 'status') {
      return NextResponse.json({
        success: true,
        data: gitStatus,
      });
    }

    if (action === 'pull') {
      const result = await execCommand('git pull', {
        cwd: project.path,
        timeout: 60000,
      });

      return NextResponse.json({
        success: result.exitCode === 0,
        data: {
          output: result.stdout || result.stderr,
          exitCode: result.exitCode,
        },
      });
    }

    if (action === 'push') {
      if (!gitStatus.hasRemote) {
        return NextResponse.json(
          { success: false, error: 'No remote repository configured' },
          { status: 400 }
        );
      }

      // Generate commit message
      const commitMessage = message || `Update ${project.name} - ${new Date().toISOString().split('T')[0]}`;

      // Sync to GitHub
      const result = await syncToGitHub(project.path, commitMessage);

      // Get updated status
      const newStatus = await getGitStatus(project.path);

      const isSuccess = result.exitCode === 0 || result.stderr.includes('nothing to commit');

      if (!isSuccess) {
        return NextResponse.json({
          success: false,
          error: result.stderr || result.stdout || 'Push failed - check git credentials and remote configuration',
          data: {
            output: result.stdout || result.stderr,
            exitCode: result.exitCode,
            gitStatus: newStatus,
          },
        });
      }

      return NextResponse.json({
        success: true,
        data: {
          output: result.stdout || result.stderr,
          exitCode: result.exitCode,
          gitStatus: newStatus,
        },
      });
    }

    return NextResponse.json(
      { success: false, error: 'Invalid action' },
      { status: 400 }
    );
  } catch (error) {
    console.error('Error syncing to GitHub:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to sync to GitHub' },
      { status: 500 }
    );
  }
}
