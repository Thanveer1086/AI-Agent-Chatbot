import React, { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Send,
  Bot,
  User,
  Bookmark,
  Loader2,
  Sparkles,
  ThumbsUp,
  ThumbsDown,
  Copy,
  Check,
  Square,
  ArrowDown
} from 'lucide-react';
import { useSSEChat } from '../../hooks/useSSEChat';
import { ThoughtAccordion } from './ThoughtAccordion';
import { CitationDrawer } from './CitationDrawer';
import { ChatSidebar } from './ChatSidebar';

export const ChatContainer: React.FC = () => {
  const [input, setInput] = useState<string>('');
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [isNearBottom, setIsNearBottom] = useState<boolean>(true);

  const {
    messages,
    isStreaming,
    activeCitation,
    setActiveCitation,
    sessionId,
    sessions,
    isLoadingHistory,
    sendMessage,
    selectSession,
    startNewChat,
    deleteSession,
    renameSession,
    stopStreaming,
  } = useSSEChat(1);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef<boolean>(true);

  // Monitor scroll position to enable/disable auto-scroll
  const handleScroll = useCallback(() => {
    if (!scrollContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    const distanceToBottom = scrollHeight - scrollTop - clientHeight;
    const nearBottom = distanceToBottom < 140;
    setIsNearBottom(nearBottom);
    isAtBottomRef.current = nearBottom;
  }, []);

  // Smart Auto-Scroll: only scroll to bottom if user is already near bottom
  useEffect(() => {
    if (isAtBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    setIsNearBottom(true);
    isAtBottomRef.current = true;
  };

  const handleCopy = (messageId: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedMessageId(messageId);
    setTimeout(() => {
      setCopiedMessageId(null);
    }, 2000);
  };

  const submitFeedback = async (messageId: string, rating: 'satisfactory' | 'unsatisfactory') => {
    try {
      await fetch('/api/submit/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_id: messageId, rating }),
      });
      alert(`Thank you! Marked as ${rating}.`);
    } catch (err) {
      console.error('Feedback error:', err);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !isStreaming) {
      sendMessage(input.trim());
      setInput('');
      // Force scroll to bottom on new message submission
      isAtBottomRef.current = true;
      setTimeout(scrollToBottom, 50);
    }
  };

  return (
    <div className="relative flex h-full w-full overflow-hidden bg-slate-50">
      {/* ChatGPT-style Left History Sidebar */}
      <ChatSidebar
        sessions={sessions}
        activeSessionId={sessionId}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen((prev) => !prev)}
        onSelectSession={selectSession}
        onNewChat={startNewChat}
        onDeleteSession={deleteSession}
        onRenameSession={renameSession}
      />

      {/* Main Chat Flow */}
      <div className="relative flex flex-1 flex-col h-full overflow-hidden bg-slate-50">
        {/* Messages Scroll Area */}
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto px-4 py-6 md:px-12 lg:px-24 scroll-smooth"
        >
          {isLoadingHistory ? (
            <div className="flex h-full flex-col items-center justify-center text-slate-400 gap-3">
              <Loader2 className="h-7 w-7 animate-spin text-blue-600" />
              <p className="text-sm font-medium">Loading conversation...</p>
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-100 text-blue-600 shadow-md mb-4">
                <Sparkles className="h-8 w-8" />
              </div>
              <h2 className="text-xl font-bold text-slate-800">What would you like to know?</h2>
              <p className="mt-1 text-sm text-slate-500 max-w-md">
                Ask any question grounded in our knowledge base, company policies, or external tools.
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-2 max-w-lg">
                {[
                  'In my github how many repo are there please check?',
                  'List all my repository names',
                  'Please give the overall explanation about netspective sync meeting 02-11',
                  'Show me the database system metrics'
                ].map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      sendMessage(q);
                      isAtBottomRef.current = true;
                      setTimeout(scrollToBottom, 50);
                    }}
                    className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-medium text-slate-700 shadow-2xs hover:border-blue-400 hover:text-blue-600 transition-all text-left"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3.5 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {msg.role === 'assistant' && (
                    <div className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-xl bg-blue-600 text-white shadow-xs">
                      <Bot className="h-4 w-4" />
                    </div>
                  )}

                  <div
                    className={`max-w-3xl rounded-2xl px-5 py-4 text-sm shadow-xs ${
                      msg.role === 'user'
                        ? 'bg-blue-600 text-white'
                        : 'border border-slate-200 bg-white text-slate-800'
                    }`}
                  >
                    {/* Thought & Tool Accordion (Assistant only) */}
                    {msg.role === 'assistant' && (
                      <ThoughtAccordion thoughts={msg.thoughts} toolTraces={msg.tool_traces} />
                    )}

                    {/* Message Content */}
                    <div className="prose prose-sm max-w-none prose-slate">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content || (isStreaming ? '...' : '')}
                      </ReactMarkdown>
                    </div>

                    {/* Assistant Action Bar: Copy + Sources + Feedback */}
                    {msg.role === 'assistant' && (
                      <div className="mt-3.5 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2">
                        {/* Sources Badges */}
                        {msg.citations && msg.citations.length > 0 ? (
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="text-[11px] font-semibold text-slate-400 mr-1 flex items-center gap-1">
                              <Bookmark className="h-3 w-3" /> Sources:
                            </span>
                            {msg.citations.map((cit, idx) => (
                              <button
                                key={idx}
                                onClick={() => setActiveCitation(cit)}
                                className="flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-blue-50 hover:text-blue-700 hover:border-blue-200 transition-colors"
                              >
                                <span>{cit.document_name}</span>
                                <span className="text-[10px] text-emerald-600 font-bold">
                                  {Math.round(cit.confidence_score * 100)}%
                                </span>
                              </button>
                            ))}
                          </div>
                        ) : (
                          <div />
                        )}

                        {/* Action buttons (Copy + Feedback) */}
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleCopy(msg.id, msg.content)}
                            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                            title="Copy response to clipboard"
                          >
                            {copiedMessageId === msg.id ? (
                              <>
                                <Check className="h-3.5 w-3.5 text-emerald-600" />
                                <span className="text-[11px] font-medium text-emerald-600">Copied</span>
                              </>
                            ) : (
                              <>
                                <Copy className="h-3.5 w-3.5" />
                                <span className="text-[11px]">Copy</span>
                              </>
                            )}
                          </button>

                          <button
                            onClick={() => submitFeedback(msg.id, 'satisfactory')}
                            className="rounded-md p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-slate-100 transition-colors"
                            title="Helpful answer"
                          >
                            <ThumbsUp className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => submitFeedback(msg.id, 'unsatisfactory')}
                            className="rounded-md p-1.5 text-slate-400 hover:text-red-600 hover:bg-slate-100 transition-colors"
                            title="Unsatisfactory answer"
                          >
                            <ThumbsDown className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  {msg.role === 'user' && (
                    <div className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-xl bg-slate-800 text-white shadow-xs">
                      <User className="h-4 w-4" />
                    </div>
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Scroll to Bottom Floating Pill if user scrolled up */}
        {!isNearBottom && messages.length > 0 && (
          <button
            onClick={scrollToBottom}
            className="absolute bottom-20 left-1/2 -translate-x-1/2 flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-md border border-slate-200 hover:bg-slate-50 transition-all z-10"
          >
            <ArrowDown className="h-3.5 w-3.5 text-blue-600" />
            Scroll to bottom
          </button>
        )}

        {/* Input Bar */}
        <div className="border-t border-slate-200 bg-white p-4 shadow-lg">
          <form onSubmit={handleSubmit} className="mx-auto flex max-w-4xl items-center gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask a question or request an action..."
              disabled={isStreaming}
              className="flex-1 rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900 shadow-2xs focus:border-blue-500 focus:bg-white focus:outline-hidden disabled:opacity-50"
            />
            {isStreaming ? (
              <button
                type="button"
                onClick={stopStreaming}
                className="flex h-11 items-center gap-1.5 px-4 rounded-xl bg-red-600 text-white shadow-md hover:bg-red-700 transition-colors"
                title="Stop generation"
              >
                <Square className="h-4 w-4 fill-white" />
                <span className="text-xs font-bold">Stop</span>
              </button>
            ) : (
              <button
                type="submit"
                disabled={!input.trim()}
                className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600 text-white shadow-md hover:bg-blue-700 transition-colors disabled:opacity-40"
                title="Send message"
              >
                <Send className="h-5 w-5" />
              </button>
            )}
          </form>
        </div>

        {/* Citation Details Drawer */}
        <CitationDrawer citation={activeCitation} onClose={() => setActiveCitation(null)} />
      </div>
    </div>
  );
};
