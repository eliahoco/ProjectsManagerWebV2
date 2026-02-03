'use client';

/**
 * Global Service Monitor
 * Watches all projects for service status changes and shows alerts
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { AlertTriangle, RefreshCw, X, Play, CheckCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ServiceAlert {
  id: string;
  projectId: string;
  projectName: string;
  serviceName: string;
  port: number;
  status: 'stopped' | 'crashed';
  timestamp: Date;
  dismissed: boolean;
}

interface ServiceStatus {
  projectId: string;
  projectName: string;
  services: Array<{
    id: string;
    name: string;
    port: number;
    status: 'running' | 'stopped';
  }>;
}

export function ServiceMonitor() {
  const [alerts, setAlerts] = useState<ServiceAlert[]>([]);
  const [restartingService, setRestartingService] = useState<string | null>(null);
  const previousStatusRef = useRef<Map<string, boolean>>(new Map());
  const [isMinimized, setIsMinimized] = useState(false);

  // Fetch all projects and their service statuses
  const checkServices = useCallback(async () => {
    try {
      const res = await fetch('/api/projects');
      const data = await res.json();

      if (!data.success) return;

      const newAlerts: ServiceAlert[] = [];

      for (const project of data.data.projects) {
        if (!project.services || project.services.length === 0) continue;

        for (const service of project.services) {
          const serviceKey = `${project.id}-${service.port}`;
          const wasRunning = previousStatusRef.current.get(serviceKey);
          const isRunning = service.status === 'running';

          // If service was running and now stopped, create alert
          if (wasRunning === true && !isRunning) {
            const existingAlert = alerts.find(
              a => a.projectId === project.id && a.port === service.port && !a.dismissed
            );

            if (!existingAlert) {
              newAlerts.push({
                id: `${serviceKey}-${Date.now()}`,
                projectId: project.id,
                projectName: project.name,
                serviceName: service.name,
                port: service.port,
                status: 'stopped',
                timestamp: new Date(),
                dismissed: false,
              });
            }
          }

          // Update previous status
          previousStatusRef.current.set(serviceKey, isRunning);
        }
      }

      if (newAlerts.length > 0) {
        setAlerts(prev => [...prev, ...newAlerts]);
      }
    } catch (error) {
      console.error('Error checking services:', error);
    }
  }, [alerts]);

  // Poll every 15 seconds
  useEffect(() => {
    // Initial check after a short delay (to let the page load)
    const initialTimeout = setTimeout(checkServices, 2000);

    const interval = setInterval(checkServices, 15000);

    return () => {
      clearTimeout(initialTimeout);
      clearInterval(interval);
    };
  }, [checkServices]);

  const handleRestart = async (alert: ServiceAlert) => {
    setRestartingService(alert.id);
    try {
      // Find the service ID from the port
      const projectRes = await fetch(`/api/projects/${alert.projectId}`);
      const projectData = await projectRes.json();

      if (projectData.success) {
        const port = projectData.data.ports.find((p: { port: number }) => p.port === alert.port);
        if (port) {
          const res = await fetch(`/api/projects/${alert.projectId}/services/${port.id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'restart' }),
          });
          const data = await res.json();

          if (data.success) {
            // Dismiss the alert
            setAlerts(prev =>
              prev.map(a => (a.id === alert.id ? { ...a, dismissed: true } : a))
            );
          }
        }
      }
    } catch (error) {
      console.error('Error restarting service:', error);
    } finally {
      setRestartingService(null);
    }
  };

  const handleDismiss = (alertId: string) => {
    setAlerts(prev => prev.map(a => (a.id === alertId ? { ...a, dismissed: true } : a)));
  };

  const handleDismissAll = () => {
    setAlerts(prev => prev.map(a => ({ ...a, dismissed: true })));
  };

  const activeAlerts = alerts.filter(a => !a.dismissed);

  if (activeAlerts.length === 0) {
    return null;
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-sm">
      {/* Header */}
      <div
        className={cn(
          'bg-red-900/90 backdrop-blur-sm border border-red-700 rounded-t-lg px-4 py-2 flex items-center justify-between cursor-pointer',
          isMinimized && 'rounded-b-lg'
        )}
        onClick={() => setIsMinimized(!isMinimized)}
      >
        <div className="flex items-center gap-2 text-red-200">
          <AlertTriangle className="h-4 w-4" />
          <span className="font-medium text-sm">
            {activeAlerts.length} Service{activeAlerts.length > 1 ? 's' : ''} Stopped
          </span>
        </div>
        <div className="flex items-center gap-2">
          {activeAlerts.length > 1 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleDismissAll();
              }}
              className="text-xs text-red-300 hover:text-white"
            >
              Dismiss All
            </button>
          )}
          <X
            className="h-4 w-4 text-red-300 hover:text-white cursor-pointer"
            onClick={(e) => {
              e.stopPropagation();
              handleDismissAll();
            }}
          />
        </div>
      </div>

      {/* Alert List */}
      {!isMinimized && (
        <div className="bg-zinc-900/95 backdrop-blur-sm border border-zinc-700 border-t-0 rounded-b-lg max-h-80 overflow-y-auto">
          {activeAlerts.map((alert) => (
            <div
              key={alert.id}
              className="p-3 border-b border-zinc-800 last:border-b-0"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-medium truncate">
                    {alert.projectName}
                  </p>
                  <p className="text-zinc-400 text-xs truncate">
                    {alert.serviceName} (port {alert.port})
                  </p>
                  <p className="text-zinc-500 text-xs mt-1">
                    Stopped at {alert.timestamp.toLocaleTimeString()}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleRestart(alert)}
                    disabled={restartingService === alert.id}
                    className={cn(
                      'p-1.5 rounded-md transition-colors',
                      restartingService === alert.id
                        ? 'bg-zinc-700 text-zinc-400'
                        : 'bg-green-600 hover:bg-green-500 text-white'
                    )}
                    title="Restart Service"
                  >
                    {restartingService === alert.id ? (
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Play className="h-3.5 w-3.5" />
                    )}
                  </button>
                  <button
                    onClick={() => handleDismiss(alert.id)}
                    className="p-1.5 rounded-md bg-zinc-700 hover:bg-zinc-600 text-zinc-300 transition-colors"
                    title="Dismiss"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
