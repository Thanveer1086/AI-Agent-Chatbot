/**
 * Types matching backend Pydantic models for Knowledge Management, Admin Overrides, and MCP.
 */

export interface FileRecord {
  id: number;
  filename: string;
  file_size: number;
  mime_type: string;
  application_ids: number[];
  is_enabled: boolean;
  indexed_chunks: number;
  created_at: string;
}

export interface MCPTool {
  server_name: string;
  tool_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  transport: 'stdio' | 'sse';
  is_active: boolean;
}

export interface MCPServerInfo {
  name: string;
  transport: string;
  status: 'online' | 'offline' | 'degraded';
  tool_count: number;
}

export interface AnswerOverride {
  id: number;
  question_text: string;
  approved_answer: string;
  application_id: number;
  status: string;
  author: string;
  created_at: string;
}
