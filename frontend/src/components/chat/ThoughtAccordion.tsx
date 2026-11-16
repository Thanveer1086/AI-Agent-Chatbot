import React, { useState } from 'react';
import { ChevronDown, ChevronRight, BrainCircuit, Wrench, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { ThoughtStep, ToolTrace } from '../../types/chat';

interface ThoughtAccordionProps {
  thoughts: ThoughtStep[];
  toolTraces: ToolTrace[];
}

export const ThoughtAccordion: React.FC<ThoughtAccordionProps> = ({ thoughts, toolTraces }) => {
  const [isOpen, setIsOpen] = useState<boolean>(true);

  if (thoughts.length === 0 && toolTraces.length === 0) return null;

  return (
    <div className="mb-3 rounded-lg border border-slate-200 bg-slate-50/80 overflow-hidden text-xs shadow-sm">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between px-3 py-2 text-left font-medium text-slate-700 hover:bg-slate-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          <BrainCircuit className="h-4 w-4 text-blue-600 animate-pulse" />
          <span>Agent Reasoning & Tool Execution</span>
          <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700">
            {thoughts.length} steps · {toolTraces.length} tools
          </span>
        </div>
        {isOpen ? (
          <ChevronDown className="h-4 w-4 text-slate-400" />
        ) : (
          <ChevronRight className="h-4 w-4 text-slate-400" />
        )}
      </button>

      {isOpen && (
        <div className="space-y-2 border-t border-slate-200 p-3 bg-white/50">
          {/* Thoughts List */}
          {thoughts.map((item, idx) => (
            <div key={idx} className="flex items-start gap-2 text-slate-600">
              <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-slate-200 text-[10px] font-bold text-slate-700">
                {item.step}
              </span>
              <p className="flex-1 leading-relaxed">{item.thought}</p>
            </div>
          ))}

          {/* Tools Traces List */}
          {toolTraces.length > 0 && (
            <div className="mt-2 pt-2 border-t border-slate-200/60 space-y-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                Tool Invocation Trace
              </span>
              <div className="flex flex-wrap gap-2">
                {toolTraces.map((trace, idx) => (
                  <div
                    key={idx}
                    className="flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 shadow-2xs"
                  >
                    <Wrench className="h-3 w-3 text-slate-500" />
                    <span className="font-mono text-[11px] font-semibold text-slate-800">
                      {trace.tool_name}
                    </span>
                    {trace.status === 'running' && (
                      <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
                    )}
                    {trace.status === 'success' && (
                      <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                    )}
                    {trace.status === 'error' && (
                      <AlertCircle className="h-3 w-3 text-red-500" />
                    )}
                    {trace.duration_ms !== undefined && (
                      <span className="text-[10px] text-slate-400 font-mono">
                        {trace.duration_ms}ms
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
