import { useEffect, useState } from 'react';
import { AGENT_DOTS, AGENT_LABELS } from '../../types/debate';
import type { AgentProgressInfo } from '../../contexts/DebateContext';

interface Props {
  agentStreams: Record<string, string>;
  activeAgents: Set<string>;
  currentPhase: string;
  agentProgress: Record<string, AgentProgressInfo>;
}

const DEBATE_AGENTS = ['security', 'performance', 'correctness'] as const;
const ALL_AGENTS = ['coder', 'security', 'performance', 'correctness', 'arbitrator', 'judge'] as const;

function getPhaseDescription(agent: string, phase: string): string {
  if (agent === 'coder') {
    if (phase === 'plan') return '设计方案中';
    if (phase === 'coding') return '编写初版代码';
    if (phase === 'debate') return '回应攻击 / 修复代码';
    if (phase === 'fixing') return '修复仲裁要求';
    return '编写代码';
  }
  const map: Record<string, string> = {
    security: '审查安全漏洞',
    performance: '审查性能问题',
    correctness: '审查逻辑正确性',
    arbitrator: '仲裁未解决争议',
    judge: '生成质量报告',
  };
  return map[agent] ?? '';
}

function ElapsedTimer({ startedAt }: { startedAt: number }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const iv = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(iv);
  }, [startedAt]);
  return <span className="tabular-nums">{elapsed}s</span>;
}

function ProgressBar({ startedAt, estimatedSeconds }: { startedAt: number; estimatedSeconds: number }) {
  const [pct, setPct] = useState(0);
  useEffect(() => {
    const iv = setInterval(() => {
      const elapsed = (Date.now() - startedAt) / 1000;
      setPct(Math.min(95, (elapsed / estimatedSeconds) * 100));
    }, 500);
    return () => clearInterval(iv);
  }, [startedAt, estimatedSeconds]);
  return (
    <div className="w-full h-1 bg-gray-100 rounded-full overflow-hidden">
      <div
        className="h-full bg-blue-400 rounded-full transition-all duration-500 ease-out"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function DoneChip({ progress }: { progress: AgentProgressInfo }) {
  const secs = progress.elapsedSeconds ?? 0;
  if (progress.stance) {
    const isSatisfied = progress.stance === 'satisfied';
    const count = progress.findingsCount ?? 0;
    return (
      <div className="flex items-center gap-1.5">
        <span className={`text-[10px] font-medium ${isSatisfied ? 'text-green-600' : 'text-orange-600'}`}>
          {isSatisfied ? '✓ 通过' : `${count} 个问题`}
        </span>
        <span className="text-[10px] text-gray-400">{secs}s</span>
      </div>
    );
  }
  if (progress.hasCode !== undefined) {
    return (
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] font-medium text-blue-600">
          {progress.hasCode ? `✓ ${progress.codeLines} 行代码` : '⚠ 未产出代码'}
        </span>
        <span className="text-[10px] text-gray-400">{secs}s</span>
      </div>
    );
  }
  return <span className="text-[10px] text-gray-400">✓ {secs}s</span>;
}

function AgentSlot({
  agent,
  isActive,
  progress,
  phase,
  compact,
}: {
  agent: string;
  isActive: boolean;
  progress?: AgentProgressInfo;
  phase: string;
  compact?: boolean;
}) {
  const dotClass = AGENT_DOTS[agent] ?? 'bg-gray-400';
  const label = AGENT_LABELS[agent] ?? agent;
  const desc = getPhaseDescription(agent, phase);
  const isDone = progress?.status === 'done';

  if (!isActive && !isDone) {
    return (
      <div className={`rounded-lg border border-dashed border-gray-200 bg-gray-50/50 ${compact ? 'p-2.5' : 'p-3'}`}>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-gray-200" />
          <span className="text-xs text-gray-300">{label}</span>
          <span className="text-[10px] text-gray-300 ml-auto">等待中</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`rounded-lg border transition-all duration-300 ${
      isDone
        ? 'border-green-200 bg-green-50/50'
        : 'border-blue-200 bg-white shadow-sm'
    } ${compact ? 'p-2.5' : 'p-3'}`}>
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full transition-all ${
          isDone ? 'bg-green-400' : `${dotClass} animate-pulse`
        }`} />
        <span className={`text-xs font-semibold ${isDone ? 'text-green-700' : 'text-gray-800'}`}>
          {label}
        </span>
        <span className="text-[10px] text-gray-400">{desc}</span>
        <div className="ml-auto">
          {isDone && progress ? (
            <DoneChip progress={progress} />
          ) : progress ? (
            <div className="flex items-center gap-1">
              <span className="text-[10px] text-blue-500">
                <ElapsedTimer startedAt={progress.startedAt} />
              </span>
              <span className="text-[10px] text-gray-300">/ ~{progress.estimatedSeconds}s</span>
            </div>
          ) : null}
        </div>
      </div>
      {isActive && progress && !isDone && (
        <div className="mt-2">
          <ProgressBar startedAt={progress.startedAt} estimatedSeconds={progress.estimatedSeconds} />
        </div>
      )}
    </div>
  );
}

export default function AgentLivePanel({
  agentStreams,
  activeAgents,
  currentPhase,
  agentProgress,
}: Props) {
  const hasAnyActive = activeAgents.size > 0;
  const hasAnyProgress = Object.keys(agentProgress).length > 0;
  if (!hasAnyActive && !hasAnyProgress && Object.keys(agentStreams).length === 0) return null;

  const isDebate = currentPhase === 'debate';
  const debateActive = DEBATE_AGENTS.some((a) => activeAgents.has(a) || agentProgress[a]);
  const singleAgent = !isDebate || !debateActive;

  if (singleAgent) {
    const activeAgent = ALL_AGENTS.find((a) => activeAgents.has(a) || agentProgress[a]?.status === 'working');
    if (!activeAgent) return null;
    return (
      <AgentSlot
        agent={activeAgent}
        isActive={activeAgents.has(activeAgent)}
        progress={agentProgress[activeAgent]}
        phase={currentPhase}
      />
    );
  }

  const doneCount = DEBATE_AGENTS.filter((a) => agentProgress[a]?.status === 'done').length;
  const workingCount = DEBATE_AGENTS.filter((a) => activeAgents.has(a)).length;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 px-1">
        <span className="text-xs font-medium text-gray-500">Agent 审查进度</span>
        <span className="text-[10px] text-gray-400">
          {doneCount > 0 && `${doneCount}/3 完成`}
          {doneCount > 0 && workingCount > 0 && ' · '}
          {workingCount > 0 && `${workingCount} 个进行中`}
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        {DEBATE_AGENTS.map((agent) => (
          <AgentSlot
            key={agent}
            agent={agent}
            isActive={activeAgents.has(agent)}
            progress={agentProgress[agent]}
            phase={currentPhase}
            compact
          />
        ))}
      </div>
      {(activeAgents.has('coder') || agentProgress['coder']?.status === 'working') && (
        <AgentSlot
          agent="coder"
          isActive={activeAgents.has('coder')}
          progress={agentProgress['coder']}
          phase={currentPhase}
        />
      )}
    </div>
  );
}
