import React, { useState, useEffect } from 'react';
import { FileUploader } from './FileUploader';
import { FileTable } from './FileTable';
import { AnswerOverrideStudio } from './AnswerOverrideStudio';
import { FileRecord } from '../../types/admin';
import { apiFetch } from '../../lib/api';

export const KnowledgeStudio: React.FC = () => {
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const fetchFiles = async () => {
    setIsLoading(true);
    try {
      const resp = await apiFetch('/api/list_files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page: 1, page_size: 50 }),
      });
      const data = await resp.json();
      if (data.files) {
        setFiles(data.files);
      }
    } catch (err) {
      console.error('Failed to load files:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []);

  return (
    <div className="h-full overflow-y-auto bg-slate-50 p-6 md:p-10 lg:px-20 space-y-8">
      <div>
        <h2 className="text-xl font-bold text-slate-800">Knowledge Admin Studio</h2>
        <p className="text-xs text-slate-500">
          Upload and curate verified corporate documents for the autonomous agent.
        </p>
      </div>

      <FileUploader onUploadSuccess={fetchFiles} />
      <FileTable files={files} isLoading={isLoading} onRefresh={fetchFiles} />
      <AnswerOverrideStudio />
    </div>
  );
};
