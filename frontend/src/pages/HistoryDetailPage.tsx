import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useAuth } from '../contexts/AuthContext';
import * as api from '../lib/api';
import { AGENT_COLORS, AGENT_LABELS } from '../types/debate';

export default function HistoryDetailPage() {
  const { sid } = useParams<{ sid: string }>();
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [detail, setDetail] = useState<api.SessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!sid) return;
    setLoading(true);
    api
      .getSessionDetail(sid)
      .then(setDetail)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [sid]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <p className="text-gray-500">加载中...</p>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error || '记录不存在'}</p>
          <Link to="/history" className="text-blue-400 hover:text-blue-300 text-sm">
            返回历史记录
          </Link>
        </div>
      </div>
    );
  }

  const risk = detail.risk_json as Record<string, string> | null;
  const summary = detail.summary_json as Record<string, unknown> | null;

  const riskColor = (level: string) => {
    if (level === 'none') return 'text-green-400';
    if (level === 'low') return 'text-green-400';
    if (level === 'medium') return 'text-yellow-400';
    if (level === 'high') return 'text-orange-400';
    if (level === 'critical') return 'text-red-400';
    return 'text-gray-500';
  };

  const groupedMessages: Record<number, api.SessionMessage[]> = {};
  for (const msg of detail.messages) {
    const r = msg.round || 0;
    if (!groupedMessages[r]) groupedMessages[r] = [];
    groupedMessages[r].push(msg);
  }

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <Link to="/dashboard" className="flex items-center gap-3">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg" />
              <h1 className="text-xl font-bold text-white">AutoJudge</h1>
            </Link>
          </div>
          <div className="flex items-center gap-4">
            <Link
              to="/dashboard"
              className="text-sm text-gray-400 hover:text-white transition-colors"
            >
              新任务
            </Link>
            <Link
              to="/history"
              className="text-sm text-gray-400 hover:text-white transition-colors"
            >
              历史记录
            </Link>
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center text-xs text-white font-medium">
                {user?.username?.[0]?.toUpperCase()}
              </div>
              <span className="text-sm text-gray-300">{user?.username}</span>
            </div>
            <button
              onClick={() => {
                logout();
                navigate('/login');
              }}
              className="text-sm text-gray-500 hover:text-red-400 transition-colors"
            >
              退出
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Task Info */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
          <p className="text-gray-100 mb-3">{detail.task}</p>
          <div className="flex flex-wrap gap-3 text-xs text-gray-500">
            <span className="px-2 py-0.5 bg-gray-800 rounded text-gray-400">
              {detail.language}
            </span>
            {detail.framework && (
              <span className="px-2 py-0.5 bg-gray-800 rounded text-gray-400">
                {detail.framework}
              </span>
            )}
            <span>
              {detail.converged ? (
                <span className="text-green-400">
                  共识达成 — {detail.convergence_reason}
                </span>
              ) : (
                <span className="text-yellow-400">未达共识</span>
              )}
            </span>
            <span>置信度 {(detail.confidence * 100).toFixed(0)}%</span>
            <span>{detail.total_rounds} 轮</span>
            <span>{detail.total_tokens} tokens</span>
            <span>${detail.cost_usd.toFixed(4)}</span>
            <span>{(detail.total_latency_ms / 1000).toFixed(1)}s</span>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Messages */}
          <div className="lg:col-span-2 space-y-4">
            {Object.entries(groupedMessages)
              .sort(([a], [b]) => Number(a) - Number(b))
              .map(([round, msgs]) => (
                <div key={round}>
                  {Number(round) > 0 && (
                    <div className="flex items-center gap-2 mb-3">
                      <div className="h-px flex-1 bg-gray-800" />
                      <span className="text-xs text-gray-500 font-medium">
                        Round {round}
                      </span>
                      <div className="h-px flex-1 bg-gray-800" />
                    </div>
                  )}
                  {msgs.map((msg, idx) => {
                    const colors = AGENT_COLORS[msg.agent] || 'border-gray-500 bg-gray-500/10';
                    return (
                      <div
                        key={`${round}-${idx}`}
                        className={`border-l-2 ${colors} rounded-r-lg px-4 py-3 mb-2`}
                      >
                        <div className="text-xs font-medium text-gray-400 mb-1">
                          {AGENT_LABELS[msg.agent] || msg.agent}
                        </div>
                        <div className="text-sm text-gray-200 prose prose-invert prose-sm max-w-none">
                          <ReactMarkdown>{msg.content}</ReactMarkdown>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))}
          </div>

          {/* Right: Code + Risk + Summary */}
          <div className="space-y-4">
            {/* Code */}
            {detail.result_code && (
              <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
                <div className="px-4 py-2 border-b border-gray-800 flex items-center justify-between">
                  <span className="text-xs text-gray-400 font-medium">最终代码</span>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(detail.result_code || '');
                      setCopied(true);
                      setTimeout(() => setCopied(false), 2000);
                    }}
                    className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
                  >
                    {copied ? '已复制 ✓' : '复制'}
                  </button>
                </div>
                <SyntaxHighlighter
                  language={detail.language}
                  style={oneDark}
                  customStyle={{
                    margin: 0,
                    padding: '1rem',
                    fontSize: '0.8rem',
                    background: 'transparent',
                    maxHeight: '400px',
                  }}
                >
                  {detail.result_code}
                </SyntaxHighlighter>
              </div>
            )}

            {/* Risk */}
            {risk && (
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <h3 className="text-sm font-medium text-gray-300 mb-3">风险评估</h3>
                <div className="space-y-2">
                  {['security', 'performance', 'correctness'].map((dim) => (
                    <div key={dim} className="flex items-center justify-between">
                      <span className="text-xs text-gray-400 capitalize">{dim}</span>
                      <span className={`text-xs font-medium ${riskColor(risk[dim] || 'unknown')}`}>
                        {risk[dim] || 'unknown'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Summary */}
            {summary && (
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <h3 className="text-sm font-medium text-gray-300 mb-3">辩论摘要</h3>
                <div className="space-y-2 text-xs text-gray-400">
                  <div className="flex justify-between">
                    <span>提出问题</span>
                    <span className="text-gray-300">
                      {(summary.total_issues_raised as number) ?? 0}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>已修复</span>
                    <span className="text-green-400">
                      {(summary.accepted_and_fixed as number) ?? 0}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>驳回</span>
                    <span className="text-yellow-400">
                      {(summary.rejected_by_coder as number) ?? 0}
                    </span>
                  </div>
                </div>
                {Array.isArray(summary.key_improvements) &&
                  summary.key_improvements.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-800">
                      <p className="text-xs text-gray-500 mb-1">关键改进：</p>
                      <ul className="text-xs text-gray-400 space-y-1">
                        {(summary.key_improvements as string[]).map((imp: string, i: number) => (
                          <li key={i}>- {imp}</li>
                        ))}
                      </ul>
                    </div>
                  )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
