import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import type { QualityReport } from '../../types/debate';

interface Props {
  report: QualityReport;
  confidence: number;
}

const STAR_LABELS: Record<number, string> = {
  5: '优秀',
  4: '良好',
  3: '合格',
  2: '待改进',
  1: '需人工介入',
};

function ScoreBar({ label, value }: { label: string; value: number }) {
  const hue = Math.round((value / 100) * 120);
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-400 w-10">{label}</span>
      <div className="flex-1 bg-gray-100 rounded-full h-2">
        <div className="h-2 rounded-full" style={{ width: `${value}%`, backgroundColor: `hsl(${hue}, 70%, 50%)` }} />
      </div>
      <span className="text-xs text-gray-600 w-10 text-right">{value}%</span>
    </div>
  );
}

export default function QualityReportPanel({ report, confidence }: Props) {
  const stars = report.star_rating || Math.round(confidence * 5);
  const starLabel = STAR_LABELS[stars] || '';
  const [showAllUnresolved, setShowAllUnresolved] = useState(false);

  const unresolvedToShow = showAllUnresolved
    ? report.unresolved_issues
    : report.unresolved_issues.slice(0, 3);

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 space-y-4">
      {/* Header: star rating */}
      <div className="text-center pb-3 border-b border-gray-200">
        <div className="text-2xl mb-1">
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i} className={i < stars ? 'text-yellow-400' : 'text-gray-200'}>★</span>
          ))}
        </div>
        <p className="text-sm font-medium text-gray-700">{starLabel}</p>
        <p className="text-xs text-gray-500 mt-1">{report.star_comment}</p>
        <p className="text-xs text-gray-600 mt-1">信心评分 {(confidence * 100).toFixed(0)}%</p>
      </div>

      {/* Resolved issues */}
      {report.resolved_issues.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-green-600 mb-2">✅ 已解决</h4>
          <ul className="space-y-1">
            {report.resolved_issues.map((issue, i) => (
              <li key={i} className="text-xs text-gray-600 flex items-start gap-1.5">
                <span className="text-green-500 mt-0.5 shrink-0">✓</span>
                {issue}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Unresolved issues */}
      {report.unresolved_issues.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-red-600 mb-2">
            🔴 未完全解决（{report.unresolved_issues.length} 条）
          </h4>
          <div className="space-y-2">
            {unresolvedToShow.map((item, i) => (
              <div key={i} className="bg-red-50 border border-red-200 rounded p-2">
                <p className="text-xs font-medium text-red-700">{item.issue || '未描述'}</p>
                <p className="text-xs text-gray-500 mt-1">状态：{item.current_status || '未评估'}</p>
                <p className="text-xs text-gray-500">影响：{item.impact || '待分析'}</p>
                <p className="text-xs text-blue-600 mt-1">建议：{item.suggestion || '暂无建议'}</p>
              </div>
            ))}
          </div>
          {report.unresolved_issues.length > 3 && (
            <button
              onClick={() => setShowAllUnresolved(!showAllUnresolved)}
              className="mt-2 text-xs text-blue-600 hover:text-blue-500"
            >
              {showAllUnresolved ? '↑ 收起' : `↓ 查看全部 ${report.unresolved_issues.length} 条`}
            </button>
          )}
        </div>
      )}

      {/* Score bars */}
      <div className="space-y-2 pt-2 border-t border-gray-200">
        <h4 className="text-xs text-gray-500 mb-1">质量详情</h4>
        <ScoreBar label="安全" value={report.score_security} />
        <ScoreBar label="性能" value={report.score_performance} />
        <ScoreBar label="正确" value={report.score_correctness} />
      </div>

      {/* Usage advice */}
      {report.usage_advice && (
        <div className="pt-2 border-t border-gray-200">
          <h4 className="text-xs text-gray-500 mb-1">💡 使用建议</h4>
          <div className="text-xs text-gray-600 leading-relaxed prose prose-xs max-w-none">
            <ReactMarkdown>{report.usage_advice}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}
