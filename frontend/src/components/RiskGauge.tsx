import type { RiskAssessment } from '../types/debate';

interface Props {
  risk: RiskAssessment;
}

const RISK_COLORS: Record<string, string> = {
  none: 'text-green-400',
  low: 'text-green-400',
  medium: 'text-yellow-400',
  high: 'text-orange-400',
  critical: 'text-red-400',
  unknown: 'text-gray-500',
};

const RISK_BG: Record<string, string> = {
  none: 'bg-green-500/20',
  low: 'bg-green-500/20',
  medium: 'bg-yellow-500/20',
  high: 'bg-orange-500/20',
  critical: 'bg-red-500/20',
  unknown: 'bg-gray-500/20',
};

export default function RiskGauge({ risk }: Props) {
  const dimensions = [
    { key: 'security', label: '安全', icon: '🔒' },
    { key: 'performance', label: '性能', icon: '⚡' },
    { key: 'correctness', label: '正确', icon: '✓' },
  ] as const;

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <h3 className="text-sm font-medium text-gray-400 mb-3">风险评级</h3>
      <div className="space-y-2">
        {dimensions.map(({ key, label, icon }) => {
          const level = risk[key] || 'unknown';
          return (
            <div
              key={key}
              className={`flex items-center justify-between px-3 py-2 rounded ${RISK_BG[level]}`}
            >
              <span className="text-sm text-gray-300">
                {icon} {label}
              </span>
              <span className={`text-sm font-medium ${RISK_COLORS[level]}`}>
                {level}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
