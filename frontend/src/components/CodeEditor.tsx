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
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
        <h3 className="text-sm font-medium text-gray-400 mb-2">代码</h3>
        <p className="text-xs text-gray-600">等待生成...</p>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800">
        <h3 className="text-sm font-medium text-gray-400">最终代码</h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-600">{language}</span>
          <button
            onClick={handleCopy}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            {copied ? '已复制 ✓' : '复制'}
          </button>
        </div>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{
          margin: 0,
          padding: '1rem',
          fontSize: '0.8rem',
          background: 'transparent',
          maxHeight: '300px',
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
