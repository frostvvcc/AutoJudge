import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import NavBar from '../components/NavBar';
import { useDebate } from '../contexts/DebateContext';
import { LANGUAGE_GROUPS } from '../types/debate';

export default function TaskCenter() {
  const navigate = useNavigate();
  const debate = useDebate();
  const [task, setTask] = useState('');
  const [language, setLanguage] = useState('python');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (task.trim().length >= 10) {
      debate.submit(task.trim(), language);
      navigate('/workspace/live');
    }
  };

  const isRunning = debate.status === 'running' || debate.status === 'connecting';

  return (
    <div className="min-h-screen bg-gray-950">
      <NavBar />

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        {/* Running task banner */}
        {isRunning && (
          <button
            onClick={() => navigate('/workspace/live')}
            className="w-full bg-blue-900/30 border border-blue-800 rounded-lg p-4 hover:bg-blue-900/40 transition-colors text-left"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex gap-1">
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <span className="text-sm text-blue-300">
                  任务进行中 — {debate.statusText || '处理中'}
                </span>
              </div>
              <span className="text-xs text-blue-400">进入工作台 →</span>
            </div>
          </button>
        )}

        {/* New task form */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
          <h2 className="text-lg font-semibold text-white mb-4">新建任务</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <textarea
                value={task}
                onChange={(e) => setTask(e.target.value)}
                placeholder="描述你的编码需求...&#10;&#10;例如：实现一个用户登录接口，支持用户名密码登录，密码需要 bcrypt 加密存储，返回 JWT token"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-100 placeholder-gray-500 resize-none focus:outline-none focus:border-blue-500 transition-colors"
                rows={5}
                disabled={isRunning}
              />
              {task.length > 0 && task.trim().length < 10 && (
                <p className="mt-1 text-xs text-gray-500">
                  还需输入 {10 - task.trim().length} 个字符
                </p>
              )}
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <label className="text-sm text-gray-400">编程语言</label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
                  disabled={isRunning}
                >
                  {LANGUAGE_GROUPS.map((group) => (
                    <optgroup key={group.group} label={group.group}>
                      {group.languages.map((lang) => (
                        <option key={lang.value} value={lang.value}>
                          {lang.label}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>

              <button
                type="submit"
                disabled={isRunning || task.trim().length < 10}
                className="px-8 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg text-sm font-medium transition-colors"
              >
                {isRunning ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    运行中
                  </span>
                ) : (
                  '开始生成 →'
                )}
              </button>
            </div>
          </form>
        </div>

        {/* Recent tasks hint */}
        <div className="text-center">
          <button
            onClick={() => navigate('/history')}
            className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
          >
            查看历史记录 →
          </button>
        </div>
      </main>
    </div>
  );
}
