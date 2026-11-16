# Interface Contract: Chat Streaming Server-Sent Events (SSE)

**Endpoint**: `POST /api/chat/stream`  
**Content-Type**: `text/event-stream`  
**Cache-Control**: `no-cache`  
**Connection**: `keep-alive`  

---

## 1. Request Payload (JSON)

```json
{
  "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "application_id": 1,
  "message": "What is our company reimbursement policy for flight delays and is there any related support ticket?",
  "enable_web_search": false
}
```

---

## 2. Server-Sent Events Protocol

The server responds with an HTTP 200 stream formatted according to standard W3C Server-Sent Events:
`event: <EVENT_TYPE>\ndata: <JSON_PAYLOAD>\n\n`

### Event Types & Payloads

#### 1. `thought_step` (Agent Reasoning Phase)
Emitted when the agent formulates a plan or enters an intermediate reflection cycle.
```text
event: thought_step
data: {"step": 1, "thought": "The user is asking about travel reimbursement policy and open support tickets. I need to query the internal knowledge base for the flight delay policy and query the internal database for related tickets."}
```

#### 2. `tool_start` (Tool Invocations Dispatched)
Emitted immediately before tool execution begins. Multiple tools may start simultaneously.
```text
event: tool_start
data: {"tool_name": "knowledge_base_search", "call_id": "call_01", "arguments": {"query": "travel reimbursement policy flight delay", "application_id": 1}}
```

#### 3. `tool_result` (Tool Invocations Completed)
Emitted when a tool finishes execution.
```text
event: tool_result
data: {"tool_name": "knowledge_base_search", "call_id": "call_01", "duration_ms": 240, "status": "success", "summary": "Retrieved 3 matching policy chunks with high confidence."}
```

#### 4. `token` (Incremental Answer Tokens)
Emitted as the LLM synthesizes the final grounded answer.
```text
event: token
data: {"text": "According to the Travel Policy Section 4.2, "}
```

#### 5. `citation` (Grounded References)
Emitted at the conclusion of answer generation, detailing verified source snippets.
```text
event: citation
data: {"document_name": "Employee_Travel_Handbook_2026.pdf", "section_title": "4.2 Flight Disruptions & Reimbursements", "confidence_score": 0.94, "snippet": "Employees experiencing flight delays exceeding 3 hours are eligible for up to $150 in meal vouchers...", "chunk_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"}
```

#### 6. `done` (Stream Termination)
Emitted once all processing is complete and records are persisted.
```text
event: done
data: {"message_id": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6", "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "total_duration_ms": 1850}
```

#### 7. `error` (Recoverable or Terminal Errors)
```text
event: error
data: {"code": "TOOL_TIMEOUT", "message": "The internal database tool timed out after 15s. Generating partial response with available knowledge."}
```
