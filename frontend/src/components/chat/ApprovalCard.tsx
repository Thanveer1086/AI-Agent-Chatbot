import React, { useState } from 'react';
import { ShieldAlert, Check, X, Loader2, CheckCircle2, XCircle, AlertTriangle, Clock } from 'lucide-react';
import { ToolApproval } from '../../types/chat';

interface ApprovalCardProps {
  approval: ToolApproval;
  onDecide: (approvalId: string, decision: 'approve' | 'reject') => Promise<string | null>;
}

const STATUS_BADGE: Record<string, { label: string; className: string; icon: React.ReactNode }> = {
  executing: { label: 'Running…', className: 'bg-blue-100 text-blue-700', icon: <Loader2 className="h-3 w-3 animate-spin" /> },
  executed: { label: 'Approved & executed', className: 'bg-emerald-100 text-emerald-700', icon: <CheckCircle2 className="h-3 w-3" /> },
  failed: { label: 'Approved, but failed', className: 'bg-red-100 text-red-700', icon: <AlertTriangle className="h-3 w-3" /> },
  rejected: { label: 'Rejected', className: 'bg-slate-200 text-slate-700', icon: <XCircle className="h-3 w-3" /> },
  expired: { label: 'Expired', className: 'bg-slate-200 text-slate-600', icon: <Clock className="h-3 w-3" /> },
};

/** Shows a write/destructive tool call the agent prepared and lets the user approve or reject it. */
export const ApprovalCard: React.FC<ApprovalCardProps> = ({ approval, onDecide }) => {
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isPending = approval.status === 'pending';
  const badge = STATUS_BADGE[approval.status];
  const args = Object.entries(approval.arguments || {});

  const decide = async (decision: 'approve' | 'reject') => {
    if (decision === 'approve' && approval.destructive) {
      const ok = window.confirm(`"${approval.title || approval.tool_name}" can delete or overwrite data. Run it?`);
      if (!ok) return;
    }
    setBusy(decision);
    setError(null);
    const err = await onDecide(approval.approval_id, decision);
    if (err) setError(err);
    setBusy(null);
  };

  return (
    <div
      className={`my-3 rounded-lg border p-3 text-xs shadow-sm ${
        isPending
          ? approval.destructive
            ? 'border-red-300 bg-red-50'
            : 'border-amber-300 bg-amber-50'
          : 'border-slate-200 bg-slate-50'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-semibold text-slate-800">
          <ShieldAlert className={`h-4 w-4 ${approval.destructive ? 'text-red-600' : 'text-amber-600'}`} />
          <span>{isPending ? 'Approval needed' : 'Action'}: {approval.title || approval.tool_name}</span>
          {approval.destructive && (
            <span className="rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold uppercase text-white">Destructive</span>
          )}
        </div>
        {badge && (
          <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}>
            {badge.icon}
            {badge.label}
          </span>
        )}
      </div>

      {approval.server && (
        <p className="mt-1 text-[11px] text-slate-500">
          Tool <code className="rounded bg-white/70 px-1">{approval.tool_name}</code> on server{' '}
          <span className="font-medium">{approval.server}</span>
        </p>
      )}

      {args.length > 0 && (
        <table className="mt-2 w-full border-collapse overflow-hidden rounded bg-white/80 text-[11px]">
          <tbody>
            {args.map(([key, value]) => (
              <tr key={key} className="border-b border-slate-100 last:border-0">
                <td className="w-1/4 px-2 py-1 align-top font-medium text-slate-600">{key}</td>
                <td className="px-2 py-1 font-mono text-slate-800 break-all whitespace-pre-wrap">
                  {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {isPending && (
        <div className="mt-3 flex items-center gap-2">
          <button
            onClick={() => decide('approve')}
            disabled={busy !== null}
            className="flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {busy === 'approve' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            Approve
          </button>
          <button
            onClick={() => decide('reject')}
            disabled={busy !== null}
            className="flex items-center gap-1 rounded-md border border-slate-300 bg-white px-3 py-1.5 font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            {busy === 'reject' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />}
            Reject
          </button>
          <span className="text-[11px] text-slate-500">Nothing runs until you approve.</span>
        </div>
      )}

      {error && <p className="mt-2 text-[11px] font-medium text-red-600">{error}</p>}
    </div>
  );
};
