import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import NavBar from '../components/NavBar';
import * as api from '../lib/api';
import { AGENT_COLORS, AGENT_LABELS } from '../types/debate';

export default function HistoryDetailPage() {
  const { sid } = useParams<{ sid: string }>();
  const navigate = useNavigate();

  const [detail, setDetail] = useState<api.SessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [codeCopied, setCodeCopied] = useState(false);
  const [copiedMsgIdx, setCopiedMsgIdx] = useState<string | null>(null);

  useEffect(() => {
    if (!sid) return;
    setLoading(true);
    api
      .getSessionDetail(sid)
      .then(setDetail)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [sid]);

  const copyText = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedMsgIdx(key);
    setTimeout(() => setCopiedMsgIdx(null), 2000);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <NavBar />
        <div className="flex items-center justify-center py-20">
          <div className="flex items-center gap-3">
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-gray-500 text-sm">加载中...</span>
          </div>
        </div>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="min-h-screen bg-gray-50">
        <NavBar />
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <p className="text-red-500 text-sm">{error || '记录不存在'}</p>
          <Link to="/history" className="text-blue-600 hover:text-blue-500 text-sm">
            返回历史记录
          </Link>
        </div>
      </div>
    );
  }

  const risk = detail.risk_json as Record<string, string> | null;
  const summary = detail.summary_json as Record<string, unknown> | null;

  const riskColor = (level: string) => {
    if (level === 'none' || level === 'low') return 'text-green-600';
    if (level === 'medium') return 'text-yellow-600';
    if (level === 'high') return 'text-orange-600';
    if (level === 'critical') return 'text-red-600';
    return 'text-gray-500';
  };

  const groupedMessages: Record<number, api.SessionMessage[]> = {};
  for (const msg of detail.messages) {
    const r = msg.round || 0;
    if (!groupedMessages[r]) groupedMessages[r] = [];
    groupedMessages[r].push(msg);
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {/* Task Info */}
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <p className="text-gray-800 leading-relaxed">{detail.task}</p>
            <button
              onClick={() => navigate('/history')}
              className="shrink-0 text-xs text-gray-400 hover:text-gray-600 transition-colors"
            >
              返回列表
            </button>
          </div>
          <div className="flex flex-wrap gap-3 mt-3 text-xs text-gray-500">
            <span className="px-2 py-0.5 bg-blue-50 rounded text-blue-600 font-medium">
              {detail.language}
            </span>
            {detail.framework && (
              <span className="px-2 py-0.5 bg-gray-100 rounded text-gray-500">
                {detail.framework}
              </span>
            )}
            <span>
              {detail.converged ? (
                <span className="text-green-600">
                  共识达成 — {detail.convergence_reason}
                </span>
              ) : (
                <span className="text-yellow-600">未达共识</span>
              )}
            </span>
            <span>置信度 {(detail.confidence * 100).toFixed(0)}%</span>
            <span>{detail.total_rounds} 轮</span>
            <span>{detail.total_tokens.toLocaleString()} tokens</span>
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
                      <div className="h-px flex-1 bg-gray-200" />
                      <span className="text-xs text-gray-400 font-medium">
                        Round {round}
                      </span>
                      <div className="h-px flex-1 bg-gray-200" />
                    </div>
                  )}
                  {msgs.map((msg, idx) => {
                    const colors = AGENT_COLORS[msg.agent] || 'border-gray-300 bg-gray-50';
                    const msgKey = `${round}-${idx}`;
                    return (
                      <div
                        key={msgKey}
                        className={`group border-l-2 ${colors} rounded-r-lg px-4 py-3 mb-2 relative`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-medium text-gray-500">
                            {AGENT_LABELS[msg.agent] || msg.agent}
                          </span>
                          <button
                            onClick={() => copyText(msg.content, msgKey)}
                            className="opacity-0 group-hover:opacity-100 text-xs text-gray-400 hover:text-gray-600 transition-all"
                          >
                            {copiedMsgIdx === msgKey ? '已复制 ✓' : '复制'}
                          </button>
                        </div>
                        <div className="text-sm text-gray-700 prose prose-sm max-w-none">
                          <ReactMarkdown>{msg.content}</ReactMarkdown>
                        </div>
                        {msg.code && (
                          <div className="mt-2 bg-gray-50 rounded border border-gray-200 overflow-hidden">
                            <div className="flex items-center justify-between px-3 py-1 border-b border-gray-200">
                              <span className="text-[10px] text-gray-400">代码</span>
                              <button
                                onClick={() => copyText(msg.code!, `code-${msgKey}`)}
                                className="text-[10px] text-gray-400 hover:text-gray-600"
                              >
                                {copiedMsgIdx === `code-${msgKey}` ? '已复制' : '复制'}
                              </button>
                            </div>
                            <SyntaxHighlighter
                              language={detail.language}
                              style={oneLight}
                              customStyle={{ margin: 0, padding: '0.75rem', fontSize: '0.75rem', background: 'transparent', maxHeight: '200px' }}
                            >
                              {msg.code}
                            </SyntaxHighlighter>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ))}
          </div>

          {/* Right: Code + Risk + Summary */}
          <div className="space-y-4">
            {/* Final Code */}
            {detail.result_code && (
              <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
                <div className="px-4 py-2.5 border-b border-gray-200 flex items-center justify-between">
                  <span className="text-xs text-gray-500 font-medium">最终代码</span>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(detail.result_code || '');
                      setCodeCopied(true);
                      setTimeout(() => setCodeCopied(false), 2000);
                    }}
                    className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
                  >
                    {codeCopied ? '已复制 ✓' : '复制代码'}
                  </button>
                </div>
                <SyntaxHighlighter
                  language={detail.language}
                  style={oneLight}
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
              <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
                <h3 className="text-sm font-medium text-gray-700 mb-3">风险评估</h3>
                <div className="space-y-2">
                  {['security', 'performance', 'correctness'].map((dim) => (
                    <div key={dim} className="flex items-center justify-between">
                      <span className="text-xs text-gray-500 capitalize">{dim}</span>
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
              <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
                <h3 className="text-sm font-medium text-gray-700 mb-3">辩论摘要</h3>
                <div className="space-y-2 text-xs text-gray-500">
                  <div className="flex justify-between">
                    <span>提出问题</span>
                    <span className="text-gray-700 font-medium">
                      {(summary.total_issues_raised as number) ?? 0}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>已修复</span>
                    <span className="text-green-600 font-medium">
                      {(summary.accepted_and_fixed as number) ?? 0}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>驳回</span>
                    <span className="text-yellow-600 font-medium">
                      {(summary.rejected_by_coder as number) ?? 0}
                    </span>
                  </div>
                </div>
                {Array.isArray(summary.key_improvements) &&
                  summary.key_improvements.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-100">
                      <p className="text-xs text-gray-500 mb-1">关键改进：</p>
                      <ul className="text-xs text-gray-600 space-y-1">
                        {(summary.key_improvements as string[]).map((imp: string, i: number) => (
                          <li key={i} className="flex items-start gap-1">
                            <span className="text-green-500 mt-0.5">•</span>
                            <span>{imp}</span>
                          </li>
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
