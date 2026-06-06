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
  c: 'C',
  cpp: 'C++',
  csharp: 'C#',
};

export default function HistoryPage() {
  const debate = useDebate();

  const [history, setHistory] = useState<api.PaginatedHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [langFilter, setLangFilter] = useState('');
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const hist = await api.listHistory({
        page,
        page_size: 15,
        language: langFilter || undefined,
        search: search || undefined,
      });
      setHistory(hist);
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
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 60) return `${diffMin} 分钟前`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `${diffH} 小时前`;
    const diffD = Math.floor(diffH / 24);
    if (diffD < 7) return `${diffD} 天前`;
    return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {/* Running task banner */}
        {(debate.status === 'running' || debate.status === 'connecting') && (
          <Link
            to="/workspace/live"
            className="block bg-blue-50 border border-blue-200 rounded-lg p-4 hover:bg-blue-100 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-sm text-blue-700">
                有任务正在生成中 — {debate.statusText || '处理中'}
              </span>
              <span className="text-xs text-blue-600 ml-auto">点击查看 &rarr;</span>
            </div>
          </Link>
        )}

        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">历史记录</h2>
        </div>

        {/* Search & Filters */}
        <div className="flex flex-col sm:flex-row gap-3">
          <form onSubmit={handleSearch} className="flex-1 flex gap-2">
            <div className="flex-1 relative">
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索任务描述..."
                className="w-full bg-white border border-gray-200 rounded-lg pl-10 pr-4 py-2.5 text-sm text-gray-800 placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>
            <button
              type="submit"
              className="px-4 py-2.5 bg-gray-100 hover:bg-gray-100 border border-gray-300 rounded-lg text-sm text-gray-600 transition-colors"
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
            className="bg-white border border-gray-200 rounded-lg px-3 py-2.5 text-sm text-gray-800 focus:outline-none focus:border-blue-500"
          >
            <option value="">所有语言</option>
            {Object.entries(LANG_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>

        {/* History List */}
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-white border border-gray-200 rounded-lg p-4 animate-pulse">
                <div className="h-4 bg-gray-100 rounded w-3/4 mb-3" />
                <div className="flex gap-3">
                  <div className="h-3 bg-gray-100 rounded w-16" />
                  <div className="h-3 bg-gray-100 rounded w-20" />
                  <div className="h-3 bg-gray-100 rounded w-12" />
                </div>
              </div>
            ))}
          </div>
        ) : !history || history.items.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-16 h-16 bg-gray-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
            </div>
            <h3 className="text-base font-medium text-gray-900 mb-2">还没有任何历史记录</h3>
            <p className="text-sm text-gray-500 mb-2 max-w-xs mx-auto">
              AutoJudge 会自动保存每次代码生成的完整辩论过程、风险评估和质量报告
            </p>
            <div className="text-xs text-gray-600 space-y-1 mb-6">
              <p>1. 描述你的编码需求</p>
              <p>2. 选择编程语言</p>
              <p>3. 等待多 Agent 辩论审查</p>
              <p>4. 获取经过验证的高质量代码</p>
            </div>
            <Link
              to="/dashboard"
              className="inline-block px-6 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium text-white transition-colors"
            >
              创建第一个任务
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {history.items.map((item) => (
              <div
                key={item.sid}
                className="bg-white border border-gray-200 rounded-lg p-4 hover:border-gray-300 transition-colors group"
              >
                <div className="flex items-start justify-between gap-4">
                  <Link to={`/workspace/${item.sid}`} className="flex-1 min-w-0">
                    <p className="text-sm text-gray-800 line-clamp-2 mb-2 group-hover:text-gray-900 transition-colors">
                      {item.task}
                    </p>
                    <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-xs text-gray-500">
                      <span className="px-2 py-0.5 bg-gray-100 rounded text-gray-400">
                        {LANG_LABELS[item.language] || item.language}
                      </span>
                      {item.converged ? (
                        <span className="text-green-400 flex items-center gap-1">
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                          </svg>
                          共识达成
                        </span>
                      ) : (
                        <span className="text-yellow-400">未达共识</span>
                      )}
                      <span>{item.total_rounds} 轮</span>
                      <span>置信度 {(item.confidence * 100).toFixed(0)}%</span>
                      <span className="hidden sm:inline">{formatDate(item.created_at)}</span>
                    </div>
                  </Link>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-gray-600 sm:hidden">{formatDate(item.created_at)}</span>
                    <button
                      onClick={() => handleDelete(item.sid)}
                      disabled={deleting === item.sid}
                      className="px-3 py-1 text-xs text-gray-500 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                    >
                      {deleting === item.sid ? '...' : '删除'}
                    </button>
                  </div>
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
              className="px-4 py-2 text-sm bg-gray-100 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-gray-600 transition-colors"
            >
              上一页
            </button>
            <span className="text-sm text-gray-500 px-3">
              {page} / {history.total_pages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(history.total_pages, p + 1))}
              disabled={page === history.total_pages}
              className="px-4 py-2 text-sm bg-gray-100 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-gray-600 transition-colors"
            >
              下一页
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
