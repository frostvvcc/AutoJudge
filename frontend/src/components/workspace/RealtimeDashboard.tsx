import type { DebateMessage, RiskAssessment, DebateMetrics } from '../../types/debate';

interface Props {
  messages: DebateMessage[];
  risk?: RiskAssessment;
  metrics?: DebateMetrics;
}

const RISK_LABEL: Record<string, string> = {
  none: '无风险',
  low: '低风险',
  medium: '中风险',
  high: '高风险',
  critical: '严重',
  unknown: '未知',
};

const RISK_COLOR: Record<string, string> = {
  none: 'text-green-400',
  low: 'text-green-400',
  medium: 'text-yellow-400',
  high: 'text-orange-400',
  critical: 'text-red-400',
  unknown: 'text-gray-500',
};

export default function RealtimeDashboard({ messages, risk, metrics }: Props) {
  const attackers = ['security', 'performance', 'correctness'];

  const attackerStats: Record<string, { findings: number; fixed: number; stance: string }> = {};
  for (const name of attackers) {
    attackerStats[name] = { findings: 0, fixed: 0, stance: 'idle' };
  }

  for (const msg of messages) {
    if (attackers.includes(msg.agent) && msg.structured) {
      const s = msg.structured as Record<string, unknown>;
      const rawFindings = s.findings;
      const findings = Array.isArray(rawFindings) ? rawFindings : [];
      attackerStats[msg.agent].findings += findings.length;
      if (typeof s.stance === 'string') {
        attackerStats[msg.agent].stance = s.stance;
      }
    }
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-4">
      <h3 className="text-sm font-medium text-gray-400">实时状态</h3>

      {/* Attacker status */}
      <div className="space-y-2">
        {attackers.map((name) => {
          const stat = attackerStats[name];
          const isSatisfied = stat.stance === 'satisfied';
          return (
            <div key={name} className="flex items-center justify-between text-xs">
              <span className="text-gray-400 capitalize w-20">{name}</span>
              <span className="text-gray-500">{stat.findings} 发现</span>
              <span className={isSatisfied ? 'text-green-400' : stat.stance === 'attacking' ? 'text-yellow-400' : 'text-gray-600'}>
                {isSatisfied ? '✓ 满意' : stat.stance === 'attacking' ? '攻击中' : '等待中'}
              </span>
            </div>
          );
        })}
      </div>

      {/* Risk assessment */}
      {risk && (
        <div className="space-y-2 pt-2 border-t border-gray-200">
          <h4 className="text-xs text-gray-500">风险评级</h4>
          {(['security', 'performance', 'correctness'] as const).map((dim) => {
            const level = risk[dim] || 'unknown';
            return (
              <div key={dim} className="flex items-center justify-between text-xs">
                <span className="text-gray-400 capitalize w-16">{dim === 'security' ? '安全' : dim === 'performance' ? '性能' : '正确'}</span>
                <span className={RISK_COLOR[level]}>{RISK_LABEL[level]}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Metrics */}
      {metrics && (
        <div className="grid grid-cols-2 gap-2 pt-2 border-t border-gray-200">
          <div className="bg-gray-50 rounded px-2 py-1.5">
            <div className="text-xs text-gray-500">轮次</div>
            <div className="text-sm font-medium text-gray-700">{metrics.total_rounds}</div>
          </div>
          <div className="bg-gray-50 rounded px-2 py-1.5">
            <div className="text-xs text-gray-500">Token</div>
            <div className="text-sm font-medium text-gray-700">{(metrics.total_tokens / 1000).toFixed(1)}k</div>
          </div>
          <div className="bg-gray-50 rounded px-2 py-1.5">
            <div className="text-xs text-gray-500">耗时</div>
            <div className="text-sm font-medium text-gray-700">{(metrics.total_latency_ms / 1000).toFixed(1)}s</div>
          </div>
          <div className="bg-gray-50 rounded px-2 py-1.5">
            <div className="text-xs text-gray-500">费用</div>
            <div className="text-sm font-medium text-gray-700">${metrics.cost_usd.toFixed(2)}</div>
          </div>
        </div>
      )}
    </div>
  );
}
