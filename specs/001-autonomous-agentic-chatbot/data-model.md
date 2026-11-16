# Phase 1 Data Model: Relational Schemas, Agent State & Type Definitions

**Feature**: `001-autonomous-agentic-chatbot`  
**Date**: 2026-11-12  
**Status**: Completed  

---

## 1. Relational Database Schema (PostgreSQL 15+)

```sql
-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- 1. Master Data Tables
CREATE TABLE applications (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    application_id INT REFERENCES applications(id) ON DELETE CASCADE,
    UNIQUE(name, application_id)
);

CREATE TABLE document_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

-- 2. File & Ingestion Metadata
CREATE TABLE uploaded_files (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(500) UNIQUE NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(255) NOT NULL,
    storage_url TEXT NOT NULL,
    application_ids INT[] NOT NULL,
    category_ids INT[] DEFAULT '{}',
    document_type_id INT REFERENCES document_types(id),
    indexed_chunks INT DEFAULT 0,
    is_enabled BOOLEAN DEFAULT TRUE,
    uploaded_by VARCHAR(255) DEFAULT 'system',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_uploaded_files_apps ON uploaded_files USING GIN(application_ids);
CREATE INDEX idx_uploaded_files_enabled ON uploaded_files(is_enabled);

-- 3. Primary Vector Collection (Knowledge Chunks)
CREATE TABLE primary_vector_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_id INT REFERENCES uploaded_files(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    chunk_index INT NOT NULL,
    chunk_text TEXT NOT NULL,
    section_title TEXT,
    dense_vector vector(1536) NOT NULL,
    sparse_tokens TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', chunk_text)) STORED,
    application_names TEXT[] NOT NULL,
    category_ids INT[] DEFAULT '{}',
    document_type_id INT,
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- HNSW Cosine Index for dense vector similarity
CREATE INDEX idx_vector_chunks_hnsw ON primary_vector_chunks 
    USING hnsw (dense_vector vector_cosine_ops) WITH (m = 16, ef_construction = 64);
-- GIN Indexes for BM25 full-text and application filtering
CREATE INDEX idx_vector_chunks_sparse ON primary_vector_chunks USING GIN(sparse_tokens);
CREATE INDEX idx_vector_chunks_app_names ON primary_vector_chunks USING GIN(application_names);
CREATE INDEX idx_vector_chunks_enabled ON primary_vector_chunks(is_enabled);

-- 4. Expansion Vector Collection (Approved / Override Answers)
CREATE TABLE approved_answers (
    id SERIAL PRIMARY KEY,
    question_text TEXT NOT NULL,
    approved_answer TEXT NOT NULL,
    dense_vector vector(1536) NOT NULL,
    application_id INT REFERENCES applications(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'answer_embedded', -- 'answer_drafted', 'answer_embedded'
    author VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_approved_answers_hnsw ON approved_answers 
    USING hnsw (dense_vector vector_cosine_ops);
CREATE INDEX idx_approved_answers_app ON approved_answers(application_id);

-- 5. Chat History & Feedback
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    application_id INT REFERENCES applications(id),
    title VARCHAR(255) DEFAULT 'New Conversation',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_chat_sessions_user ON chat_sessions(user_id);

CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL, -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,
    thought_traces JSONB DEFAULT '[]',
    tool_calls JSONB DEFAULT '[]',
    citations JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_chat_messages_session ON chat_messages(session_id);

CREATE TABLE feedback_records (
    id SERIAL PRIMARY KEY,
    message_id UUID REFERENCES chat_messages(id) ON DELETE CASCADE,
    rating VARCHAR(50) NOT NULL, -- 'satisfactory', 'unsatisfactory', 'noresponse'
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 2. LangGraph Agent State Schema

The agent operates over an immutable typed state dictionary:

```python
from typing import Annotated, Sequence, TypedDict, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage
import operator

class ToolCallRecord(TypedDict):
    tool_name: str
    arguments: Dict[str, Any]
    output: Any
    latency_ms: float
    status: str # "success" | "error" | "timeout"

class CitationRecord(TypedDict):
    document_name: str
    section_title: Optional[str]
    snippet: str
    confidence_score: float
    chunk_id: str

class AgentState(TypedDict):
    session_id: str
    application_id: int
    application_name: str
    messages: Annotated[Sequence[BaseMessage], operator.add]
    plan: Optional[str]
    iteration_count: int
    active_tools: List[str]
    tool_execution_history: Annotated[List[ToolCallRecord], operator.add]
    citations: Annotated[List[CitationRecord], operator.add]
    intermediate_thoughts: Annotated[List[str], operator.add]
    final_answer: Optional[str]
    status: str # "planning" | "executing_tools" | "synthesizing" | "completed" | "error"
```

---

## 3. Pydantic v2 Models (Backend DTOs)

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

# --- Chat & Streaming ---
class ChatStreamRequest(BaseModel):
    session_id: Optional[UUID] = None
    application_id: int
    message: str = Field(..., min_length=1, max_length=5000)
    enable_web_search: bool = False

class Citation(BaseModel):
    document_name: str
    section_title: Optional[str] = None
    snippet: str
    confidence_score: float
    chunk_id: str

class ThoughtStep(BaseModel):
    step_number: int
    thought: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ToolTrace(BaseModel):
    tool_name: str
    input_args: Dict[str, Any]
    output_summary: str
    duration_ms: float
    success: bool

# --- Ingestion & Files ---
class UploadFileResponse(BaseModel):
    success: bool
    message: str
    file_id: int
    filename: str
    indexed_chunks: int

class FileRecord(BaseModel):
    id: int
    filename: str
    file_size: int
    mime_type: str
    application_ids: List[int]
    is_enabled: bool
    indexed_chunks: int
    created_at: datetime

class ToggleFileStatusRequest(BaseModel):
    file_id: int
    is_enabled: bool

# --- MCP Tool Definition ---
class MCPToolDefinition(BaseModel):
    server_name: str
    tool_name: str
    description: str
    input_schema: Dict[str, Any]
    transport: str # "stdio" | "sse"
    is_active: bool = True
```

---

## 4. TypeScript Interfaces (Frontend Alignment)

```typescript
// types/chat.ts
export interface Citation {
  document_name: string;
  section_title?: string;
  snippet: string;
  confidence_score: number;
  chunk_id: string;
}

export interface ThoughtStep {
  step_number: number;
  thought: string;
  timestamp: string;
}

export interface ToolTrace {
  tool_name: string;
  input_args: Record<string, unknown>;
  output_summary: string;
  duration_ms: number;
  success: boolean;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  thoughts?: ThoughtStep[];
  tool_traces?: ToolTrace[];
  citations?: Citation[];
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string;
  application_id: number;
  created_at: string;
}

// types/admin.ts
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
```
