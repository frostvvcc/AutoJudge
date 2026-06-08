import { useEffect, useRef } from 'react';
import { AGENT_DOTS, AGENT_LABELS } from '../../types/debate';

interface Props {
  agentStreams: Record<string, string>;
  activeAgents: Set<string>;
  currentPhase: string;
}

const DEBATE_AGENTS = ['security', 'performance', 'correctness'] as const;
const ALL_AGENTS = ['coder', 'security', 'performance', 'correctness', 'arbitrator', 'judge'] as const;

const AGENT_DESCRIPTIONS: Record<string, string> = {
  coder: '编写代码 / 回应攻击',
  security: '审查安全漏洞',
  performance: '审查性能问题',
  correctness: '审查逻辑正确性',
  arbitrator: '仲裁未解决争议',
  judge: '生成质量报告',
};

function StreamSlot({
  agent,
  text,
  isActive,
  compact,
}: {
  agent: string;
  text: string;
  isActive: boolean;
  compact?: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [text]);

  const dotClass = AGENT_DOTS[agent] ?? 'bg-gray-400';
  const label = AGENT_LABELS[agent] ?? agent;
  const desc = AGENT_DESCRIPTIONS[agent] ?? '';

  if (!isActive && !text) return null;

  return (
    <div
      className={`rounded-lg border transition-all duration-300 ${
        isActive
          ? 'border-gray-300 bg-white shadow-sm'
          : 'border-gray-100 bg-gray-50 opacity-60'
      } ${compact ? 'p-2.5' : 'p-3'}`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-1.5">
        <div
          className={`w-2 h-2 rounded-full transition-all ${
            isActive ? `${dotClass} animate-pulse` : 'bg-gray-300'
          }`}
        />
        <span className={`text-xs font-semibold ${isActive ? 'text-gray-800' : 'text-gray-400'}`}>
          {label}
        </span>
        {isActive && (
          <span className="text-[10px] text-gray-400">{desc}</span>
        )}
        {isActive && !text && (
          <div className="ml-auto flex items-center gap-1">
            <span className="text-[10px] text-gray-400">思考中</span>
            <div className="flex gap-0.5">
              <div className="w-1 h-1 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-1 h-1 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-1 h-1 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
      </div>

      {/* Stream content */}
      {(text || isActive) && (
        <div
          ref={scrollRef}
          className={`text-xs text-gray-600 leading-relaxed whitespace-pre-wrap overflow-y-auto font-mono ${
            compact ? 'max-h-[120px]' : 'max-h-[180px]'
          }`}
        >
          {text || (
            <span className="text-gray-300 italic">等待输出...</span>
          )}
          {isActive && text && (
            <span className="inline-block w-1.5 h-3.5 bg-blue-500 animate-pulse ml-0.5 align-middle" />
          )}
        </div>
      )}
    </div>
  );
}

export default function AgentLivePanel({
  agentStreams,
  activeAgents,
  currentPhase,
}: Props) {
  const hasAnyActive = activeAgents.size > 0;
  if (!hasAnyActive && Object.keys(agentStreams).length === 0) return null;

  const isDebate = currentPhase === 'debate';
  const debateActive = DEBATE_AGENTS.some((a) => activeAgents.has(a) || agentStreams[a]);
  const singleAgent = !isDebate || !debateActive;

  if (singleAgent) {
    const activeAgent = ALL_AGENTS.find((a) => activeAgents.has(a) || agentStreams[a]);
    if (!activeAgent) return null;
    return (
      <StreamSlot
        agent={activeAgent}
        text={agentStreams[activeAgent] ?? ''}
        isActive={activeAgents.has(activeAgent)}
      />
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 px-1">
        <span className="text-xs font-medium text-gray-500">Agent 实时输出</span>
        <span className="text-[10px] text-gray-400">
          {activeAgents.size} 个 Agent 并行工作中
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        {DEBATE_AGENTS.map((agent) => {
          const isActive = activeAgents.has(agent);
          const text = agentStreams[agent] ?? '';
          if (!isActive && !text) {
            return (
              <div key={agent} className="rounded-lg border border-dashed border-gray-200 bg-gray-50/50 p-2.5">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-gray-200" />
                  <span className="text-xs text-gray-300">{AGENT_LABELS[agent]}</span>
                  <span className="text-[10px] text-gray-300 ml-auto">等待中</span>
                </div>
              </div>
            );
          }
          return (
            <StreamSlot
              key={agent}
              agent={agent}
              text={text}
              isActive={isActive}
              compact
            />
          );
        })}
      </div>
      {/* Coder stream if active during debate */}
      {(activeAgents.has('coder') || agentStreams['coder']) && (
        <StreamSlot
          agent="coder"
          text={agentStreams['coder'] ?? ''}
          isActive={activeAgents.has('coder')}
        />
      )}
    </div>
  );
}
