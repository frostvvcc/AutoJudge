import { AGENT_DOTS, AGENT_LABELS } from '../../types/debate';

interface Props {
  activeAgents: Set<string>;
}

const AGENTS = ['coder', 'security', 'performance', 'correctness', 'arbitrator', 'judge'];

export default function AgentStatusBar({ activeAgents }: Props) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      {AGENTS.map((name) => {
        const isActive = activeAgents.has(name);
        const dotClass = AGENT_DOTS[name] ?? 'bg-gray-500';
        return (
          <div key={name} className="flex items-center gap-1.5">
            <div
              className={`w-2.5 h-2.5 rounded-full transition-all ${
                isActive ? `${dotClass} animate-pulse scale-110` : 'bg-gray-300'
              }`}
            />
            <span className={`text-xs ${isActive ? 'text-gray-800 font-medium' : 'text-gray-500'}`}>
              {AGENT_LABELS[name] ?? name}
            </span>
          </div>
        );
      })}
    </div>
  );
}
