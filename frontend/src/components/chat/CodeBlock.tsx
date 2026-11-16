import React, { useState } from 'react';
import { Copy, Check, Code2, Terminal } from 'lucide-react';

interface CodeBlockProps {
  inline?: boolean;
  className?: string;
  children?: React.ReactNode;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({ inline, className, children, ...props }) => {
  const [copied, setCopied] = useState<boolean>(false);

  // Extract raw text content from children
  const rawCode = String(children).replace(/\n$/, '');

  // If it's an inline code snippet (e.g., `vector(1536)`)
  if (inline || !className) {
    return (
      <code
        className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[13px] font-semibold text-blue-700 border border-slate-200/80"
        {...props}
      >
        {children}
      </code>
    );
  }

  // Extract language from className (e.g., "language-python" -> "python")
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1].toLowerCase() : 'code';

  const handleCopy = () => {
    navigator.clipboard.writeText(rawCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Basic syntax coloring helper for popular keywords
  const highlightCode = (code: string, lang: string) => {
    const lines = code.split('\n');
    return lines.map((line, lineIdx) => {
      // Tokens highlighting using regex replacements for display
      let highlighted = line
        // Comments (# or //)
        .replace(/(#.*|\/\/.*)$/g, '<span class="text-slate-500 italic">$1</span>')
        // Strings (double or single quotes)
        .replace(/(["'])(?:(?=(\\?))\2.)*?\1/g, '<span class="text-amber-300">$1</span>')
        // SQL keywords
        .replace(/\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP BY|ORDER BY|LIMIT|OFFSET|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|EXTENSION|IF NOT EXISTS|AND|OR|NOT|AS|RETURNING)\b/gi, '<span class="text-purple-400 font-bold">$1</span>')
        // Python/JS keywords
        .replace(/\b(def|class|return|import|from|async|await|const|let|var|function|if|else|elif|for|while|try|except|catch|finally|throw|raise|in|of|yield)\b/g, '<span class="text-blue-400 font-bold">$1</span>')
        // Booleans & Null
        .replace(/\b(true|false|True|False|None|null|undefined)\b/g, '<span class="text-rose-400 font-bold">$1</span>');

      return (
        <div key={lineIdx} className="table-row">
          <span className="table-cell select-none pr-4 text-right text-[11px] text-slate-600 font-mono w-8">
            {lineIdx + 1}
          </span>
          <span
            className="table-cell whitespace-pre font-mono"
            dangerouslySetToString={{ __html: highlighted || '&nbsp;' }}
          />
        </div>
      );
    });
  };

  const getLanguageIcon = (lang: string) => {
    switch (lang) {
      case 'bash':
      case 'sh':
      case 'shell':
      case 'powershell':
      case 'terminal':
        return <Terminal className="h-3.5 w-3.5 text-emerald-400" />;
      default:
        return <Code2 className="h-3.5 w-3.5 text-blue-400" />;
    }
  };

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-slate-700/80 bg-slate-900 shadow-md">
      {/* Code Header Bar */}
      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950/70 px-4 py-2 text-xs">
        <div className="flex items-center gap-2">
          {getLanguageIcon(language)}
          <span className="font-mono font-semibold uppercase tracking-wider text-slate-300 text-[11px]">
            {language}
          </span>
        </div>

        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
          title="Copy code to clipboard"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-emerald-400 font-bold">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" />
              <span>Copy code</span>
            </>
          )}
        </button>
      </div>

      {/* Code Content */}
      <div className="overflow-x-auto p-4 text-[13px] leading-relaxed text-slate-100 font-mono">
        <div className="table w-full">
          {highlightCode(rawCode, language)}
        </div>
      </div>
    </div>
  );
};
