import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { useDebate } from '../contexts/DebateContext';
import * as api from '../lib/api';
import NavBar from '../components/NavBar';

const LANG_LABELS: Record<string, string> = {
  python: 'Python',
  javascript: 'JavaScript',
  typescript: 'TypeScript',
  java: 'Java',
  go: 'Go',
  rust: 'Rust',
};

export default function HistoryPage() {
  const debate = useDebate();

  const [history, setHistory] = useState<api.PaginatedHistory | null>(null);
  const [stats, setStats] = useState<api.StatsOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [langFilter, setLangFilter] = useState('');
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [hist, st] = await Promise.all([
        api.listHistory({
          page,
          page_size: 15,
          language: langFilter || undefined,
          search: search || undefined,
        }),
        api.getStats(),
      ]);
      setHistory(hist);
      setStats(st);
    } catch {
      // handled by api layer
    } finally {
      setLoading(false);
    }
  }, [page, search, langFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleDelete = async (sid: string) => {
    if (!confirm('确定要删除这条记录吗？')) return;
    setDeleting(sid);
    try {
      await api.deleteSession(sid);
      fetchData();
    } finally {
      setDeleting(null);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
  };

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="min-h-screen bg-gray-950">
      <NavBar />

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Running task banner */}
        {(debate.status === 'running' || debate.status === 'connecting') && (
          <Link
            to="/"
            className="block bg-blue-900/30 border border-blue-800 rounded-lg p-4 hover:bg-blue-900/40 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="flex gap-1">
                <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-sm text-blue-300">
                有任务正在生成中 — {debate.statusText || '处理中'}
              </span>
              <span className="text-xs text-blue-400 ml-auto">点击查看 &rarr;</span>
            </div>
          </Link>
        )}

        {/* Stats Cards */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="text-2xl font-bold text-white">{stats.total_sessions}</div>
              <div className="text-sm text-gray-500">总生成次数</div>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="text-2xl font-bold text-white">
                {stats.total_tokens > 10000
                  ? `${(stats.total_tokens / 1000).toFixed(0)}k`
                  : stats.total_tokens}
              </div>
              <div className="text-sm text-gray-500">总 Token 消耗</div>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="text-2xl font-bold text-white">
                {(stats.converge_rate * 100).toFixed(0)}%
              </div>
              <div className="text-sm text-gray-500">共识达成率</div>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="text-2xl font-bold text-white">
                ${stats.total_cost_usd.toFixed(2)}
              </div>
              <div className="text-sm text-gray-500">总费用</div>
            </div>
          </div>
        )}

        {/* Search & Filters */}
        <div className="flex flex-col sm:flex-row gap-3">
          <form onSubmit={handleSearch} className="flex-1 flex gap-2">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索任务描述..."
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
            <button
              type="submit"
              className="px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-sm text-gray-300"
            >
              搜索
            </button>
          </form>
          <select
            value={langFilter}
            onChange={(e) => {
              setLangFilter(e.target.value);
              setPage(1);
            }}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
          >
            <option value="">所有语言</option>
            {Object.entries(LANG_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </div>

        {/* History List */}
        {loading ? (
          <div className="text-center py-12 text-gray-500">加载中...</div>
        ) : !history || history.items.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-500 mb-4">暂无历史记录</p>
            <Link
              to="/"
              className="inline-block px-6 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm text-white"
            >
              开始第一次生成
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {history.items.map((item) => (
              <div
                key={item.sid}
                className="bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-gray-700 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <Link to={`/workspace/${item.sid}`} className="flex-1 min-w-0">
                    <p className="text-sm text-gray-100 line-clamp-2 mb-2">{item.task}</p>
                    <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500">
                      <span className="px-2 py-0.5 bg-gray-800 rounded text-gray-400">
                        {LANG_LABELS[item.language] || item.language}
                      </span>
                      <span>
                        {item.converged ? (
                          <span className="text-green-400">共识达成</span>
                        ) : (
                          <span className="text-yellow-400">未达共识</span>
                        )}
                      </span>
                      <span>{item.total_rounds} 轮</span>
                      <span>置信度 {(item.confidence * 100).toFixed(0)}%</span>
                      <span>{formatDate(item.created_at)}</span>
                    </div>
                  </Link>
                  <button
                    onClick={() => handleDelete(item.sid)}
                    disabled={deleting === item.sid}
                    className="shrink-0 px-3 py-1 text-xs text-gray-500 hover:text-red-400 hover:bg-red-900/20 rounded transition-colors"
                  >
                    {deleting === item.sid ? '删除中' : '删除'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Pagination */}
        {history && history.total_pages > 1 && (
          <div className="flex items-center justify-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1.5 text-sm bg-gray-800 hover:bg-gray-700 disabled:opacity-50 rounded-lg text-gray-300"
            >
              上一页
            </button>
            <span className="text-sm text-gray-500">
              {page} / {history.total_pages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(history.total_pages, p + 1))}
              disabled={page === history.total_pages}
              className="px-3 py-1.5 text-sm bg-gray-800 hover:bg-gray-700 disabled:opacity-50 rounded-lg text-gray-300"
            >
              下一页
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
