# Interface Contract: Knowledge Ingestion, Management & Admin Review

**Base URL**: `/api`  
**Authentication**: `Authorization: Bearer <JWT_TOKEN>` (Bypassed if `DEV_AUTH_BYPASS=true`)  

---

## 1. Document Upload & Ingestion

### `POST /api/upload_file`
Accepts multipart form-data. Converts file via Docling/FFmpeg, generates embeddings, stores binary in Azure Blob Storage, and indexes chunks in PostgreSQL.

**Request (Multipart Form-Data)**:
- `file`: `<Binary File>` (`.pdf`, `.docx`, `.csv`, `.xlsx`, `.txt`, `.md`, `.mp4`)
- `application_ids`: `[1, 2]` (JSON array of integer application IDs)
- `category_ids`: `[5]` (Optional JSON array of integer category IDs)
- `document_type_id`: `3` (Integer document type ID)

**Response (200 OK)**:
```json
{
  "success": true,
  "message": "File processed and indexed successfully.",
  "data": {
    "file_id": 42,
    "filename": "HR_Policy_2026.pdf",
    "indexed_chunks": 18,
    "storage_url": "https://storage.blob.core.windows.net/documents/HR_Policy_2026.pdf"
  }
}
```

---

## 2. File Listing & Status Management

### `POST /api/list_files`
Fetches paginated uploaded files with active filters.

**Request (JSON)**:
```json
{
  "application_id": 1,
  "page": 1,
  "page_size": 50,
  "search_query": "Policy"
}
```

**Response (200 OK)**:
```json
{
  "total": 1,
  "page": 1,
  "page_size": 50,
  "files": [
    {
      "id": 42,
      "filename": "HR_Policy_2026.pdf",
      "file_size": 1048576,
      "mime_type": "application/pdf",
      "application_ids": [1],
      "is_enabled": true,
      "indexed_chunks": 18,
      "created_at": "2026-11-12T10:00:00Z"
    }
  ]
}
```

### `POST /api/toggle_file_status`
Toggles whether a file's vector chunks are eligible for knowledge search without deleting the file.

**Request (JSON)**:
```json
{
  "file_id": 42,
  "is_enabled": false
}
```

**Response (200 OK)**:
```json
{
  "success": true,
  "file_id": 42,
  "is_enabled": false,
  "message": "File and 18 associated vector chunks have been disabled."
}
```

---

## 3. Answer Review & Verified Overrides

### `POST /api/override_answer`
Allows an administrator to publish an authoritative approved answer that is embedded in the expansion vector collection.

**Request (JSON)**:
```json
{
  "question_text": "How do I claim flight delay expenses?",
  "approved_answer": "Submit a travel expense form within 14 days attaching boarding passes and airline disruption confirmation.",
  "application_id": 1
}
```

**Response (200 OK)**:
```json
{
  "success": true,
  "override_id": 15,
  "message": "Approved answer successfully vectorized and published."
}
```

---

## 4. User Feedback Submission

### `POST /api/submit/feedback`
Records user satisfaction rating for an agent message.

**Request (JSON)**:
```json
{
  "message_id": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
  "rating": "satisfactory",
  "comment": "Accurate flight policy guidance!"
}
```

**Response (200 OK)**:
```json
{
  "success": true,
  "message": "Feedback recorded."
}
```
