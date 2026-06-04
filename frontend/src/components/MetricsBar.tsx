import type { DebateMetrics } from '../types/debate';

interface Props {
  metrics: DebateMetrics;
}

export default function MetricsBar({ metrics }: Props) {
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <h3 className="text-sm font-medium text-gray-400 mb-3">指标</h3>
      <div className="grid grid-cols-2 gap-3">
        <MetricItem
          label="轮次"
          value={String(metrics.total_rounds)}
        />
        <MetricItem
          label="Token"
          value={`${(metrics.total_tokens / 1000).toFixed(1)}k`}
        />
        <MetricItem
          label="耗时"
          value={`${(metrics.total_latency_ms / 1000).toFixed(1)}s`}
        />
        <MetricItem
          label="费用"
          value={`$${metrics.cost_usd.toFixed(2)}`}
        />
      </div>
    </div>
  );
}

function MetricItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-800/50 rounded px-3 py-2">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-sm font-medium text-gray-200">{value}</div>
    </div>
  );
}
