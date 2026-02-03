/**
 * Project Services HTML API Route
 * GET /api/projects/[id]/services - Get services HTML page for a project
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const project = await prisma.project.findUnique({
      where: { id },
      include: { ports: true },
    });

    if (!project) {
      return NextResponse.json(
        { success: false, error: 'Project not found' },
        { status: 404 }
      );
    }

    // Always generate fresh HTML with current project data
    const html = generateServicesHtml(project);
    return new NextResponse(html, {
      headers: {
        'Content-Type': 'text/html',
      },
    });
  } catch (error) {
    console.error('Error fetching project services:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to fetch project services' },
      { status: 500 }
    );
  }
}

function generateServicesHtml(project: {
  name: string;
  description: string | null;
  path: string;
  status: string;
  type: string | null;
  version: string | null;
  createdAt: Date;
  updatedAt: Date;
  ports: Array<{
    port: number;
    serviceName: string;
    serviceType: string;
    protocol: string;
    internalPort: number | null;
    url: string | null;
    notes: string | null;
    createdAt: Date;
  }>;
}) {
  const portsHtml = project.ports
    .sort((a, b) => a.port - b.port)
    .map(
      (port) =>
        `<tr>
          <td>${port.port}</td>
          <td>${port.serviceName}</td>
          <td><span class="badge badge-${port.serviceType.toLowerCase()}">${port.serviceType}</span></td>
          <td>${port.protocol}</td>
          <td>${port.internalPort || '-'}</td>
          <td>${
            port.url?.startsWith('http')
              ? `<a href="${port.url}" target="_blank" style="color:#4fc3f7">${port.url}</a>`
              : port.url || '-'
          }</td>
          <td>${port.notes || '-'}</td>
        </tr>`
    )
    .join('\n');

  const quickLinks = project.ports
    .filter((p) => p.url?.startsWith('http'))
    .map((p) => `<a href="${p.url}" target="_blank">${p.serviceName}: ${p.url}</a>`)
    .join('\n');

  return `<!DOCTYPE html>
<html>
<head>
    <title>${project.name} - Services</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1e1e1e; color: #e0e0e0; padding: 40px; margin: 0; }
        h1 { color: #4fc3f7; border-bottom: 2px solid #4fc3f7; padding-bottom: 10px; }
        h2 { color: #81c784; margin-top: 30px; }
        h3 { color: #ffb74d; }
        table { border-collapse: collapse; width: 100%; margin: 20px 0; }
        th, td { border: 1px solid #444; padding: 12px; text-align: left; }
        th { background: #2d2d2d; color: #4fc3f7; }
        tr:nth-child(even) { background: #252525; }
        tr:hover { background: #333; }
        a { color: #4fc3f7; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .description { background: #2d2d2d; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #4fc3f7; }
        .quick-links { display: flex; gap: 10px; flex-wrap: wrap; margin: 20px 0; }
        .quick-links a { background: #4fc3f7; color: #1e1e1e; padding: 10px 20px; border-radius: 5px; font-weight: bold; }
        .quick-links a:hover { background: #81d4fa; text-decoration: none; }
        .back-link { margin-bottom: 20px; }
        .back-link a { color: #4fc3f7; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
        .badge-frontend { background: #4caf50; color: white; }
        .badge-backend { background: #2196f3; color: white; }
        .badge-database { background: #9c27b0; color: white; }
        .badge-cache { background: #ff9800; color: white; }
        .badge-queue { background: #f44336; color: white; }
        .badge-monitoring { background: #00bcd4; color: white; }
        .badge-other { background: #607d8b; color: white; }
        .stats { display: flex; gap: 20px; margin: 20px 0; flex-wrap: wrap; }
        .stat-card { background: #2d2d2d; padding: 15px 25px; border-radius: 8px; text-align: center; }
        .stat-value { font-size: 24px; font-weight: bold; color: #4fc3f7; }
        .stat-label { font-size: 12px; color: #888; margin-top: 5px; }
        .project-info { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
        .info-item { background: #2d2d2d; padding: 15px; border-radius: 8px; }
        .info-label { font-size: 12px; color: #888; margin-bottom: 5px; }
        .info-value { font-size: 16px; color: #e0e0e0; }
        .status-badge { padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; display: inline-block; }
        .status-active { background: #4caf50; color: white; }
        .status-deprecated { background: #ff9800; color: white; }
        .status-archived { background: #9e9e9e; color: white; }
    </style>
</head>
<body>
    <div class="back-link">
        <a href="http://localhost:3601">← Back to Projects Manager</a>
    </div>

    <h1>🚀 ${project.name}</h1>

    <div class="description">
        <strong>Description:</strong> ${project.description || 'No description available'}
    </div>

    <h2>📋 Project Information</h2>
    <div class="project-info">
        <div class="info-item">
            <div class="info-label">Status</div>
            <div class="info-value"><span class="status-badge status-${project.status.toLowerCase()}">${project.status}</span></div>
        </div>
        <div class="info-item">
            <div class="info-label">Type</div>
            <div class="info-value">${project.type || 'Not specified'}</div>
        </div>
        <div class="info-item">
            <div class="info-label">Version</div>
            <div class="info-value">${project.version || 'Not specified'}</div>
        </div>
        <div class="info-item">
            <div class="info-label">Created</div>
            <div class="info-value">${new Date(project.createdAt).toLocaleDateString()}</div>
        </div>
        <div class="info-item">
            <div class="info-label">Last Updated</div>
            <div class="info-value">${new Date(project.updatedAt).toLocaleDateString()}</div>
        </div>
    </div>

    <h2>📈 Service Statistics</h2>
    <div class="stats">
        <div class="stat-card">
            <div class="stat-value">${project.ports.length}</div>
            <div class="stat-label">Total Services</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${project.ports.filter(p => p.url?.startsWith('http')).length}</div>
            <div class="stat-label">Web Services</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${project.ports.filter(p => p.serviceType === 'DATABASE').length}</div>
            <div class="stat-label">Databases</div>
        </div>
    </div>

    <h2>🔌 Quick Links</h2>
    <div class="quick-links">
        ${quickLinks || '<span style="color:#888">No web services configured</span>'}
    </div>

    <h2>📊 All Services</h2>
    <table>
        <tr><th>Port</th><th>Service Name</th><th>Type</th><th>Protocol</th><th>Internal Port</th><th>URL</th><th>Notes</th></tr>
        ${portsHtml || '<tr><td colspan="7" style="text-align:center;color:#888">No services configured</td></tr>'}
    </table>

    <h2>📁 Project Path</h2>
    <div class="description">
        <code>${project.path}</code>
    </div>

    <p style="color:#666; margin-top:40px; font-size:12px;">Generated by Projects Manager Web at ${new Date().toLocaleString()}</p>
</body>
</html>`;
}
