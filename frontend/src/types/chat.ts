/**
 * Types matching backend Pydantic models for Chat and SSE Streaming.
 */

export interface Citation {
  document_name: string;
  section_title?: string;
  snippet: string;
  confidence_score: number;
  chunk_id: string;
}

export interface ThoughtStep {
  step: number;
  thought: string;
}

export interface ToolTrace {
  tool_name: string;
  call_id: string;
  duration_ms?: number;
  status: 'running' | 'success' | 'error' | 'timeout';
  summary?: string;
  arguments?: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  thoughts: ThoughtStep[];
  tool_traces: ToolTrace[];
  citations: Citation[];
  created_at: string;
  feedback?: 'satisfactory' | 'unsatisfactory';
}

export interface ChatSession {
  id: string;
  title: string;
  application_id: number;
  created_at: string;
}

export interface ApplicationInfo {
  id: number;
  name: string;
  description: string;
}
