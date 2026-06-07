import { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';

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
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
      <div className="flex items-center justify-between px-3 py-1.5 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-500 font-medium">最终代码</span>
          <span className="text-[10px] text-gray-400">{language}</span>
          <span className="text-[10px] text-gray-400">{lineCount} 行</span>
        </div>
        <button
          onClick={handleCopy}
          className={`px-2 py-0.5 border rounded text-[10px] flex items-center gap-1 ${
            copied ? 'border-green-300 text-green-600' : 'border-gray-300 text-gray-500 hover:bg-gray-100'
          }`}
        >
          {copied ? '✓ 已复制' : '📋 复制代码'}
        </button>
      </div>
      <div className="bg-[#fafbfc] overflow-x-auto" style={{ maxHeight: '400px', overflowY: 'auto' }}>
        <SyntaxHighlighter
          language={language}
          style={oneLight}
          customStyle={{
            margin: 0,
            padding: '0.75rem',
            fontSize: '0.75rem',
            background: 'transparent',
          }}
          showLineNumbers
          lineNumberStyle={{ color: '#9ca3af', fontSize: '0.65rem' }}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}
