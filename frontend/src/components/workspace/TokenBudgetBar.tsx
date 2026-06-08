import type { BudgetData } from '../../types/debate';
import { PHASE_COLORS, PHASE_LABELS, AGENT_LABELS } from '../../types/debate';

interface Props {
  budget: BudgetData;
}

const PHASE_ORDER = ['plan', 'code_gen', 'debate', 'arbitration', 'judge'] as const;

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export default function TokenBudgetBar({ budget }: Props) {
  const pct = Math.min((budget.spent / Math.max(budget.total, 1)) * 100, 100);
  const isHigh = pct > 85;
  const isMid = pct > 60 && pct <= 85;

  const agentEntries = Object.entries(budget.by_agent)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6);

  const segments: Array<{ phase: string; pct: number; color: string }> = [];
  let accounted = 0;
  for (const phase of PHASE_ORDER) {
    let phaseTokens = 0;
    if (phase === 'plan') {
      phaseTokens = (budget.by_agent['planner'] ?? 0);
    } else if (phase === 'code_gen') {
      phaseTokens = (budget.by_agent['coder'] ?? 0) * 0.3;
    } else if (phase === 'debate') {
      phaseTokens =
        (budget.by_agent['security'] ?? 0) +
        (budget.by_agent['performance'] ?? 0) +
        (budget.by_agent['correctness'] ?? 0) +
        (budget.by_agent['coder'] ?? 0) * 0.7;
    } else if (phase === 'arbitration') {
      phaseTokens = (budget.by_agent['arbitrator'] ?? 0);
    } else if (phase === 'judge') {
      phaseTokens = (budget.by_agent['judge'] ?? 0);
    }
    const segPct = (phaseTokens / Math.max(budget.total, 1)) * 100;
    if (segPct > 0.3) {
      segments.push({ phase, pct: segPct, color: PHASE_COLORS[phase] ?? '#6B7280' });
      accounted += segPct;
    }
  }
  if (pct > accounted + 0.5) {
    segments.push({ phase: 'reserve', pct: pct - accounted, color: '#6B7280' });
  }

  const cacheHitRate =
    budget.cache_read > 0
      ? Math.round((budget.cache_read / (budget.cache_read + budget.cache_creation + budget.spent * 0.5)) * 100)
      : 0;

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3">
      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-500">Token 预算</span>
          {budget.agent && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-400">
              {AGENT_LABELS[budget.agent] ?? budget.agent}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs tabular-nums">
          <span className={`font-mono font-medium ${isHigh ? 'text-red-600' : isMid ? 'text-amber-600' : 'text-gray-700'}`}>
            {formatTokens(budget.spent)}
          </span>
          <span className="text-gray-400">/</span>
          <span className="font-mono text-gray-400">{formatTokens(budget.total)}</span>
          <span className={`font-medium ${isHigh ? 'text-red-500' : isMid ? 'text-amber-500' : 'text-blue-500'}`}>
            {pct.toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Phase-colored segmented progress bar */}
      <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden flex">
        {segments.map((seg) => (
          <div
            key={seg.phase}
            className="h-full transition-all duration-700 ease-out first:rounded-l-full last:rounded-r-full"
            style={{
              width: `${seg.pct}%`,
              backgroundColor: seg.color,
              minWidth: seg.pct > 0.5 ? '3px' : '0px',
            }}
            title={`${PHASE_LABELS[seg.phase] ?? seg.phase}: ${seg.pct.toFixed(1)}%`}
          />
        ))}
      </div>

      {/* Phase legend + agent breakdown */}
      <div className="mt-2 flex items-center justify-between">
        {/* Phase legend */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {PHASE_ORDER.map((phase) => {
            const hasSeg = segments.some((s) => s.phase === phase);
            if (!hasSeg) return null;
            return (
              <div key={phase} className="flex items-center gap-1">
                <div
                  className="w-2 h-2 rounded-sm"
                  style={{ backgroundColor: PHASE_COLORS[phase] }}
                />
                <span className="text-[10px] text-gray-400">
                  {PHASE_LABELS[phase] ?? phase}
                </span>
              </div>
            );
          })}
        </div>

        {/* Agent breakdown */}
        <div className="flex items-center gap-2">
          {agentEntries.map(([agent, tokens]) => (
            <span key={agent} className="text-[10px] text-gray-400 tabular-nums">
              {AGENT_LABELS[agent] ?? agent}: {formatTokens(tokens)}
            </span>
          ))}
          {cacheHitRate > 0 && (
            <span className="text-[10px] text-emerald-500 tabular-nums" title="Prompt Cache 命中率">
              cache {cacheHitRate}%
            </span>
          )}
        </div>
      </div>

      {/* Warning when budget is high */}
      {isHigh && (
        <div className="mt-1.5 text-[10px] text-red-500 flex items-center gap-1">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
          预算即将耗尽，系统可能触发仲裁或降级
        </div>
      )}
    </div>
  );
}
