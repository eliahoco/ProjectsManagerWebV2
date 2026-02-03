/**
 * Settings API Route
 * GET /api/settings - Get all settings
 * POST /api/settings - Update settings
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';

// Default settings
const DEFAULT_SETTINGS: Record<string, string> = {
  projectsDir: process.env.PROJECTS_DIR || './projects',
  autoRefresh: 'true',
  refreshInterval: '10',
  terminalApp: 'wezterm',
  githubUsername: '',
  githubEmail: '',
  githubToken: '',
  githubAutoConnect: 'true',
};

export async function GET() {
  try {
    const settings = await prisma.setting.findMany();

    // Merge with defaults
    const settingsMap: Record<string, string> = { ...DEFAULT_SETTINGS };
    for (const setting of settings) {
      settingsMap[setting.key] = setting.value;
    }

    return NextResponse.json({
      success: true,
      data: settingsMap,
    });
  } catch (error) {
    console.error('Error fetching settings:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to fetch settings' },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const updates: Array<{ key: string; value: string }> = [];

    // Validate and collect updates
    for (const [key, value] of Object.entries(body)) {
      if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        updates.push({ key, value: String(value) });
      }
    }

    // Upsert each setting
    for (const { key, value } of updates) {
      await prisma.setting.upsert({
        where: { key },
        update: { value },
        create: { key, value },
      });
    }

    // Return updated settings
    const settings = await prisma.setting.findMany();
    const settingsMap: Record<string, string> = { ...DEFAULT_SETTINGS };
    for (const setting of settings) {
      settingsMap[setting.key] = setting.value;
    }

    return NextResponse.json({
      success: true,
      data: settingsMap,
    });
  } catch (error) {
    console.error('Error updating settings:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to update settings' },
      { status: 500 }
    );
  }
}
