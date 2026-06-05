import type { DebatePhase } from '../../types/debate';

interface Props {
  phase: DebatePhase;
  currentRound: number;
  maxRounds: number;
  statusText: string;
}

const PHASES: { key: DebatePhase; label: string; icon: string }[] = [
  { key: 'plan', label: '方案', icon: '\u{1F4A1}' },
  { key: 'coding', label: '编码', icon: '\u{1F4BB}' },
  { key: 'debate', label: '辩论', icon: '\u{2694}' },
  { key: 'arbitration', label: '仲裁', icon: '\u{2696}' },
  { key: 'fixing', label: '修复', icon: '\u{1F527}' },
  { key: 'judging', label: '报告', icon: '\u{1F4CB}' },
  { key: 'done', label: '完成', icon: '✓' },
];

function phaseIndex(phase: DebatePhase): number {
  const idx = PHASES.findIndex((p) => p.key === phase);
  return idx >= 0 ? idx : 0;
}

export default function PipelineProgress({ phase, currentRound, maxRounds: _maxRounds, statusText }: Props) {
  const activeIdx = phase === 'idle' ? -1 : phaseIndex(phase);

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-0.5">
        {PHASES.map((p, i) => {
          const isCompleted = i < activeIdx;
          const isCurrent = i === activeIdx;
          let label = p.label;
          if (p.key === 'debate' && (phase === 'debate' || activeIdx > 2)) {
            label = `R${currentRound}`;
          }
          return (
            <div key={p.key} className="flex items-center">
              <div
                className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-all ${
                  isCompleted
                    ? 'bg-green-500/15 text-green-400'
                    : isCurrent
                      ? 'bg-blue-500/15 text-blue-400 ring-1 ring-blue-500/30'
                      : 'text-gray-600'
                }`}
              >
                {isCompleted ? (
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                ) : isCurrent ? (
                  <div className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                ) : null}
                {label}
              </div>
              {i < PHASES.length - 1 && (
                <div className={`w-3 h-px mx-0.5 ${isCompleted ? 'bg-green-500/40' : 'bg-gray-800'}`} />
              )}
            </div>
          );
        })}
      </div>
      {statusText && (
        <span className="text-xs text-gray-500 truncate ml-2 hidden sm:inline">{statusText}</span>
      )}
    </div>
  );
}
