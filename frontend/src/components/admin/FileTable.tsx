import React, { useState } from 'react';
import { FileText, Trash2, Power, RefreshCw, Eye, X, Search, Copy, Check, Loader2 } from 'lucide-react';
import { FileRecord } from '../../types/admin';

interface FileTableProps {
  files: FileRecord[];
  isLoading: boolean;
  onRefresh: () => void;
}

interface ChunkData {
  id: string;
  chunk_index: number;
  section_title: string;
  chunk_text: string;
  char_count: number;
}

interface ChunkInspectorState {
  isOpen: boolean;
  fileId: number | null;
  filename: string;
  isLoading: boolean;
  chunks: ChunkData[];
  searchQuery: string;
}

export const FileTable: React.FC<FileTableProps> = ({ files, isLoading, onRefresh }) => {
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [copiedChunkId, setCopiedChunkId] = useState<string | null>(null);
  const [inspector, setInspector] = useState<ChunkInspectorState>({
    isOpen: false,
    fileId: null,
    filename: '',
    isLoading: false,
    chunks: [],
    searchQuery: '',
  });

  const toggleStatus = async (file: FileRecord) => {
    setTogglingId(file.id);
    try {
      await fetch('/api/toggle_file_status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: file.id,
          is_enabled: !file.is_enabled,
        }),
      });
      onRefresh();
    } catch (err) {
      console.error('Failed to toggle status:', err);
    } finally {
      setTogglingId(null);
    }
  };

  const deleteFile = async (id: number) => {
    if (!confirm('Are you sure you want to delete this file and its indexed vectors?')) return;
    try {
      await fetch('/api/delete_files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_ids: [id] }),
      });
      onRefresh();
    } catch (err) {
      console.error('Failed to delete file:', err);
    }
  };

  const openInspector = async (file: FileRecord) => {
    setInspector({
      isOpen: true,
      fileId: file.id,
      filename: file.filename,
      isLoading: true,
      chunks: [],
      searchQuery: '',
    });

    try {
      const res = await fetch(`/api/files/${file.id}/chunks`);
      if (res.ok) {
        const data = await res.json();
        setInspector((prev) => ({
          ...prev,
          isLoading: false,
          chunks: data.chunks || [],
        }));
      } else {
        alert('Failed to load chunks for this file.');
        closeInspector();
      }
    } catch (err) {
      console.error('Failed to fetch chunks:', err);
      alert('Network error loading chunks.');
      closeInspector();
    }
  };

  const closeInspector = () => {
    setInspector({
      isOpen: false,
      fileId: null,
      filename: '',
      isLoading: false,
      chunks: [],
      searchQuery: '',
    });
  };

  const handleCopyChunk = (chunkId: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedChunkId(chunkId);
    setTimeout(() => setCopiedChunkId(null), 2000);
  };

  const filteredChunks = inspector.chunks.filter((c) =>
    c.chunk_text.toLowerCase().includes(inspector.searchQuery.toLowerCase()) ||
    c.section_title.toLowerCase().includes(inspector.searchQuery.toLowerCase())
  );

  return (
    <>
      <div className="rounded-2xl border border-slate-200 bg-white shadow-xs overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h3 className="font-bold text-slate-800 text-base">Indexed Knowledge Files</h3>
            <p className="text-xs text-slate-500">Manage search eligibility, inspection, and chunks</p>
          </div>
          <button
            onClick={onRefresh}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50/80 text-slate-400 font-semibold uppercase tracking-wider border-b border-slate-200">
              <tr>
                <th className="px-6 py-3">Document</th>
                <th className="px-4 py-3">Format</th>
                <th className="px-4 py-3">Chunks</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {files.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-400">
                    No knowledge files uploaded yet. Upload a document above to get started.
                  </td>
                </tr>
              ) : (
                files.map((file) => (
                  <tr key={file.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-6 py-3.5 font-medium text-slate-900 flex items-center gap-2">
                      <FileText className="h-4 w-4 text-blue-600 shrink-0" />
                      <span className="truncate max-w-xs">{file.filename}</span>
                    </td>
                    <td className="px-4 py-3.5 text-slate-500 font-mono uppercase">
                      {file.mime_type.replace('application/', '').replace('.', '')}
                    </td>
                    <td className="px-4 py-3.5 text-slate-700 font-semibold">
                      <button
                        onClick={() => openInspector(file)}
                        className="inline-flex items-center gap-1 rounded-md bg-blue-50 px-2 py-0.5 border border-blue-200 text-blue-700 hover:bg-blue-100 transition-colors"
                        title="Click to inspect chunks"
                      >
                        <Eye className="h-3 w-3" />
                        <span>{file.indexed_chunks} chunks</span>
                      </button>
                    </td>
                    <td className="px-4 py-3.5">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-bold ${
                          file.is_enabled
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-slate-100 text-slate-500 border border-slate-200'
                        }`}
                      >
                        <span className={`h-1.5 w-1.5 rounded-full ${file.is_enabled ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                        {file.is_enabled ? 'Active / Searchable' : 'Disabled'}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-right space-x-1.5">
                      <button
                        onClick={() => openInspector(file)}
                        className="rounded-md p-1.5 text-slate-400 hover:bg-blue-50 hover:text-blue-600 transition-colors"
                        title="Inspect Chunks"
                      >
                        <Eye className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => toggleStatus(file)}
                        disabled={togglingId === file.id}
                        className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
                        title={file.is_enabled ? 'Disable from retrieval' : 'Enable in retrieval'}
                      >
                        <Power className={`h-4 w-4 ${file.is_enabled ? 'text-emerald-600' : 'text-slate-400'}`} />
                      </button>
                      <button
                        onClick={() => deleteFile(file.id)}
                        className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors"
                        title="Delete document"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Chunk Inspector Modal */}
      {inspector.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
          <div className="relative flex flex-col w-full max-w-4xl max-h-[88vh] rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50/80">
              <div className="flex items-center gap-2.5">
                <FileText className="h-5 w-5 text-blue-600" />
                <div>
                  <h3 className="font-bold text-slate-900 text-base leading-tight">
                    Chunk Inspector: {inspector.filename}
                  </h3>
                  <p className="text-xs text-slate-500">
                    {inspector.chunks.length} total indexed vector chunks in PostgreSQL
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                {/* Search Bar within chunks */}
                <div className="relative">
                  <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
                  <input
                    type="text"
                    value={inspector.searchQuery}
                    onChange={(e) => setInspector((prev) => ({ ...prev, searchQuery: e.target.value }))}
                    placeholder="Search chunk text..."
                    className="w-56 rounded-lg border border-slate-300 bg-white pl-8 pr-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:border-blue-500 focus:outline-hidden"
                  />
                </div>

                <button
                  onClick={closeInspector}
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-slate-50">
              {inspector.isLoading ? (
                <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-3">
                  <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
                  <p className="text-sm font-medium">Fetching vector chunks...</p>
                </div>
              ) : filteredChunks.length === 0 ? (
                <div className="text-center py-16 text-slate-400">
                  <p className="text-sm">No chunks matched your search query.</p>
                </div>
              ) : (
                filteredChunks.map((chunk) => (
                  <div
                    key={chunk.id}
                    className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs space-y-2 hover:border-blue-300 transition-all"
                  >
                    <div className="flex items-center justify-between text-xs border-b border-slate-100 pb-2">
                      <div className="flex items-center gap-2">
                        <span className="rounded-md bg-blue-100 text-blue-800 font-bold px-2 py-0.5 text-[11px]">
                          Chunk #{chunk.chunk_index}
                        </span>
                        <span className="font-semibold text-slate-700">
                          Section: {chunk.section_title}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-slate-400 text-[11px]">
                          {chunk.char_count} chars
                        </span>
                        <button
                          onClick={() => handleCopyChunk(chunk.id, chunk.chunk_text)}
                          className="flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] text-slate-500 hover:bg-slate-100 hover:text-slate-800 transition-colors"
                          title="Copy chunk text"
                        >
                          {copiedChunkId === chunk.id ? (
                            <>
                              <Check className="h-3 w-3 text-emerald-600" />
                              <span className="text-emerald-600 font-medium">Copied</span>
                            </>
                          ) : (
                            <>
                              <Copy className="h-3 w-3" />
                              <span>Copy</span>
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                    <pre className="text-xs text-slate-700 whitespace-pre-wrap font-sans bg-slate-50/60 p-3 rounded-lg border border-slate-100 leading-relaxed max-h-48 overflow-y-auto">
                      {chunk.chunk_text}
                    </pre>
                  </div>
                ))
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between border-t border-slate-200 px-6 py-3 bg-white text-xs text-slate-500">
              <span>
                Showing {filteredChunks.length} of {inspector.chunks.length} chunks
              </span>
              <button
                onClick={closeInspector}
                className="rounded-lg bg-slate-100 px-4 py-2 font-semibold text-slate-700 hover:bg-slate-200 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
