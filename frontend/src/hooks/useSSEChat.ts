import React, { useState, useCallback, useEffect, useRef } from 'react';
import { ChatMessage, Citation, ThoughtStep, ToolTrace, ChatSession } from '../types/chat';
import { apiFetch } from '../lib/api';

export function useSSEChat(applicationId: number = 1) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Fetch all chat sessions for this application
  const fetchSessions = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/chat/sessions?application_id=${applicationId}`);
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
      }
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  }, [applicationId]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // Select an old conversation from history
  const selectSession = useCallback(async (id: string) => {
    if (isStreaming) return;
    setSessionId(id);
    setIsLoadingHistory(true);
    try {
      const res = await apiFetch(`/api/chat/sessions/${id}/messages`);
      if (res.ok) {
        const msgs = await res.json();
        setMessages(msgs);
      }
    } catch (err) {
      console.error('Failed to load messages for session:', err);
    } finally {
      setIsLoadingHistory(false);
    }
  }, [isStreaming]);

  // Start a fresh, clean chat session
  const startNewChat = useCallback(() => {
    if (isStreaming) return;
    setSessionId(null);
    setMessages([]);
  }, [isStreaming]);

  // Delete an old chat session
  const deleteSession = useCallback(async (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    try {
      await apiFetch(`/api/chat/sessions/${id}`, { method: 'DELETE' });
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (sessionId === id) {
        setSessionId(null);
        setMessages([]);
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
  }, [sessionId]);

  // Rename a chat session title
  const renameSession = useCallback(async (id: string, newTitle: string) => {
    if (!newTitle.trim()) return;
    try {
      const res = await apiFetch(`/api/chat/sessions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle.trim() }),
      });
      if (res.ok) {
        setSessions((prev) =>
          prev.map((s) => (s.id === id ? { ...s, title: newTitle.trim() } : s))
        );
      }
    } catch (err) {
      console.error('Failed to rename session:', err);
    }
  }, []);

  // Stop / cancel streaming midway
  const stopStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isStreaming) return;

    const userMessageId = `user_${Date.now()}`;
    const assistantMessageId = `asst_${Date.now()}`;

    const userMsg: ChatMessage = {
      id: userMessageId,
      role: 'user',
      content: text,
      thoughts: [],
      tool_traces: [],
      citations: [],
      created_at: new Date().toISOString(),
    };

    const assistantMsg: ChatMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      thoughts: [],
      tool_traces: [],
      citations: [],
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await apiFetch('/api/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: sessionId,
          application_id: applicationId,
          message: text,
        }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const block of lines) {
          if (!block.trim()) continue;

          let eventType = 'message';
          let dataStr = '';

          const blockLines = block.split('\n');
          for (const line of blockLines) {
            if (line.startsWith('event:')) {
              eventType = line.replace('event:', '').trim();
            } else if (line.startsWith('data:')) {
              dataStr = line.replace('data:', '').trim();
            }
          }

          if (!dataStr) continue;

          try {
            const data = JSON.parse(dataStr);

            if (eventType === 'done' && data.session_id) {
              setSessionId(data.session_id);
              fetchSessions();
            }

            setMessages((prev) =>
              prev.map((msg) => {
                if (msg.id !== assistantMessageId) return msg;

                if (eventType === 'thought_step') {
                  const newThought: ThoughtStep = {
                    step: data.step,
                    thought: data.thought,
                  };
                  return {
                    ...msg,
                    thoughts: [...msg.thoughts, newThought],
                  };
                }

                if (eventType === 'tool_start') {
                  const newTool: ToolTrace = {
                    tool_name: data.tool_name,
                    call_id: data.call_id,
                    status: 'running',
                    arguments: data.arguments,
                  };
                  return {
                    ...msg,
                    tool_traces: [...msg.tool_traces, newTool],
                  };
                }

                if (eventType === 'tool_result') {
                  return {
                    ...msg,
                    tool_traces: msg.tool_traces.map((t) =>
                      t.call_id === data.call_id
                        ? {
                            ...t,
                            status: data.status,
                            duration_ms: data.latency_ms,
                            summary: data.output ? String(data.output).slice(0, 100) + '...' : '',
                          }
                        : t
                    ),
                  };
                }

                if (eventType === 'citation') {
                  const citation: Citation = {
                    document_name: data.document_name,
                    section_title: data.section_title,
                    snippet: data.snippet,
                    confidence_score: data.confidence_score,
                    chunk_id: data.chunk_id,
                  };
                  return {
                    ...msg,
                    citations: [...msg.citations, citation],
                  };
                }

                if (eventType === 'token') {
                  return {
                    ...msg,
                    content: msg.content + data.text,
                  };
                }

                if (eventType === 'done' && data.message_id && msg.content) {
                  // Switch to the server-side id so feedback and history refer to the stored message
                  return { ...msg, id: data.message_id };
                }

                if (eventType === 'error') {
                  return {
                    ...msg,
                    content: msg.content + `\n\n⚠️ *${data.message}*`,
                  };
                }

                return msg;
              })
            );
          } catch (err) {
            console.error('Failed to parse SSE payload:', err, dataStr);
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.log('Stream aborted by user');
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? { ...msg, content: msg.content + '\n\n*(Generation stopped by user)*' }
              : msg
          )
        );
      } else {
        console.error('SSE Stream Connection Error:', err);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? { ...msg, content: msg.content + '\n\n⚠️ *Connection dropped or stream failed.*' }
              : msg
          )
        );
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }, [applicationId, isStreaming, sessionId, fetchSessions]);

  return {
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
    fetchSessions,
  };
}
