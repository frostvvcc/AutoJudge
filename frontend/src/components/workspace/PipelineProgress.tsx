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
  { key: 'judging', label: '评审' },
  { key: 'user_decision', label: '用户确认' },
  { key: 'done', label: '完成' },
];

function phaseIndex(phase: DebatePhase): number {
  const idx = PHASES.findIndex((p) => p.key === phase);
  return idx >= 0 ? idx : 0;
}

export default function PipelineProgress({ phase, currentRound, maxRounds: _maxRounds, statusText }: Props) {
  const isError = phase === 'error';
  const activeIdx = phase === 'idle' || isError ? -1 : phaseIndex(phase);

  return (
    <div className="bg-white rounded-lg border border-gray-200 px-4 py-3">
      <div className="flex items-center gap-1 mb-2 overflow-x-auto">
        {PHASES.map((p, i) => {
          const isCompleted = !isError && i < activeIdx;
          const isCurrent = !isError && i === activeIdx;
          let label = p.label;
          if (p.key === 'debate' && (phase === 'debate' || activeIdx > 2)) {
            label = `辩论 R${currentRound}`;
          }
          return (
            <div key={p.key} className="flex items-center">
              <div
                className={`px-2 py-1 rounded text-xs whitespace-nowrap ${
                  isCompleted
                    ? 'bg-green-50 text-green-600'
                    : isCurrent
                      ? 'bg-blue-50 text-blue-600 font-semibold'
                      : 'bg-gray-100 text-gray-500'
                }`}
              >
                {isCompleted ? '✓ ' : isCurrent ? '● ' : ''}{label}
              </div>
              {i < PHASES.length - 1 && (
                <div className={`w-4 h-px mx-0.5 ${isCompleted ? 'bg-green-300' : 'bg-gray-200'}`} />
              )}
            </div>
          );
        })}
      </div>
      {isError && (
        <p className="text-xs text-red-500 font-medium">{statusText || '任务异常终止'}</p>
      )}
      {!isError && statusText && (
        <p className="text-xs text-gray-500">{statusText}</p>
      )}
    </div>
  );
}
