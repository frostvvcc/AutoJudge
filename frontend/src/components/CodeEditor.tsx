interface Props {
  code: string;
  language: string;
}

export default function CodeEditor({ code, language }: Props) {
  if (!code) {
    return (
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
        <h3 className="text-sm font-medium text-gray-400 mb-2">代码</h3>
        <p className="text-xs text-gray-600">等待生成...</p>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800">
        <h3 className="text-sm font-medium text-gray-400">最终代码</h3>
        <span className="text-xs text-gray-600">{language}</span>
      </div>
      <pre className="p-4 text-sm text-gray-300 overflow-x-auto max-h-[300px] overflow-y-auto">
        <code>{code}</code>
      </pre>
    </div>
  );
}
