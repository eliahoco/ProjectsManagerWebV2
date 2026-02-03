/**
 * Database Seed Script
 * Migrates data from the existing ports.db SQLite database to the new Prisma schema
 */

import { PrismaClient } from '@prisma/client';
import Database from 'better-sqlite3';
import path from 'path';

const prisma = new PrismaClient();

// Source database path
const SOURCE_DB = process.env.SOURCE_PORTS_DB || './data/ports.db';
const PROJECTS_DIR = process.env.PROJECTS_DIR || './projects';

interface OldProject {
  id: number;
  name: string;
  path: string;
  status: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

interface OldPort {
  id: number;
  project_id: number;
  port: number;
  service_name: string;
  service_type: string;
  protocol: string;
  internal_port: number | null;
  url: string | null;
  notes: string | null;
  created_at: string;
}

interface OldPortRange {
  id: number;
  service_type: string;
  range_start: number;
  range_end: number;
  description: string | null;
}

async function main() {
  console.log('🚀 Starting database migration...');
  console.log(`   Source: ${SOURCE_DB}`);

  // Open source database
  const sourceDb = new Database(SOURCE_DB, { readonly: true });

  try {
    // Clear existing data
    console.log('🗑️  Clearing existing data...');
    await prisma.port.deleteMany();
    await prisma.session.deleteMany();
    await prisma.project.deleteMany();
    await prisma.portRange.deleteMany();
    await prisma.setting.deleteMany();

    // Migrate projects
    console.log('📁 Migrating projects...');
    const oldProjects = sourceDb.prepare('SELECT * FROM projects').all() as OldProject[];

    const projectIdMap = new Map<number, string>();

    for (const oldProject of oldProjects) {
      const newProject = await prisma.project.create({
        data: {
          name: oldProject.name,
          path: oldProject.path || path.join(PROJECTS_DIR, oldProject.name),
          status: oldProject.status?.toUpperCase() || 'ACTIVE',
          description: oldProject.description,
          createdAt: oldProject.created_at ? new Date(oldProject.created_at) : new Date(),
          updatedAt: oldProject.updated_at ? new Date(oldProject.updated_at) : new Date(),
        },
      });
      projectIdMap.set(oldProject.id, newProject.id);
      console.log(`   ✓ ${oldProject.name}`);
    }

    // Migrate ports
    console.log('🔌 Migrating ports...');
    const oldPorts = sourceDb.prepare('SELECT * FROM ports').all() as OldPort[];

    for (const oldPort of oldPorts) {
      const projectId = projectIdMap.get(oldPort.project_id);
      if (!projectId) {
        console.log(`   ⚠️  Skipping port ${oldPort.port} - project not found`);
        continue;
      }

      await prisma.port.create({
        data: {
          projectId,
          port: oldPort.port,
          serviceName: oldPort.service_name,
          serviceType: oldPort.service_type?.toUpperCase() || 'OTHER',
          protocol: oldPort.protocol?.toUpperCase() || 'TCP',
          internalPort: oldPort.internal_port,
          url: oldPort.url,
          notes: oldPort.notes,
          createdAt: oldPort.created_at ? new Date(oldPort.created_at) : new Date(),
        },
      });
    }
    console.log(`   ✓ Migrated ${oldPorts.length} ports`);

    // Migrate port ranges
    console.log('📊 Migrating port ranges...');
    const oldRanges = sourceDb.prepare('SELECT * FROM port_ranges').all() as OldPortRange[];

    for (const oldRange of oldRanges) {
      await prisma.portRange.create({
        data: {
          serviceType: oldRange.service_type,
          rangeStart: oldRange.range_start,
          rangeEnd: oldRange.range_end,
          description: oldRange.description,
        },
      });
    }
    console.log(`   ✓ Migrated ${oldRanges.length} port ranges`);

    // Add default settings
    console.log('⚙️  Adding default settings...');
    await prisma.setting.createMany({
      data: [
        { key: 'projectsDir', value: PROJECTS_DIR },
        { key: 'theme', value: 'dark' },
        { key: 'autoRefresh', value: 'true' },
        { key: 'refreshInterval', value: '5000' },
      ],
    });

    // Print summary
    const projectCount = await prisma.project.count();
    const portCount = await prisma.port.count();
    const rangeCount = await prisma.portRange.count();

    console.log('');
    console.log('✅ Migration complete!');
    console.log(`   Projects: ${projectCount}`);
    console.log(`   Ports: ${portCount}`);
    console.log(`   Port Ranges: ${rangeCount}`);

  } finally {
    sourceDb.close();
    await prisma.$disconnect();
  }
}

main()
  .catch((e) => {
    console.error('❌ Migration failed:', e);
    process.exit(1);
  });
