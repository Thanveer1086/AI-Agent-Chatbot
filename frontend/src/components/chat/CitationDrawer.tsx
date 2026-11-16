import React from 'react';
import { X, FileText, CheckCircle, ExternalLink } from 'lucide-react';
import { Citation } from '../../types/chat';

interface CitationDrawerProps {
  citation: Citation | null;
  onClose: () => void;
}

export const CitationDrawer: React.FC<CitationDrawerProps> = ({ citation, onClose }) => {
  if (!citation) return null;

  const matchPercent = Math.round(citation.confidence_score * 100);

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-96 flex-col border-l border-slate-200 bg-white shadow-2xl transition-all">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
        <div className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-blue-600" />
          <h3 className="font-semibold text-slate-800 text-sm">Source Citation Details</h3>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {/* Document Info */}
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Source Document
          </span>
          <p className="mt-1 font-semibold text-slate-900 text-sm break-all">
            {citation.document_name}
          </p>
          {citation.section_title && (
            <p className="mt-1 text-xs text-slate-600 font-medium">
              Section: {citation.section_title}
            </p>
          )}

          {/* Confidence Badge */}
          <div className="mt-3 flex items-center gap-2">
            <span className="flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 border border-emerald-200">
              <CheckCircle className="h-3.5 w-3.5 text-emerald-600" />
              {matchPercent}% Relevance Match
            </span>
          </div>
        </div>

        {/* Snippet Content */}
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Retrieved Evidence Passage
          </span>
          <div className="mt-2 rounded-xl border border-slate-200 bg-white p-4 text-xs leading-relaxed text-slate-700 shadow-2xs font-serif italic">
            "{citation.snippet}"
          </div>
        </div>

        {/* Chunk Details */}
        <div className="pt-2 text-[11px] text-slate-400 font-mono">
          Chunk ID: {citation.chunk_id}
        </div>
      </div>
    </div>
  );
};
