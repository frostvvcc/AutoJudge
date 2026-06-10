import { useEffect, useState } from 'react';
import type { DebatePhase } from '../../types/debate';
import { AGENT_DOTS } from '../../types/debate';

interface Props {
  phase: DebatePhase;
  currentRound: number;
  maxRounds: number;
  statusText: string;
  activeAgents: Set<string>;
  elapsedMs: number;
  selectedPhase: string | null;
  onSelectPhase: (phase: string) => void;
  visitedPhases: Set<string>;
}

const PHASES: { key: string; label: string; icon: string }[] = [
  { key: 'analysis', label: '需求分析', icon: '🧠' },
  { key: 'plan', label: '方案设计', icon: '💡' },
  { key: 'coding', label: '编码', icon: '⌨️' },
  { key: 'debate', label: '辩论', icon: '⚔️' },
  { key: 'arbitration', label: '仲裁', icon: '⚖️' },
  { key: 'fixing', label: '修复', icon: '🔧' },
  { key: 'judging', label: '评审', icon: '📋' },
  { key: 'user_decision', label: '用户决策', icon: '🤔' },
  { key: 'done', label: '完成', icon: '✅' },
];

function phaseIndex(phase: string): number {
  const idx = PHASES.findIndex((p) => p.key === phase);
  return idx >= 0 ? idx : 0;
}

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}m ${rem}s`;
}

const DEBATE_AGENTS = [
  { key: 'security', label: 'Security', color: 'text-red-500' },
  { key: 'performance', label: 'Performance', color: 'text-orange-500' },
  { key: 'correctness', label: 'Correctness', color: 'text-green-500' },
];

export default function PipelineProgress({
  phase,
  currentRound,
  maxRounds,
  statusText,
  activeAgents,
  elapsedMs,
  selectedPhase,
  onSelectPhase,
  visitedPhases,
}: Props) {
  const isError = phase === 'error';
  const activeIdx = phase === 'idle' || isError ? -1 : phaseIndex(phase);

  const [dots, setDots] = useState('');
  useEffect(() => {
    if (phase === 'idle' || phase === 'done' || phase === 'error') return;
    const id = setInterval(() => setDots((p) => (p.length >= 3 ? '' : p + '.')), 400);
    return () => clearInterval(id);
  }, [phase]);

  const isRunning = phase !== 'idle' && phase !== 'done' && phase !== 'error';

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      {/* Phase bar */}
      <div className="flex items-center px-4 py-3 gap-0.5 overflow-x-auto">
        {PHASES.map((p, i) => {
          const isPast = !isError && i < activeIdx;
          const isCurrent = !isError && i === activeIdx;
          const wasVisited = visitedPhases.has(p.key);
          const isCompleted = isPast && wasVisited;
          const isSkipped = isPast && !wasVisited;
          const isSelected = selectedPhase === p.key || (selectedPhase === null && isCurrent);
          const isClickable = isCompleted || isCurrent;

          let label = p.label;
          if (p.key === 'debate' && currentRound > 0) {
            label = `辩论 R${currentRound}`;
          }

          let icon: string | null = null;
          let badge: string | null = null;
          let style = 'bg-gray-50 text-gray-400 cursor-default';
          if (isCompleted) {
            icon = '✓';
            style = 'bg-green-50 text-green-700 hover:bg-green-100 cursor-pointer';
          } else if (isSkipped) {
            badge = '跳过';
            style = 'bg-gray-50 text-gray-400 cursor-default';
          } else if (isCurrent) {
            icon = p.icon;
            style = 'bg-blue-50 text-blue-700 cursor-pointer';
          }

          return (
            <div key={p.key} className="flex items-center">
              <button
                onClick={() => isClickable && onSelectPhase(p.key)}
                disabled={!isClickable}
                className={`
                  relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                  transition-all duration-300 whitespace-nowrap
                  ${isSelected ? 'ring-2 ring-blue-400 ring-offset-1' : ''}
                  ${style}
                `}
              >
                {icon && <span className="text-sm">{icon}</span>}
                {label}
                {badge && <span className="text-[9px] text-gray-400 ml-0.5">({badge})</span>}
                {isCurrent && isRunning && (
                  <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-blue-500 animate-ping" />
                )}
              </button>
              {i < PHASES.length - 1 && (
                <div className={`w-5 h-0.5 mx-0.5 rounded transition-colors duration-500 ${
                  isCompleted ? 'bg-green-300' : isSkipped ? 'bg-gray-200' : 'bg-gray-200'
                }`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Status bar: sub-steps + status text + elapsed */}
      {(isRunning || isError) && (
        <div className="px-4 py-2.5 bg-gray-50 border-t border-gray-100">
          <div className="flex items-center justify-between gap-4">
            {/* Left: sub-step indicators */}
            <div className="flex items-center gap-4 min-w-0 flex-1">
              {/* Agent activity dots for debate phase */}
              {phase === 'debate' && (
                <div className="flex items-center gap-3">
                  {DEBATE_AGENTS.map((agent) => {
                    const isActive = activeAgents.has(agent.key);
                    const dotCls = AGENT_DOTS[agent.key] ?? 'bg-gray-400';
                    return (
                      <div key={agent.key} className="flex items-center gap-1.5">
                        <div className={`w-2 h-2 rounded-full transition-all duration-300 ${
                          isActive ? `${dotCls} animate-pulse scale-125` : 'bg-gray-300'
                        }`} />
                        <span className={`text-xs transition-colors ${
                          isActive ? `${agent.color} font-medium` : 'text-gray-400'
                        }`}>
                          {agent.label}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Coder indicator for coding/fixing phase */}
              {(phase === 'coding' || phase === 'fixing') && activeAgents.has('coder') && (
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                  <span className="text-xs text-blue-600 font-medium">Coder</span>
                </div>
              )}

              {/* Judge indicator */}
              {phase === 'judging' && (
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-purple-500 animate-pulse" />
                  <span className="text-xs text-purple-600 font-medium">Judge</span>
                </div>
              )}

              {/* Status text */}
              <span className="text-xs text-gray-500 truncate">
                {statusText}{isRunning ? dots : ''}
              </span>
            </div>

            {/* Right: elapsed time + round info */}
            <div className="flex items-center gap-3 shrink-0">
              {currentRound > 0 && (
                <span className="text-xs text-gray-400">
                  {currentRound}/{maxRounds} 轮
                </span>
              )}
              {elapsedMs > 0 && (
                <span className="text-xs font-mono text-gray-400 tabular-nums">
                  {formatElapsed(elapsedMs)}
                </span>
              )}
              {isRunning && (
                <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
              )}
            </div>
          </div>

          {/* Elapsed time is shown above — no fake percentage progress bar */}
        </div>
      )}

      {isError && (
        <div className="px-4 py-2 bg-red-50 border-t border-red-100">
          <p className="text-xs text-red-600 font-medium">{statusText || '任务异常终止'}</p>
        </div>
      )}
    </div>
  );
}
