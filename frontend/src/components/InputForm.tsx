import { useState } from 'react';

interface Props {
  onSubmit: (task: string, language: string) => void;
  disabled: boolean;
}

const LANGUAGES = ['python', 'javascript', 'typescript', 'java', 'go', 'rust'];

export default function InputForm({ onSubmit, disabled }: Props) {
  const [task, setTask] = useState('');
  const [language, setLanguage] = useState('python');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (task.trim().length >= 10) {
      onSubmit(task.trim(), language);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <div className="flex gap-3">
        <div className="flex-1">
          <textarea
            id="task-input"
            aria-label="编码需求描述"
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="描述你的编码需求... (如: 实现用户注册接口，邮箱唯一，密码哈希存储)"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-100 placeholder-gray-500 resize-none focus:outline-none focus:border-blue-500"
            rows={2}
            disabled={disabled}
          />
          {task.length > 0 && task.trim().length < 10 && (
            <p className="mt-1 text-xs text-gray-500">
              还需输入 {10 - task.trim().length} 个字符
            </p>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <select
            aria-label="编程语言"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
            disabled={disabled}
          >
            {LANGUAGES.map((lang) => (
              <option key={lang} value={lang}>
                {lang}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={disabled || task.trim().length < 10}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg text-sm font-medium transition-colors"
          >
            {disabled ? (
              <span className="flex items-center justify-center gap-1.5">
                <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                运行中
              </span>
            ) : '开始生成'}
          </button>
        </div>
      </div>
    </form>
  );
}
