import type { BudgetData } from '../../types/debate';
import { AGENT_LABELS } from '../../types/debate';

interface Props {
  budget: BudgetData;
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export default function TokenBudgetBar({ budget }: Props) {
  const agentEntries = Object.entries(budget.by_agent ?? {})
    .filter(([, v]) => v > 0)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);

  return (
    <div className="flex items-center gap-4 px-4 py-2 bg-white rounded-lg border border-gray-100 text-xs text-gray-500">
      <span className="font-medium text-gray-700">
        已消耗 <span className="font-mono text-blue-600">{formatTokens(budget.spent)}</span> tokens
      </span>
      {agentEntries.length > 0 && (
        <>
          <span className="text-gray-300">|</span>
          {agentEntries.map(([agent, tokens]) => (
            <span key={agent} className="tabular-nums">
              {AGENT_LABELS[agent] ?? agent}: {formatTokens(tokens)}
            </span>
          ))}
        </>
      )}
      {budget.cache_read > 0 && (
        <>
          <span className="text-gray-300">|</span>
          <span className="text-emerald-500">cache 命中 {formatTokens(budget.cache_read)}</span>
        </>
      )}
    </div>
  );
}
