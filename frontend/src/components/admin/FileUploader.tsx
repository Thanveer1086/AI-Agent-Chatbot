import React, { useState, useRef } from 'react';
import { Upload, FileText, CheckCircle2, AlertCircle, Loader2, Files } from 'lucide-react';
import { apiFetch } from '../../lib/api';

interface FileUploaderProps {
  onUploadSuccess: () => void;
}

interface UploadProgress {
  current: number;
  total: number;
  currentFilename: string;
}

export const FileUploader: React.FC<FileUploaderProps> = ({ onUploadSuccess }) => {
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    if (fileArray.length === 0) return;

    setIsUploading(true);
    setStatusMessage(null);

    let successCount = 0;
    let totalChunks = 0;
    const errors: string[] = [];

    for (let i = 0; i < fileArray.length; i++) {
      const file = fileArray[i];
      setProgress({
        current: i + 1,
        total: fileArray.length,
        currentFilename: file.name,
      });

      const formData = new FormData();
      formData.append('file', file);
      formData.append('application_ids', JSON.stringify([1]));
      formData.append('document_type_id', '1');

      try {
        const response = await apiFetch('/api/upload_file', {
          method: 'POST',
          body: formData,
        });
        const data = await response.json();

        if (data.success) {
          successCount++;
          totalChunks += data.data.indexed_chunks || 0;
        } else {
          errors.push(`${file.name}: ${data.message || data.detail || `Upload failed (HTTP ${response.status})`}`);
        }
      } catch (err: any) {
        errors.push(`${file.name}: ${err.message || 'Network error'}`);
      }
    }

    setIsUploading(false);
    setProgress(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }

    if (successCount > 0) {
      onUploadSuccess();
      if (errors.length === 0) {
        setStatusMessage({
          type: 'success',
          text: `Successfully indexed ${successCount} file(s) into ${totalChunks} vector chunks!`,
        });
      } else {
        setStatusMessage({
          type: 'error',
          text: `Indexed ${successCount} file(s), but ${errors.length} failed: ${errors.join(', ')}`,
        });
      }
    } else {
      setStatusMessage({
        type: 'error',
        text: errors.join('; ') || 'Batch upload failed.',
      });
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-bold text-slate-800 text-base">Upload Knowledge Documents</h3>
          <p className="mt-1 text-xs text-slate-500">
            Batch upload supported. PDF, Word (.docx), CSV, Excel (.xlsx), Markdown (.md), and TXT files.
          </p>
        </div>
        <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
          <Files className="h-3.5 w-3.5" /> Multi-file ready
        </span>
      </div>

      {/* Drag & Drop Zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
        className={`mt-4 flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-all ${
          isDragging
            ? 'border-blue-500 bg-blue-50/50'
            : isUploading
            ? 'border-blue-300 bg-blue-50/20 cursor-not-allowed'
            : 'border-slate-200 hover:border-blue-400 hover:bg-slate-50/50'
        }`}
      >
        <input
          type="file"
          ref={fileInputRef}
          multiple
          disabled={isUploading}
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
          className="hidden"
          accept=".pdf,.docx,.csv,.tsv,.xlsx,.txt,.md,.json"
        />

        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-100 text-blue-600 mb-3 shadow-2xs">
          {isUploading ? <Loader2 className="h-6 w-6 animate-spin" /> : <Upload className="h-6 w-6" />}
        </div>

        {isUploading && progress ? (
          <div className="w-full max-w-sm space-y-2">
            <p className="font-semibold text-slate-800 text-sm">
              Processing {progress.current} of {progress.total}: {progress.currentFilename}
            </p>
            <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                style={{ width: `${(progress.current / progress.total) * 100}%` }}
              />
            </div>
            <p className="text-[11px] text-slate-400">Extracting structure, chunking & vectorizing...</p>
          </div>
        ) : (
          <>
            <p className="font-semibold text-slate-700 text-sm">
              Click or drag files here to upload (single or multiple)
            </p>
            <p className="mt-1 text-xs text-slate-400">Automatic structure parsing with Docling & parallel embeddings</p>
          </>
        )}
      </div>

      {/* Status Alert */}
      {statusMessage && (
        <div
          className={`mt-4 flex items-center gap-2 rounded-xl p-3 text-xs font-medium ${
            statusMessage.type === 'success'
              ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
              : 'bg-red-50 text-red-800 border border-red-200'
          }`}
        >
          {statusMessage.type === 'success' ? (
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
          ) : (
            <AlertCircle className="h-4 w-4 shrink-0 text-red-600" />
          )}
          <span>{statusMessage.text}</span>
        </div>
      )}
    </div>
  );
};
