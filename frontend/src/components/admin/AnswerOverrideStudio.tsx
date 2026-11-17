import React, { useState } from 'react';
import { ShieldCheck, PlusCircle, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { apiFetch } from '../../lib/api';

export const AnswerOverrideStudio: React.FC = () => {
  const [questionText, setQuestionText] = useState('');
  const [approvedAnswer, setApprovedAnswer] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const handlePublish = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!questionText.trim() || !approvedAnswer.trim()) return;

    setIsSubmitting(true);
    setFeedback(null);

    try {
      const resp = await apiFetch('/api/override_answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question_text: questionText.trim(),
          approved_answer: approvedAnswer.trim(),
          application_id: 1,
        }),
      });
      const data = await resp.json();

      if (data.success) {
        setFeedback({
          type: 'success',
          message: 'Authoritative answer published! Future semantically matching questions will return this verified answer.',
        });
        setQuestionText('');
        setApprovedAnswer('');
      } else {
        setFeedback({ type: 'error', message: data.message || 'Failed to publish answer.' });
      }
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Network error.' });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-emerald-600" />
        <h3 className="font-bold text-slate-800 text-base">Verified Answer Overrides</h3>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Publish human-curated official answers to resolve frequent questions or override model hallucinations.
      </p>

      <form onSubmit={handlePublish} className="mt-4 space-y-4">
        <div>
          <label className="block text-xs font-semibold text-slate-700">Question or Frequent Query</label>
          <input
            type="text"
            value={questionText}
            onChange={(e) => setQuestionText(e.target.value)}
            placeholder="e.g. How do I claim travel reimbursement?"
            className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2 text-xs text-slate-900 focus:border-blue-500 focus:outline-hidden"
            required
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700">Approved Official Answer</label>
          <textarea
            value={approvedAnswer}
            onChange={(e) => setApprovedAnswer(e.target.value)}
            placeholder="Provide the exact, authoritative resolution text..."
            rows={4}
            className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2 text-xs text-slate-900 focus:border-blue-500 focus:outline-hidden"
            required
          />
        </div>

        <button
          type="submit"
          disabled={isSubmitting || !questionText.trim() || !approvedAnswer.trim()}
          className="flex items-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white shadow-xs hover:bg-emerald-700 transition-colors disabled:opacity-40"
        >
          {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlusCircle className="h-4 w-4" />}
          Publish to Approved QA Collection
        </button>

        {feedback && (
          <div
            className={`flex items-center gap-2 rounded-xl p-3 text-xs font-medium ${
              feedback.type === 'success'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                : 'bg-red-50 text-red-800 border border-red-200'
            }`}
          >
            {feedback.type === 'success' ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
            ) : (
              <AlertCircle className="h-4 w-4 shrink-0 text-red-600" />
            )}
            <span>{feedback.message}</span>
          </div>
        )}
      </form>
    </div>
  );
};
