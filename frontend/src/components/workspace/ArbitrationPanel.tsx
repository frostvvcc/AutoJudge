import { useState, useCallback } from 'react';

interface Ruling {
  dispute_id: string;
  verdict: string;
  re_assessed_severity: string;
  reasoning: string;
}

interface OverrideAction {
  action: string;
  new_verdict: string;
}

interface Props {
  rulings: Ruling[];
  overallVerdict: string;
  summary: string;
  confidence: number;
  onAccept: () => void;
  onOverride: (overrides: Record<string, OverrideAction>) => void;
}

const VERDICT_STYLES: Record<string, { bg: string; text: string; border: string; label: string }> = {
  dismissed: { bg: 'bg-gray-100', text: 'text-gray-400', border: 'border-gray-200', label: 'Dismissed' },
  acknowledged: { bg: 'bg-blue-900/30', text: 'text-blue-400', border: 'border-blue-700/40', label: 'Acknowledged' },
  must_fix: { bg: 'bg-red-900/30', text: 'text-red-400', border: 'border-red-700/40', label: 'Must Fix' },
  deferred: { bg: 'bg-yellow-900/30', text: 'text-yellow-400', border: 'border-yellow-700/40', label: 'Deferred' },
  needs_human: { bg: 'bg-purple-900/30', text: 'text-purple-400', border: 'border-purple-700/40', label: 'Needs Human' },
};

const SEVERITY_STYLES: Record<string, { dot: string; text: string }> = {
  critical: { dot: 'bg-red-500', text: 'text-red-400' },
  high: { dot: 'bg-orange-500', text: 'text-orange-400' },
  medium: { dot: 'bg-yellow-500', text: 'text-yellow-400' },
  low: { dot: 'bg-gray-500', text: 'text-gray-400' },
};

const VERDICT_ORDER = ['dismissed', 'acknowledged', 'deferred', 'must_fix', 'needs_human'];

function getVerdictStyle(verdict: string) {
  return VERDICT_STYLES[verdict] ?? VERDICT_STYLES.dismissed;
}

function getSeverityStyle(severity: string) {
  return SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.low;
}

export default function ArbitrationPanel({
  rulings,
  overallVerdict,
  summary,
  confidence,
  onAccept,
  onOverride,
}: Props) {
  const [mode, setMode] = useState<'view' | 'override'>('view');
  const [overrides, setOverrides] = useState<Record<string, OverrideAction>>({});

  const isCritical = (ruling: Ruling) => ruling.re_assessed_severity === 'critical';

  const handleOverrideAction = useCallback((disputeId: string, action: string, currentVerdict: string) => {
    setOverrides((prev) => {
      const next = { ...prev };
      const currentIdx = VERDICT_ORDER.indexOf(currentVerdict);

      if (action === 'upgrade') {
        const newIdx = Math.min(currentIdx + 1, VERDICT_ORDER.length - 1);
        next[disputeId] = { action: 'upgrade', new_verdict: VERDICT_ORDER[newIdx] };
      } else if (action === 'downgrade') {
        const newIdx = Math.max(currentIdx - 1, 0);
        next[disputeId] = { action: 'downgrade', new_verdict: VERDICT_ORDER[newIdx] };
      } else if (action === 'dismiss') {
        next[disputeId] = { action: 'dismiss', new_verdict: 'dismissed' };
      }
      return next;
    });
  }, []);

  const handleSubmitOverrides = () => {
    if (Object.keys(overrides).length > 0) {
      onOverride(overrides);
    }
  };

  const overallStyle = getVerdictStyle(overallVerdict);

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-900/80">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-full bg-amber-600/20 flex items-center justify-center">
              <svg className="w-3.5 h-3.5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v17.25m0 0c-1.472 0-2.882.265-4.185.75M12 20.25c1.472 0 2.882.265 4.185.75M18.75 4.97A48.416 48.416 0 0012 4.5c-2.291 0-4.545.16-6.75.47m13.5 0c1.01.143 2.01.317 3 .52m-3-.52l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.988 5.988 0 01-2.031.352 5.988 5.988 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L18.75 4.971zm-16.5.52c.99-.203 1.99-.377 3-.52m0 0l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.989 5.989 0 01-2.031.352 5.989 5.989 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L5.25 4.971z" />
              </svg>
            </div>
            <span className="text-sm font-semibold text-amber-400">Arbitrator 裁决</span>
          </div>
          <div className="flex items-center gap-3">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium border ${overallStyle.bg} ${overallStyle.text} ${overallStyle.border}`}>
              {overallStyle.label}
            </span>
            <div className="flex items-center gap-1.5">
              <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full bg-amber-500/60 transition-all"
                  style={{ width: `${Math.round(confidence * 100)}%` }}
                />
              </div>
              <span className="text-xs text-gray-500">{Math.round(confidence * 100)}%</span>
            </div>
          </div>
        </div>
        {summary && (
          <p className="text-xs text-gray-400 mt-2 leading-relaxed">{summary}</p>
        )}
      </div>

      {/* Ruling cards */}
      <div className="p-4 space-y-3 max-h-[450px] overflow-y-auto">
        {rulings.map((ruling) => {
          const verdictStyle = getVerdictStyle(overrides[ruling.dispute_id]?.new_verdict ?? ruling.verdict);
          const sevStyle = getSeverityStyle(ruling.re_assessed_severity);
          const critical = isCritical(ruling);
          const hasOverride = ruling.dispute_id in overrides;

          return (
            <div
              key={ruling.dispute_id}
              className={`rounded-lg border p-3 transition-colors ${verdictStyle.border} ${verdictStyle.bg}`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  {critical && (
                    <svg className="w-3.5 h-3.5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
                    </svg>
                  )}
                  <div className="flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${sevStyle.dot}`} />
                    <span className={`text-xs font-medium ${sevStyle.text}`}>
                      {ruling.re_assessed_severity.toUpperCase()}
                    </span>
                  </div>
                  <span className="text-xs text-gray-600 bg-gray-50 px-1.5 py-0.5 rounded">
                    {ruling.dispute_id}
                  </span>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium border ${verdictStyle.bg} ${verdictStyle.text} ${verdictStyle.border}`}>
                  {hasOverride ? `${verdictStyle.label} (modified)` : verdictStyle.label}
                </span>
              </div>

              <p className="text-xs text-gray-400 leading-relaxed">{ruling.reasoning}</p>

              {/* Override controls */}
              {mode === 'override' && (
                <div className="flex items-center gap-2 mt-3 pt-2 border-t border-gray-200">
                  {critical ? (
                    <div className="flex items-center gap-1.5 text-xs text-red-400/70">
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
                      </svg>
                      Security redline - cannot downgrade
                    </div>
                  ) : (
                    <>
                      <button
                        onClick={() => handleOverrideAction(ruling.dispute_id, 'upgrade', overrides[ruling.dispute_id]?.new_verdict ?? ruling.verdict)}
                        className="px-2 py-1 text-xs bg-orange-900/30 text-orange-400 border border-orange-700/40 rounded hover:bg-orange-900/50 transition-colors"
                      >
                        Upgrade
                      </button>
                      <button
                        onClick={() => handleOverrideAction(ruling.dispute_id, 'downgrade', overrides[ruling.dispute_id]?.new_verdict ?? ruling.verdict)}
                        className="px-2 py-1 text-xs bg-blue-900/30 text-blue-400 border border-blue-700/40 rounded hover:bg-blue-900/50 transition-colors"
                      >
                        Downgrade
                      </button>
                      <button
                        onClick={() => handleOverrideAction(ruling.dispute_id, 'dismiss', ruling.verdict)}
                        className="px-2 py-1 text-xs bg-gray-100 text-gray-400 border border-gray-200 rounded hover:text-gray-700 transition-colors"
                      >
                        Dismiss
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Action bar */}
      <div className="px-4 py-3 border-t border-gray-200 flex items-center justify-end gap-3">
        {mode === 'view' ? (
          <>
            <button
              onClick={() => setMode('override')}
              className="px-4 py-2 text-xs font-medium text-yellow-400 bg-yellow-900/20 border border-yellow-700/40 rounded-lg hover:bg-yellow-900/40 transition-colors"
            >
              我有异议，查看详情
            </button>
            <button
              onClick={onAccept}
              className="px-4 py-2 text-xs font-medium text-green-400 bg-green-900/20 border border-green-700/40 rounded-lg hover:bg-green-900/40 transition-colors"
            >
              接受全部裁决
            </button>
          </>
        ) : (
          <>
            <button
              onClick={() => { setMode('view'); setOverrides({}); }}
              className="px-4 py-2 text-xs font-medium text-gray-400 bg-gray-100 border border-gray-200 rounded-lg hover:text-gray-700 transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleSubmitOverrides}
              disabled={Object.keys(overrides).length === 0}
              className={`px-4 py-2 text-xs font-medium rounded-lg transition-colors ${
                Object.keys(overrides).length > 0
                  ? 'text-amber-400 bg-amber-900/20 border border-amber-700/40 hover:bg-amber-900/40'
                  : 'text-gray-600 bg-gray-100 border border-gray-200 cursor-not-allowed'
              }`}
            >
              提交异议 ({Object.keys(overrides).length})
            </button>
          </>
        )}
      </div>
    </div>
  );
}
