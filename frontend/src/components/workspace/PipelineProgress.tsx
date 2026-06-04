import type { DebatePhase } from '../../types/debate';

interface Props {
  phase: DebatePhase;
  currentRound: number;
  maxRounds: number;
  statusText: string;
}

const PHASES: { key: DebatePhase; label: string }[] = [
  { key: 'plan', label: '方案设计' },
  { key: 'coding', label: '写代码' },
  { key: 'debate', label: '辩论' },
  { key: 'arbitration', label: '仲裁' },
  { key: 'fixing', label: '修复' },
  { key: 'judging', label: '报告' },
  { key: 'done', label: '完成' },
];

function phaseIndex(phase: DebatePhase): number {
  const idx = PHASES.findIndex((p) => p.key === phase);
  return idx >= 0 ? idx : 0;
}

export default function PipelineProgress({ phase, currentRound, maxRounds: _maxRounds, statusText }: Props) {
  const activeIdx = phaseIndex(phase);

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 px-4 py-3">
      <div className="flex items-center gap-1 mb-2 overflow-x-auto">
        {PHASES.map((p, i) => {
          const isCompleted = i < activeIdx;
          const isCurrent = i === activeIdx;
          let label = p.label;
          if (p.key === 'debate' && (phase === 'debate' || activeIdx > 2)) {
            label = `辩论 R${currentRound}`;
          }
          return (
            <div key={p.key} className="flex items-center">
              <div
                className={`px-2 py-1 rounded text-xs whitespace-nowrap ${
                  isCompleted
                    ? 'bg-green-500/20 text-green-400'
                    : isCurrent
                      ? 'bg-blue-500/20 text-blue-400 font-semibold'
                      : 'bg-gray-800 text-gray-600'
                }`}
              >
                {isCompleted ? '✓ ' : isCurrent ? '● ' : ''}{label}
              </div>
              {i < PHASES.length - 1 && (
                <div className={`w-4 h-px mx-0.5 ${isCompleted ? 'bg-green-500/50' : 'bg-gray-700'}`} />
              )}
            </div>
          );
        })}
      </div>
      {statusText && (
        <p className="text-xs text-gray-500">{statusText}</p>
      )}
    </div>
  );
}
