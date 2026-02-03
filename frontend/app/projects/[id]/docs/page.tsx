'use client';

/**
 * Project Documentation & Conversations Page
 * View project docs, conversation history, and plans
 */

import { useState, useEffect, use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  FileText,
  MessageSquare,
  Clock,
  RefreshCw,
  ChevronRight,
  Search,
  File,
  Calendar,
  GitBranch,
  ExternalLink,
  Copy,
  Check,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import { cn, formatDate } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';

interface DocFile {
  name: string;
  path: string;
  size: number;
  modified: string;
}

interface Session {
  sessionId: string;
  firstPrompt: string;
  messageCount: number;
  created: string;
  modified: string;
  gitBranch: string;
  fileSize: number;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

type TabType = 'docs' | 'conversations';

export default function ProjectDocsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<TabType>('docs');
  const [loading, setLoading] = useState(true);

  // Documentation state
  const [docFiles, setDocFiles] = useState<DocFile[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [docContent, setDocContent] = useState<string>('');
  const [loadingDoc, setLoadingDoc] = useState(false);

  // Conversations state
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Copy state
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Fetch documentation files
  const fetchDocs = async () => {
    try {
      const res = await fetch(`/api/projects/${id}/docs`);
      const data = await res.json();
      if (data.success) {
        setDocFiles(data.data.files);
        // Auto-select first doc if available
        if (data.data.files.length > 0 && !selectedDoc) {
          loadDocContent(data.data.files[0].name);
        }
      }
    } catch (error) {
      console.error('Failed to fetch docs:', error);
    }
  };

  // Load specific doc content
  const loadDocContent = async (fileName: string) => {
    setSelectedDoc(fileName);
    setLoadingDoc(true);
    try {
      const res = await fetch(`/api/projects/${id}/docs?file=${encodeURIComponent(fileName)}`);
      const data = await res.json();
      if (data.success) {
        setDocContent(data.data.content);
      }
    } catch (error) {
      console.error('Failed to load doc:', error);
      toast.error('Load Failed', 'Could not load document');
    } finally {
      setLoadingDoc(false);
    }
  };

  // Fetch conversation sessions
  const fetchSessions = async () => {
    try {
      const res = await fetch(`/api/projects/${id}/conversations`);
      const data = await res.json();
      if (data.success) {
        setSessions(data.data.sessions);
      }
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    }
  };

  // Load messages for a session
  const loadSessionMessages = async (sessionId: string) => {
    setSelectedSession(sessionId);
    setLoadingMessages(true);
    try {
      const res = await fetch(`/api/projects/${id}/conversations?session=${sessionId}`);
      const data = await res.json();
      if (data.success) {
        setMessages(data.data.messages);
      }
    } catch (error) {
      console.error('Failed to load messages:', error);
      toast.error('Load Failed', 'Could not load conversation');
    } finally {
      setLoadingMessages(false);
    }
  };

  // Initial fetch
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchDocs(), fetchSessions()]);
      setLoading(false);
    };
    loadData();
  }, [id]);

  // Copy to clipboard
  const copyToClipboard = (text: string, itemId: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(itemId);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Filter sessions by search
  const filteredSessions = sessions.filter(
    (s) =>
      s.firstPrompt.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.gitBranch.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Format file size
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-zinc-500" />
      </div>
    );
  }

  return (
    <div className="p-6 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <Button variant="ghost" size="sm" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-white">Documentation & History</h1>
          <p className="text-zinc-400 mt-1">
            View project docs, prompts, and conversation history
          </p>
        </div>
        <Link href={`/projects/${id}`}>
          <Button variant="outline" size="sm">
            Back to Project
          </Button>
        </Link>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 mb-6">
        <button
          onClick={() => setActiveTab('docs')}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
            activeTab === 'docs'
              ? 'bg-cyan-500 text-white'
              : 'bg-zinc-800 text-zinc-400 hover:text-white'
          )}
        >
          <FileText className="h-4 w-4" />
          Documentation ({docFiles.length})
        </button>
        <button
          onClick={() => setActiveTab('conversations')}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
            activeTab === 'conversations'
              ? 'bg-cyan-500 text-white'
              : 'bg-zinc-800 text-zinc-400 hover:text-white'
          )}
        >
          <MessageSquare className="h-4 w-4" />
          Conversations ({sessions.length})
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0">
        {activeTab === 'docs' && (
          <div className="grid grid-cols-4 gap-6 h-full">
            {/* File List */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
              <div className="p-3 border-b border-zinc-800">
                <h3 className="text-sm font-medium text-zinc-400">Files</h3>
              </div>
              <div className="overflow-y-auto max-h-[calc(100vh-320px)]">
                {docFiles.length === 0 ? (
                  <div className="p-4 text-center text-zinc-500 text-sm">
                    No documentation files found
                  </div>
                ) : (
                  docFiles.map((file) => (
                    <button
                      key={file.name}
                      onClick={() => loadDocContent(file.name)}
                      className={cn(
                        'w-full flex items-center gap-3 p-3 text-left hover:bg-zinc-800 transition-colors',
                        selectedDoc === file.name && 'bg-zinc-800 border-l-2 border-cyan-500'
                      )}
                    >
                      <File className="h-4 w-4 text-zinc-500 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-white truncate">{file.name}</p>
                        <p className="text-xs text-zinc-500">
                          {formatSize(file.size)} • {formatDate(file.modified)}
                        </p>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>

            {/* Content Viewer */}
            <div className="col-span-3 bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden flex flex-col">
              <div className="p-3 border-b border-zinc-800 flex items-center justify-between">
                <h3 className="text-sm font-medium text-white">
                  {selectedDoc || 'Select a file'}
                </h3>
                {selectedDoc && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => copyToClipboard(docContent, 'doc')}
                  >
                    {copiedId === 'doc' ? (
                      <Check className="h-4 w-4 text-green-400" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                )}
              </div>
              <div className="flex-1 overflow-y-auto p-4">
                {loadingDoc ? (
                  <div className="flex items-center justify-center h-32">
                    <RefreshCw className="h-6 w-6 animate-spin text-zinc-500" />
                  </div>
                ) : docContent ? (
                  <div className="prose prose-invert prose-sm max-w-none">
                    <ReactMarkdown>{docContent}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="text-center text-zinc-500 py-8">
                    Select a file to view its contents
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'conversations' && (
          <div className="grid grid-cols-3 gap-6 h-full">
            {/* Session List */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden flex flex-col">
              <div className="p-3 border-b border-zinc-800">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
                  <input
                    type="text"
                    placeholder="Search sessions..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-9 pr-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  />
                </div>
              </div>
              <div className="flex-1 overflow-y-auto">
                {filteredSessions.length === 0 ? (
                  <div className="p-4 text-center text-zinc-500 text-sm">
                    No conversations found
                  </div>
                ) : (
                  filteredSessions.map((session) => (
                    <button
                      key={session.sessionId}
                      onClick={() => loadSessionMessages(session.sessionId)}
                      className={cn(
                        'w-full p-3 text-left hover:bg-zinc-800 transition-colors border-b border-zinc-800',
                        selectedSession === session.sessionId && 'bg-zinc-800 border-l-2 border-cyan-500'
                      )}
                    >
                      <p className="text-sm text-white line-clamp-2 mb-2">
                        {session.firstPrompt}
                      </p>
                      <div className="flex items-center gap-3 text-xs text-zinc-500">
                        <span className="flex items-center gap-1">
                          <MessageSquare className="h-3 w-3" />
                          {session.messageCount}
                        </span>
                        <span className="flex items-center gap-1">
                          <GitBranch className="h-3 w-3" />
                          {session.gitBranch}
                        </span>
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          {formatDate(session.modified)}
                        </span>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>

            {/* Messages Viewer */}
            <div className="col-span-2 bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden flex flex-col">
              <div className="p-3 border-b border-zinc-800 flex items-center justify-between">
                <h3 className="text-sm font-medium text-white">
                  {selectedSession ? `Conversation (${messages.length} messages)` : 'Select a session'}
                </h3>
                {messages.length > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      const text = messages
                        .map((m) => `${m.role.toUpperCase()}:\n${m.content}`)
                        .join('\n\n---\n\n');
                      copyToClipboard(text, 'messages');
                    }}
                  >
                    {copiedId === 'messages' ? (
                      <Check className="h-4 w-4 text-green-400" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                )}
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {loadingMessages ? (
                  <div className="flex items-center justify-center h-32">
                    <RefreshCw className="h-6 w-6 animate-spin text-zinc-500" />
                  </div>
                ) : messages.length > 0 ? (
                  messages.map((message, idx) => (
                    <div
                      key={idx}
                      className={cn(
                        'p-3 rounded-lg',
                        message.role === 'user'
                          ? 'bg-cyan-500/10 border border-cyan-500/30'
                          : 'bg-zinc-800'
                      )}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <span
                          className={cn(
                            'text-xs font-medium px-2 py-0.5 rounded',
                            message.role === 'user'
                              ? 'bg-cyan-500/20 text-cyan-400'
                              : 'bg-zinc-700 text-zinc-400'
                          )}
                        >
                          {message.role === 'user' ? 'You' : 'Claude'}
                        </span>
                      </div>
                      <div className="text-sm text-zinc-300 whitespace-pre-wrap break-words">
                        {message.content.length > 2000
                          ? message.content.substring(0, 2000) + '...'
                          : message.content}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-center text-zinc-500 py-8">
                    Select a session to view the conversation
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
