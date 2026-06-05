import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import NavBar from '../components/NavBar';
import { useAuth } from '../contexts/AuthContext';
import { useDebate } from '../contexts/DebateContext';
import { LANGUAGE_GROUPS } from '../types/debate';
import * as api from '../lib/api';

const EXAMPLES = [
  { icon: '🔐', title: '用户认证', desc: '实现 JWT 登录接口，密码 bcrypt 加密，含 token 刷新', lang: 'python' },
  { icon: '📊', title: '数据处理', desc: '编写 CSV 文件解析器，支持大文件流式读取和数据清洗', lang: 'python' },
  { icon: '🌐', title: 'REST API', desc: '实现一个 CRUD RESTful API，含参数校验和错误处理', lang: 'typescript' },
  { icon: '🔍', title: '算法实现', desc: '实现 LRU 缓存，支持 O(1) 的 get 和 put 操作', lang: 'python' },
];

export default function TaskCenter() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const debate = useDebate();
  const [task, setTask] = useState('');
  const [language, setLanguage] = useState('python');
  const [stats, setStats] = useState<api.StatsOut | null>(null);
  const [recentTasks, setRecentTasks] = useState<api.SessionBrief[]>([]);

  const fetchData = useCallback(async () => {
    try {
      const [st, hist] = await Promise.all([
        api.getStats(),
        api.listHistory({ page: 1, page_size: 3 }),
      ]);
      setStats(st);
      setRecentTasks(hist.items);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (task.trim().length >= 10) {
      debate.submit(task.trim(), language);
      navigate('/workspace/live');
    }
  };

  const handleUseExample = (example: typeof EXAMPLES[0]) => {
    setTask(example.desc);
    setLanguage(example.lang);
  };

  const isRunning = debate.status === 'running' || debate.status === 'connecting';

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 60) return `${diffMin} 分钟前`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `${diffH} 小时前`;
    const diffD = Math.floor(diffH / 24);
    if (diffD < 7) return `${diffD} 天前`;
    return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
  };

  return (
    <div className="min-h-screen bg-gray-950">
      <NavBar />

      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-6">
        {/* Running task banner */}
        {isRunning && (
          <button
            onClick={() => navigate('/workspace/live')}
            className="w-full bg-blue-900/30 border border-blue-800 rounded-lg p-4 hover:bg-blue-900/40 transition-colors text-left"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                <span className="text-sm text-blue-300">
                  任务进行中 — {debate.statusText || '处理中'}
                </span>
              </div>
              <span className="text-xs text-blue-400">进入工作台 &rarr;</span>
            </div>
          </button>
        )}

        {/* Welcome */}
        <div>
          <h2 className="text-lg font-semibold text-white">
            欢迎回来，{user?.username}
          </h2>
          <p className="text-sm text-gray-500 mt-1">描述你的编码需求，AI Agent 会从安全、性能、正确性三个维度审查优化</p>
        </div>

        {/* New task form */}
        <form onSubmit={handleSubmit} className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="描述你的编码需求..."
            className="w-full bg-transparent px-5 py-4 text-sm text-gray-100 placeholder-gray-500 resize-none focus:outline-none"
            rows={4}
            disabled={isRunning}
          />
          <div className="flex items-center justify-between px-5 py-3 border-t border-gray-800 bg-gray-800/20">
            <div className="flex items-center gap-3">
              <label className="text-xs text-gray-500">语言</label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
                disabled={isRunning}
              >
                {LANGUAGE_GROUPS.map((group) => (
                  <optgroup key={group.group} label={group.group}>
                    {group.languages.map((lang) => (
                      <option key={lang.value} value={lang.value}>{lang.label}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
              {task.length > 0 && task.trim().length < 10 && (
                <span className="text-xs text-gray-600">
                  还需 {10 - task.trim().length} 个字符
                </span>
              )}
            </div>
            <button
              type="submit"
              disabled={isRunning || task.trim().length < 10}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg text-sm font-medium text-white transition-colors flex items-center gap-2"
            >
              {isRunning ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  运行中
                </>
              ) : (
                '开始生成'
              )}
            </button>
          </div>
        </form>

        {/* Example templates */}
        <div>
          <h3 className="text-sm font-medium text-gray-400 mb-3">试试这些示例</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {EXAMPLES.map((ex) => (
              <button
                key={ex.title}
                onClick={() => handleUseExample(ex)}
                disabled={isRunning}
                className="text-left bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-gray-700 hover:bg-gray-800/50 transition-colors disabled:opacity-50 group"
              >
                <div className="text-lg mb-2">{ex.icon}</div>
                <div className="text-sm font-medium text-white mb-1">{ex.title}</div>
                <div className="text-xs text-gray-500 line-clamp-2 leading-relaxed">{ex.desc}</div>
                <div className="mt-2 text-xs text-gray-600 group-hover:text-blue-400 transition-colors">
                  {ex.lang}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Stats */}
        {stats && stats.total_sessions > 0 && (
          <div>
            <h3 className="text-sm font-medium text-gray-400 mb-3">你的统计</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <StatCard icon="📝" value={String(stats.total_sessions)} label="总任务" />
              <StatCard
                icon="🎯"
                value={`${(stats.converge_rate * 100).toFixed(0)}%`}
                label="共识率"
              />
              <StatCard
                icon="🔤"
                value={stats.total_tokens > 10000 ? `${(stats.total_tokens / 1000).toFixed(0)}k` : String(stats.total_tokens)}
                label="Token"
              />
              <StatCard icon="💰" value={`$${stats.total_cost_usd.toFixed(2)}`} label="总费用" />
            </div>
          </div>
        )}

        {/* Recent tasks */}
        {recentTasks.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-gray-400">最近任务</h3>
              <Link to="/history" className="text-xs text-gray-600 hover:text-blue-400 transition-colors">
                查看全部 &rarr;
              </Link>
            </div>
            <div className="space-y-2">
              {recentTasks.map((item) => (
                <Link
                  key={item.sid}
                  to={`/workspace/${item.sid}`}
                  className="block bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 hover:border-gray-700 transition-colors"
                >
                  <div className="flex items-center justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-200 truncate">{item.task}</p>
                      <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-500">
                        <span className="px-1.5 py-0.5 bg-gray-800 rounded text-gray-400">{item.language}</span>
                        {item.converged ? (
                          <span className="text-green-400">共识达成</span>
                        ) : (
                          <span className="text-yellow-400">未达共识</span>
                        )}
                        <span>{item.total_rounds} 轮</span>
                      </div>
                    </div>
                    <span className="text-xs text-gray-600 shrink-0">{formatDate(item.created_at)}</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function StatCard({ icon, value, label }: { icon: string; value: string; label: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-sm">{icon}</span>
        <span className="text-lg font-bold text-white">{value}</span>
      </div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );
}
