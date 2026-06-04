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
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="描述你的编码需求... (如: 实现用户注册接口，邮箱唯一，密码哈希存储)"
          className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-100 placeholder-gray-500 resize-none focus:outline-none focus:border-blue-500"
          rows={2}
          disabled={disabled}
        />
        <div className="flex flex-col gap-2">
          <select
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
            {disabled ? '运行中...' : '开始对抗'}
          </button>
        </div>
      </div>
    </form>
  );
}
