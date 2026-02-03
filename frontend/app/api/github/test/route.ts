/**
 * GitHub Test API Route
 * POST /api/github/test - Test and configure git credentials
 */

import { NextRequest, NextResponse } from 'next/server';
import { execCommand } from '@/lib/shell';
import prisma from '@/lib/db';

interface TestRequest {
  username: string;
  email: string;
}

export async function POST(request: NextRequest) {
  try {
    const body: TestRequest = await request.json();
    const { username, email } = body;

    if (!username || !email) {
      return NextResponse.json(
        { success: false, error: 'Username and email are required' },
        { status: 400 }
      );
    }

    // Test if git is available
    const gitVersion = await execCommand('git --version');
    if (gitVersion.exitCode !== 0) {
      return NextResponse.json(
        { success: false, error: 'Git is not installed or not in PATH' },
        { status: 400 }
      );
    }

    // Set global git config
    const setName = await execCommand(`git config --global user.name "${username}"`);
    if (setName.exitCode !== 0) {
      return NextResponse.json(
        { success: false, error: 'Failed to set git user.name' },
        { status: 500 }
      );
    }

    const setEmail = await execCommand(`git config --global user.email "${email}"`);
    if (setEmail.exitCode !== 0) {
      return NextResponse.json(
        { success: false, error: 'Failed to set git user.email' },
        { status: 500 }
      );
    }

    // Verify the settings
    const verifyName = await execCommand('git config --global user.name');
    const verifyEmail = await execCommand('git config --global user.email');

    // Save to database
    await prisma.setting.upsert({
      where: { key: 'githubUsername' },
      update: { value: username },
      create: { key: 'githubUsername', value: username },
    });

    await prisma.setting.upsert({
      where: { key: 'githubEmail' },
      update: { value: email },
      create: { key: 'githubEmail', value: email },
    });

    return NextResponse.json({
      success: true,
      data: {
        gitVersion: gitVersion.stdout.trim(),
        username: verifyName.stdout.trim(),
        email: verifyEmail.stdout.trim(),
        configured: true,
      },
    });
  } catch (error) {
    console.error('Error testing GitHub config:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to test GitHub configuration' },
      { status: 500 }
    );
  }
}

// GET - Check current git configuration
export async function GET() {
  try {
    const gitVersion = await execCommand('git --version');
    const userName = await execCommand('git config --global user.name');
    const userEmail = await execCommand('git config --global user.email');

    // Also get from database
    const dbUsername = await prisma.setting.findUnique({ where: { key: 'githubUsername' } });
    const dbEmail = await prisma.setting.findUnique({ where: { key: 'githubEmail' } });
    const dbToken = await prisma.setting.findUnique({ where: { key: 'githubToken' } });

    return NextResponse.json({
      success: true,
      data: {
        gitInstalled: gitVersion.exitCode === 0,
        gitVersion: gitVersion.stdout.trim(),
        globalConfig: {
          username: userName.stdout.trim(),
          email: userEmail.stdout.trim(),
        },
        savedConfig: {
          username: dbUsername?.value || '',
          email: dbEmail?.value || '',
          hasToken: !!dbToken?.value,
        },
      },
    });
  } catch (error) {
    console.error('Error getting GitHub config:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to get GitHub configuration' },
      { status: 500 }
    );
  }
}
