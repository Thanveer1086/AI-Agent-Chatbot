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
  ArrowDown,
  Mic,
  MicOff,
  Download
} from 'lucide-react';
import { useSSEChat } from '../../hooks/useSSEChat';
import { ThoughtAccordion } from './ThoughtAccordion';
import { CitationDrawer } from './CitationDrawer';
import { ChatSidebar } from './ChatSidebar';
import { CodeBlock } from './CodeBlock';
import { ApprovalCard } from './ApprovalCard';
import { apiFetch, errorMessage } from '../../lib/api';

export const ChatContainer: React.FC = () => {
  const [input, setInput] = useState<string>('');
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [isNearBottom, setIsNearBottom] = useState<boolean>(true);
  const [isListening, setIsListening] = useState<boolean>(false);

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
    decideApproval,
  } = useSSEChat(1);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef<boolean>(true);
  const recognitionRef = useRef<any>(null);

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

  // Voice Input Speech-to-Text Handler
  const toggleListening = () => {
    if (isListening) {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      setIsListening(false);
      return;
    }

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert('Speech recognition is not supported in this browser. Please use Chrome, Edge, or Safari.');
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setIsListening(true);
      };

      recognition.onresult = (event: any) => {
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }
        if (transcript) {
          setInput((prev) => (prev ? `${prev} ${transcript}` : transcript));
        }
      };

      recognition.onerror = (event: any) => {
        console.error('Speech recognition error:', event.error);
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err) {
      console.error('Speech recognition exception:', err);
      setIsListening(false);
    }
  };

  // Export Chat Conversation as Markdown (.md)
  const exportChatToMarkdown = () => {
    if (messages.length === 0) return;
    const currentSession = sessions.find((s) => s.id === sessionId);
    const title = currentSession?.title || 'Chat Conversation';
    const timestamp = new Date().toLocaleString();

    let md = `# ${title}\n\n`;
    md += `*Exported on: ${timestamp}*\n\n---\n\n`;

    messages.forEach((msg) => {
      const roleName = msg.role === 'user' ? '👤 User' : '🤖 Assistant';
      md += `### ${roleName}\n\n`;

      if (msg.role === 'assistant' && msg.thoughts && msg.thoughts.length > 0) {
        md += `<details>\n<summary>Thinking Process (${msg.thoughts.length} steps)</summary>\n\n`;
        msg.thoughts.forEach((t) => {
          md += `- **Step ${t.step}**: ${t.thought}\n`;
        });
        md += `\n</details>\n\n`;
      }

      md += `${msg.content}\n\n`;

      if (msg.citations && msg.citations.length > 0) {
        md += `**Sources:**\n`;
        msg.citations.forEach((cit) => {
          md += `- **${cit.document_name}** (${Math.round(cit.confidence_score * 100)}% match)\n`;
        });
        md += `\n`;
      }

      md += `---\n\n`;
    });

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const safeFilename = title.toLowerCase().replace(/[^a-z0-9]/g, '_').substring(0, 32);
    link.download = `${safeFilename || 'chat_export'}_${Date.now()}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const submitFeedback = async (messageId: string, rating: 'satisfactory' | 'unsatisfactory') => {
    try {
      const res = await apiFetch('/api/submit/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_id: messageId, rating }),
      });
      if (!res.ok) {
        alert(`Feedback was not saved: ${await errorMessage(res)}`);
        return;
      }
      alert(`Thank you! Marked as ${rating}.`);
    } catch (err) {
      console.error('Feedback error:', err);
      alert('Feedback was not saved: network error.');
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
    }
    if (input.trim() && !isStreaming) {
      sendMessage(input.trim());
      setInput('');
      isAtBottomRef.current = true;
      setTimeout(scrollToBottom, 50);
    }
  };

  const currentSession = sessions.find((s) => s.id === sessionId);

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
        {/* Top Chat Bar: Session Title & Export Action */}
        {messages.length > 0 && (
          <div className="flex items-center justify-between border-b border-slate-200/80 bg-white/70 px-6 py-2.5 backdrop-blur-xs text-xs">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-700 truncate max-w-md">
                {currentSession?.title || 'Current Conversation'}
              </span>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500">
                {messages.length} messages
              </span>
            </div>

            <button
              onClick={exportChatToMarkdown}
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-blue-600 transition-colors shadow-2xs"
              title="Download conversation as Markdown report"
            >
              <Download className="h-3.5 w-3.5 text-blue-600" />
              <span>Export Chat (.md)</span>
            </button>
          </div>
        )}

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

                    {/* Message Content with CodeBlock syntax highlighting */}
                    <div className="prose prose-sm max-w-none prose-slate">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          code: (props) => <CodeBlock {...props} />,
                        }}
                      >
                        {msg.content || (isStreaming ? '...' : '')}
                      </ReactMarkdown>
                    </div>

                    {/* Human-in-the-loop approvals for write/destructive tools */}
                    {msg.role === 'assistant' &&
                      msg.approvals?.map((approval) => (
                        <ApprovalCard key={approval.approval_id} approval={approval} onDecide={decideApproval} />
                      ))}

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
              placeholder={isListening ? "Listening... Speak now..." : "Ask a question or request an action..."}
              disabled={isStreaming}
              className={`flex-1 rounded-xl border px-4 py-3 text-sm text-slate-900 shadow-2xs focus:outline-hidden disabled:opacity-50 transition-all ${
                isListening
                  ? 'border-rose-400 bg-rose-50/50 ring-2 ring-rose-300'
                  : 'border-slate-300 bg-slate-50 focus:border-blue-500 focus:bg-white'
              }`}
            />

            {/* Voice Input Microphone Button */}
            <button
              type="button"
              onClick={toggleListening}
              disabled={isStreaming}
              className={`flex h-11 w-11 items-center justify-center rounded-xl transition-all shadow-xs ${
                isListening
                  ? 'bg-rose-500 text-white animate-pulse shadow-md hover:bg-rose-600'
                  : 'border border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 hover:text-slate-800'
              }`}
              title={isListening ? 'Stop listening' : 'Voice input (Speech to text)'}
            >
              {isListening ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
            </button>

            {/* Send or Stop Generation Button */}
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
