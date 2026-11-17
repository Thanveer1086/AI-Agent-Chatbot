-- =============================================================================
-- AI-Agent-ChatBot Database Schema
-- Extensions: uuid-ossp, vector (pgvector), pg_trgm (BM25 lexical search)
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- 1. Master Data
CREATE TABLE IF NOT EXISTS applications (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    application_id INT REFERENCES applications(id) ON DELETE CASCADE,
    UNIQUE(name, application_id)
);

CREATE TABLE IF NOT EXISTS document_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

-- Seed default master data if empty
INSERT INTO applications (id, name, description) VALUES 
    (1, 'General Knowledge', 'Company-wide standard knowledge base and general policies'),
    (2, 'Customer Support', 'Support tickets, customer issue resolution guides, and FAQs')
ON CONFLICT (id) DO NOTHING;

INSERT INTO document_types (id, name) VALUES 
    (1, 'Policy Document'),
    (2, 'User Manual'),
    (3, 'FAQ'),
    (4, 'Technical Specification')
ON CONFLICT (id) DO NOTHING;

-- Seeds use explicit ids, so move the SERIAL counters past them; otherwise the next
-- normal INSERT would try id 1 again and fail with a duplicate key error.
SELECT setval(pg_get_serial_sequence('applications', 'id'), GREATEST((SELECT MAX(id) FROM applications), 1));
SELECT setval(pg_get_serial_sequence('document_types', 'id'), GREATEST((SELECT MAX(id) FROM document_types), 1));

-- 2. File & Ingestion Metadata
CREATE TABLE IF NOT EXISTS uploaded_files (
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
CREATE INDEX IF NOT EXISTS idx_uploaded_files_apps ON uploaded_files USING GIN(application_ids);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_enabled ON uploaded_files(is_enabled);

-- 3. Primary Vector Collection (Dense Embeddings + BM25 Full-Text)
CREATE TABLE IF NOT EXISTS primary_vector_chunks (
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

CREATE INDEX IF NOT EXISTS idx_vector_chunks_hnsw ON primary_vector_chunks 
    USING hnsw (dense_vector vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_vector_chunks_sparse ON primary_vector_chunks USING GIN(sparse_tokens);
CREATE INDEX IF NOT EXISTS idx_vector_chunks_app_names ON primary_vector_chunks USING GIN(application_names);
CREATE INDEX IF NOT EXISTS idx_vector_chunks_enabled ON primary_vector_chunks(is_enabled);

-- 4. Expansion Vector Collection (Approved / Override Answers)
CREATE TABLE IF NOT EXISTS approved_answers (
    id SERIAL PRIMARY KEY,
    question_text TEXT NOT NULL,
    approved_answer TEXT NOT NULL,
    dense_vector vector(1536) NOT NULL,
    application_id INT REFERENCES applications(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'answer_embedded',
    author VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_approved_answers_hnsw ON approved_answers 
    USING hnsw (dense_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_approved_answers_app ON approved_answers(application_id);

-- 5. Chat History & Feedback
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    application_id INT REFERENCES applications(id),
    title VARCHAR(255) DEFAULT 'New Conversation',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    thought_traces JSONB DEFAULT '[]',
    tool_calls JSONB DEFAULT '[]',
    citations JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_time ON chat_messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS feedback_records (
    id SERIAL PRIMARY KEY,
    message_id UUID REFERENCES chat_messages(id) ON DELETE CASCADE,
    rating VARCHAR(50) NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Human-in-the-loop approvals for tools that change things (write / destructive tools)
CREATE TABLE IF NOT EXISTS tool_approvals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,
    tool_name VARCHAR(255) NOT NULL,
    arguments JSONB NOT NULL DEFAULT '{}',
    reason TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending | executing | executed | failed | rejected | expired
    result TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    decided_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_tool_approvals_user_status ON tool_approvals(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tool_approvals_session ON tool_approvals(session_id);
