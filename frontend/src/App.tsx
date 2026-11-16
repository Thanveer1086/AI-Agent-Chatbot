import React, { useState } from 'react';
import { MessageSquare, FolderUp, Cpu, Sparkles } from 'lucide-react';
import { ChatContainer } from './components/chat/ChatContainer';
import { KnowledgeStudio } from './components/admin/KnowledgeStudio';
import { MCPInspector } from './components/admin/MCPInspector';

export default function App() {
  const [activeTab, setActiveTab] = useState<'chat' | 'knowledge' | 'mcp'>('chat');

  return (
    <div className="flex h-screen w-screen flex-col bg-slate-50 text-slate-900">
      {/* Top Header */}
      <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-6 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white shadow-md">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-800 leading-tight">AI Agent ChatBot</h1>
            <p className="text-xs text-slate-500">Autonomous MCP & Advanced RAG System</p>
          </div>
        </div>

        {/* Workspace Navigation Tabs */}
        <nav className="flex items-center gap-1 rounded-lg bg-slate-100 p-1 border border-slate-200">
          <button
            onClick={() => setActiveTab('chat')}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all ${
              activeTab === 'chat'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <MessageSquare className="h-4 w-4" />
            Agent Chat
          </button>
          <button
            onClick={() => setActiveTab('knowledge')}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all ${
              activeTab === 'knowledge'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <FolderUp className="h-4 w-4" />
            Knowledge Studio
          </button>
          <button
            onClick={() => setActiveTab('mcp')}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all ${
              activeTab === 'mcp'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Cpu className="h-4 w-4" />
            MCP Inspector
          </button>
        </nav>

        {/* Backend Status indicator */}
        <div className="flex items-center gap-2">
          <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-medium text-slate-600">FastAPI Online</span>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 overflow-hidden">
        {activeTab === 'chat' && (
          <div id="chat-workspace" className="h-full">
            <ChatContainer />
          </div>
        )}
        {activeTab === 'knowledge' && (
          <div id="knowledge-workspace" className="h-full">
            <KnowledgeStudio />
          </div>
        )}
        {activeTab === 'mcp' && (
          <div id="mcp-workspace" className="h-full">
            <MCPInspector />
          </div>
        )}
      </main>
    </div>
  );
}
