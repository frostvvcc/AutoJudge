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
  const color =
    value >= 80 ? 'bg-green-500' : value >= 60 ? 'bg-yellow-500' : value >= 40 ? 'bg-orange-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-400 w-10">{label}</span>
      <div className="flex-1 bg-gray-100 rounded-full h-2">
        <div className={`h-2 rounded-full ${color}`} style={{ width: `${value}%` }} />
      </div>
      <span className="text-xs text-gray-600 w-10 text-right">{value}%</span>
    </div>
  );
}

export default function QualityReportPanel({ report, confidence }: Props) {
  const stars = report.star_rating || Math.round(confidence * 5);
  const starLabel = STAR_LABELS[stars] || '';

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 space-y-4">
      {/* Header: star rating */}
      <div className="text-center pb-3 border-b border-gray-200">
        <div className="text-2xl mb-1">
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i} className={i < stars ? 'text-yellow-400' : 'text-gray-700'}>★</span>
          ))}
        </div>
        <p className="text-sm font-medium text-gray-700">{starLabel}</p>
        <p className="text-xs text-gray-500 mt-1">{report.star_comment}</p>
        <p className="text-xs text-gray-600 mt-1">信心评分 {(confidence * 100).toFixed(0)}%</p>
      </div>

      {/* Resolved issues */}
      {report.resolved_issues.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-green-400 mb-2">✅ 已解决</h4>
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
          <h4 className="text-xs font-medium text-red-400 mb-2">🔴 未完全解决</h4>
          <div className="space-y-2">
            {report.unresolved_issues.map((item, i) => (
              <div key={i} className="bg-red-900/10 border border-red-900/30 rounded p-2">
                <p className="text-xs font-medium text-red-300">{item.issue}</p>
                <p className="text-xs text-gray-400 mt-1">状态：{item.current_status}</p>
                <p className="text-xs text-gray-400">影响：{item.impact}</p>
                <p className="text-xs text-blue-400 mt-1">建议：{item.suggestion}</p>
              </div>
            ))}
          </div>
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
          <p className="text-xs text-gray-600 leading-relaxed">{report.usage_advice}</p>
        </div>
      )}
    </div>
  );
}
