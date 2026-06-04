import type { DebateMessage } from '../types/debate';

interface Props {
  messages: DebateMessage[];
}

export default function ConsensusIndicator({ messages }: Props) {
  const attackers = ['security', 'performance', 'correctness'];

  const latestStance: Record<string, string> = {};
  for (const msg of messages) {
    if (attackers.includes(msg.agent) && msg.structured) {
      const structured = msg.structured as Record<string, unknown>;
      if (typeof structured.stance === 'string') {
        latestStance[msg.agent] = structured.stance;
      }
    }
  }

  return (
    <div className="flex items-center gap-3">
      {attackers.map((name) => {
        const stance = latestStance[name];
        const isSatisfied = stance === 'satisfied';
        const isActive = stance !== undefined;

        return (
          <div key={name} className="flex items-center gap-1.5">
            <div
              className={`w-2 h-2 rounded-full ${
                isSatisfied
                  ? 'bg-green-400'
                  : isActive
                    ? 'bg-yellow-400 animate-pulse'
                    : 'bg-gray-600'
              }`}
            />
            <span className="text-xs text-gray-400 capitalize">{name}</span>
            {isSatisfied && (
              <span className="text-xs text-green-500">满意</span>
            )}
            {isActive && !isSatisfied && (
              <span className="text-xs text-yellow-500">攻击中</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
