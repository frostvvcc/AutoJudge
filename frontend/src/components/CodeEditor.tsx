import { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface Props {
  code: string;
  language: string;
}

export default function CodeEditor({ code, language }: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!code) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex flex-col items-center justify-center py-8 text-gray-400">
          <svg className="w-10 h-10 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
          </svg>
          <span className="text-xs">等待 Coder 生成代码...</span>
        </div>
      </div>
    );
  }

  const lineCount = code.split('\n').length;

  return (
    <div className="rounded-xl overflow-hidden shadow-sm">
      <div className="flex items-center justify-between px-4 py-2 bg-[#282c34] border-b border-[#3e4451]">
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium text-gray-400">最终代码</span>
          <span className="text-xs text-gray-500">{language}</span>
          <span className="text-xs text-gray-500">{lineCount} 行</span>
        </div>
        <button
          onClick={handleCopy}
          className={`px-2.5 py-1 rounded text-xs transition-colors ${
            copied
              ? 'bg-green-600/20 text-green-400'
              : 'bg-white/10 text-gray-400 hover:bg-white/15 hover:text-gray-300'
          }`}
        >
          {copied ? '✓ 已复制' : '复制'}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{
          margin: 0,
          padding: '1rem',
          fontSize: '0.8rem',
          maxHeight: '450px',
        }}
        showLineNumbers
        lineNumberStyle={{ color: '#4a5568', fontSize: '0.7rem', minWidth: '2.5em' }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
