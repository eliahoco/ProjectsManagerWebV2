'use client';

/**
 * Create Page - New project creation wizard
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { FolderPlus, ArrowRight, ArrowLeft, Check, AlertCircle, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

type Step = 'name' | 'type' | 'ports' | 'review';

const PROJECT_TYPES = [
  { id: 'nextjs', name: 'Next.js', description: 'Full-stack React framework' },
  { id: 'fastapi', name: 'FastAPI', description: 'Python async API framework' },
  { id: 'express', name: 'Express.js', description: 'Node.js web framework' },
  { id: 'django', name: 'Django', description: 'Python web framework' },
  { id: 'go', name: 'Go', description: 'Go web service' },
  { id: 'custom', name: 'Custom', description: 'Manual configuration' },
];

const SERVICE_PRESETS: Record<string, Array<{ name: string; type: string; port: number }>> = {
  nextjs: [
    { name: 'Frontend (Next.js)', type: 'FRONTEND', port: 3000 },
  ],
  fastapi: [
    { name: 'Backend API (FastAPI)', type: 'BACKEND', port: 8000 },
    { name: 'PostgreSQL', type: 'DATABASE', port: 5432 },
    { name: 'Redis', type: 'CACHE', port: 6379 },
  ],
  express: [
    { name: 'Backend API (Express)', type: 'BACKEND', port: 3000 },
    { name: 'PostgreSQL', type: 'DATABASE', port: 5432 },
  ],
  django: [
    { name: 'Backend (Django)', type: 'BACKEND', port: 8000 },
    { name: 'PostgreSQL', type: 'DATABASE', port: 5432 },
    { name: 'Redis', type: 'CACHE', port: 6379 },
  ],
  go: [
    { name: 'Backend (Go)', type: 'BACKEND', port: 8080 },
  ],
  custom: [],
};

export default function CreatePage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>('name');
  const [projectName, setProjectName] = useState('');
  const [description, setDescription] = useState('');
  const [projectType, setProjectType] = useState('');
  const [services, setServices] = useState<Array<{ name: string; type: string; port: number }>>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const steps: Step[] = ['name', 'type', 'ports', 'review'];
  const currentStepIndex = steps.indexOf(step);

  const handleTypeSelect = (typeId: string) => {
    setProjectType(typeId);
    setServices(SERVICE_PRESETS[typeId] || []);
  };

  const handleNext = () => {
    const nextIndex = currentStepIndex + 1;
    if (nextIndex < steps.length) {
      setStep(steps[nextIndex]);
    }
  };

  const handleBack = () => {
    const prevIndex = currentStepIndex - 1;
    if (prevIndex >= 0) {
      setStep(steps[prevIndex]);
    }
  };

  const handleCreate = async () => {
    setIsCreating(true);
    setError(null);

    try {
      const res = await fetch('/api/projects/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: projectName,
          description,
          type: projectType,
          services,
        }),
      });

      const data = await res.json();

      if (data.success) {
        setSuccess(true);
        // Redirect to the new project after 2 seconds
        setTimeout(() => {
          router.push(`/projects/${data.data.id}`);
        }, 2000);
      } else {
        setError(data.error || 'Failed to create project');
      }
    } catch (err) {
      console.error('Error creating project:', err);
      setError('Failed to create project. Please try again.');
    } finally {
      setIsCreating(false);
    }
  };

  const canProceed = () => {
    switch (step) {
      case 'name':
        return projectName.trim().length > 0;
      case 'type':
        return projectType !== '';
      case 'ports':
        return true;
      case 'review':
        return true;
      default:
        return false;
    }
  };

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <FolderPlus className="h-7 w-7 text-cyan-500" />
          Create New Project
        </h1>
        <p className="text-zinc-400 mt-1">
          Set up a new project with port allocation
        </p>
      </div>

      {/* Progress Steps */}
      <div className="flex items-center justify-between mb-8">
        {steps.map((s, index) => (
          <div key={s} className="flex items-center">
            <div
              className={cn(
                'w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium',
                index < currentStepIndex
                  ? 'bg-cyan-600 text-white'
                  : index === currentStepIndex
                  ? 'bg-cyan-600 text-white'
                  : 'bg-zinc-800 text-zinc-500'
              )}
            >
              {index < currentStepIndex ? <Check className="h-4 w-4" /> : index + 1}
            </div>
            <span className={cn(
              'ml-2 text-sm capitalize',
              index <= currentStepIndex ? 'text-white' : 'text-zinc-500'
            )}>
              {s}
            </span>
            {index < steps.length - 1 && (
              <div className={cn(
                'w-16 h-0.5 mx-4',
                index < currentStepIndex ? 'bg-cyan-600' : 'bg-zinc-800'
              )} />
            )}
          </div>
        ))}
      </div>

      {/* Step Content */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 mb-6">
        {step === 'name' && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Project Name
              </label>
              <input
                type="text"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                placeholder="MyAwesomeProject"
                className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-cyan-500"
              />
              <p className="text-xs text-zinc-500 mt-1">
                Use PascalCase, no spaces (e.g., MyProjectName)
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Description (optional)
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="A brief description of your project..."
                rows={3}
                className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 resize-none"
              />
            </div>
          </div>
        )}

        {step === 'type' && (
          <div>
            <p className="text-zinc-400 mb-4">Select the primary framework for your project:</p>
            <div className="grid grid-cols-2 gap-3">
              {PROJECT_TYPES.map((type) => (
                <button
                  key={type.id}
                  onClick={() => handleTypeSelect(type.id)}
                  className={cn(
                    'p-4 rounded-lg border text-left transition-colors',
                    projectType === type.id
                      ? 'border-cyan-500 bg-cyan-500/10'
                      : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                  )}
                >
                  <p className="font-medium text-white">{type.name}</p>
                  <p className="text-sm text-zinc-400">{type.description}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {step === 'ports' && (
          <div>
            <p className="text-zinc-400 mb-4">Configure services and ports:</p>
            {services.length > 0 ? (
              <div className="space-y-3">
                {services.map((service, index) => (
                  <div key={index} className="flex items-center gap-4 p-3 bg-zinc-800 rounded-lg">
                    <input
                      type="text"
                      value={service.name}
                      onChange={(e) => {
                        const newServices = [...services];
                        newServices[index].name = e.target.value;
                        setServices(newServices);
                      }}
                      className="flex-1 px-3 py-1.5 bg-zinc-700 border border-zinc-600 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    />
                    <select
                      value={service.type}
                      onChange={(e) => {
                        const newServices = [...services];
                        newServices[index].type = e.target.value;
                        setServices(newServices);
                      }}
                      className="px-3 py-1.5 bg-zinc-700 border border-zinc-600 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    >
                      <option value="FRONTEND">Frontend</option>
                      <option value="BACKEND">Backend</option>
                      <option value="DATABASE">Database</option>
                      <option value="CACHE">Cache</option>
                      <option value="OTHER">Other</option>
                    </select>
                    <input
                      type="number"
                      value={service.port}
                      onChange={(e) => {
                        const newServices = [...services];
                        newServices[index].port = parseInt(e.target.value) || 0;
                        setServices(newServices);
                      }}
                      className="w-24 px-3 py-1.5 bg-zinc-700 border border-zinc-600 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    />
                    <button
                      onClick={() => setServices(services.filter((_, i) => i !== index))}
                      className="text-red-400 hover:text-red-300"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-zinc-500 text-center py-8">No services configured</p>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setServices([...services, { name: 'New Service', type: 'BACKEND', port: 8000 }])}
              className="mt-4"
            >
              + Add Service
            </Button>
          </div>
        )}

        {step === 'review' && (
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-white">Review Configuration</h3>
            <div className="space-y-2">
              <div className="flex justify-between py-2 border-b border-zinc-800">
                <span className="text-zinc-400">Project Name</span>
                <span className="text-white">{projectName}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-zinc-800">
                <span className="text-zinc-400">Type</span>
                <span className="text-white">{PROJECT_TYPES.find(t => t.id === projectType)?.name}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-zinc-800">
                <span className="text-zinc-400">Description</span>
                <span className="text-white">{description || '-'}</span>
              </div>
              <div className="py-2">
                <span className="text-zinc-400">Services</span>
                <div className="mt-2 space-y-1">
                  {services.map((s, i) => (
                    <div key={i} className="flex justify-between text-sm">
                      <span className="text-zinc-300">{s.name}</span>
                      <span className="text-cyan-400">:{s.port}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span className="text-sm">{error}</span>
              </div>
            )}

            {success && (
              <div className="flex items-center gap-2 p-3 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400">
                <CheckCircle className="h-4 w-4 flex-shrink-0" />
                <span className="text-sm">Project created successfully! Redirecting...</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="flex justify-between">
        <Button
          variant="outline"
          onClick={handleBack}
          disabled={currentStepIndex === 0}
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>

        {step === 'review' ? (
          <Button
            variant="default"
            onClick={handleCreate}
            loading={isCreating}
            disabled={success}
          >
            {success ? 'Created!' : 'Create Project'}
            <Check className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            variant="default"
            onClick={handleNext}
            disabled={!canProceed()}
          >
            Next
            <ArrowRight className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
}
