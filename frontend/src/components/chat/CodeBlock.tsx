import React, { useState } from 'react';
import { Copy, Check, Code2, Terminal } from 'lucide-react';

interface CodeBlockProps {
  inline?: boolean;
  className?: string;
  children?: React.ReactNode;
}

// Tokenize a line of code into comments, strings, words, and punctuation
function parseLineToTokens(line: string): string[] {
  if (!line) return [' '];

  // Regex captures:
  // 1: Comments (#... or //...)
  // 2: String literals ("..." or '...' or `...`)
  // 3: Words (\b\w+\b)
  // 4: Operators, punctuation, or spaces
  const regex = /(#.*|\/\/.*)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`[^`]*`)|(\b\w+\b)|([^\w\s]+|\s+)/g;
  const tokens: string[] = [];
  let m: RegExpExecArray | null;

  while ((m = regex.exec(line)) !== null) {
    tokens.push(m[0]);
  }

  return tokens.length > 0 ? tokens : [line];
}

// Render individual token as a clean React span with syntax colors
function renderToken(token: string, key: number) {
  if (!token) return null;

  // Comments (e.g. # comment or // comment)
  if (token.startsWith('#') || token.startsWith('//')) {
    return (
      <span key={key} className="text-slate-400 italic">
        {token}
      </span>
    );
  }

  // String literals (e.g. "hello", 'world')
  if (
    (token.startsWith('"') && token.endsWith('"')) ||
    (token.startsWith("'") && token.endsWith("'")) ||
    (token.startsWith('`') && token.endsWith('`'))
  ) {
    return (
      <span key={key} className="text-emerald-300 font-medium">
        {token}
      </span>
    );
  }

  // Python & JavaScript Keywords
  if (
    /^(def|class|return|import|from|async|await|const|let|var|function|if|else|elif|for|while|try|except|catch|finally|throw|raise|in|of|yield|pass|break|continue)$/.test(
      token
    )
  ) {
    return (
      <span key={key} className="text-sky-400 font-bold">
        {token}
      </span>
    );
  }

  // SQL Keywords
  if (
    /^(SELECT|FROM|WHERE|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|EXTENSION|AND|OR|NOT|JOIN|LEFT|RIGHT|INNER|ON|LIMIT|RETURNING)$/i.test(
      token
    )
  ) {
    return (
      <span key={key} className="text-purple-400 font-bold">
        {token}
      </span>
    );
  }

  // Common built-in functions
  if (/^(print|len|range|int|str|float|list|dict|set|console\.log)$/.test(token)) {
    return (
      <span key={key} className="text-amber-300 font-medium">
        {token}
      </span>
    );
  }

  // Booleans and Null
  if (/^(true|false|True|False|None|null|undefined)$/.test(token)) {
    return (
      <span key={key} className="text-rose-400 font-bold">
        {token}
      </span>
    );
  }

  // Numbers
  if (/^\d+$/.test(token)) {
    return (
      <span key={key} className="text-orange-300">
        {token}
      </span>
    );
  }

  // Standard variables, punctuation, whitespace
  return (
    <span key={key} className="text-slate-100">
      {token}
    </span>
  );
}

export const CodeBlock: React.FC<CodeBlockProps> = ({ inline, className, children, ...props }) => {
  const [copied, setCopied] = useState<boolean>(false);

  // Extract raw text content from children
  const rawCode = String(children).replace(/\n$/, '');

  // Inline code snippet (e.g., `vector(1536)`)
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

  const getLanguageIcon = (lang: string) => {
    switch (lang) {
      case 'bash':
      case 'sh':
      case 'shell':
      case 'powershell':
      case 'terminal':
      case 'cmd':
        return <Terminal className="h-3.5 w-3.5 text-emerald-400" />;
      default:
        return <Code2 className="h-3.5 w-3.5 text-sky-400" />;
    }
  };

  const lines = rawCode.split('\n');

  return (
    <div className="my-3.5 overflow-hidden rounded-xl border border-slate-700/80 bg-slate-950 shadow-lg">
      {/* Code Header Bar */}
      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900/90 px-4 py-2 text-xs">
        <div className="flex items-center gap-2">
          {getLanguageIcon(language)}
          <span className="font-mono font-bold uppercase tracking-wider text-slate-300 text-[11px]">
            {language}
          </span>
        </div>

        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors"
          title="Copy code to clipboard"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-emerald-400 font-semibold">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" />
              <span>Copy code</span>
            </>
          )}
        </button>
      </div>

      {/* Code Content Area */}
      <div className="overflow-x-auto p-4 text-[13px] leading-relaxed text-slate-100 font-mono bg-slate-950">
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((line, lineIdx) => {
              const tokens = parseLineToTokens(line);
              return (
                <tr key={lineIdx} className="hover:bg-slate-900/40 transition-colors">
                  <td className="select-none pr-4 text-right text-[11px] text-slate-600 font-mono w-9 align-top">
                    {lineIdx + 1}
                  </td>
                  <td className="whitespace-pre font-mono text-slate-100">
                    {tokens.map((token, tIdx) => renderToken(token, tIdx))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
