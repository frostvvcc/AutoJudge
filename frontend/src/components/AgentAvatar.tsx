import { AGENT_LABELS, AGENT_DOTS } from '../types/debate';

const AGENT_RING: Record<string, string> = {
  coder: 'ring-blue-500',
  security: 'ring-red-500',
  performance: 'ring-orange-500',
  correctness: 'ring-green-500',
  judge: 'ring-purple-500',
  system: 'ring-gray-500',
};

const AGENT_TEXT: Record<string, string> = {
  coder: 'text-blue-400',
  security: 'text-red-400',
  performance: 'text-orange-400',
  correctness: 'text-green-400',
  judge: 'text-purple-400',
  system: 'text-gray-400',
};

const SIZE_MAP = {
  sm: { wrapper: 'w-6 h-6', dot: 'w-1.5 h-1.5', text: 'text-[10px]' },
  md: { wrapper: 'w-8 h-8', dot: 'w-2 h-2', text: 'text-xs' },
  lg: { wrapper: 'w-10 h-10', dot: 'w-2.5 h-2.5', text: 'text-sm' },
} as const;

interface Props {
  agent: string;
  size?: 'sm' | 'md' | 'lg';
}

export default function AgentAvatar({ agent, size = 'md' }: Props) {
  const label = AGENT_LABELS[agent] ?? agent;
  const dotClass = AGENT_DOTS[agent] ?? AGENT_DOTS.system;
  const ringClass = AGENT_RING[agent] ?? AGENT_RING.system;
  const textClass = AGENT_TEXT[agent] ?? AGENT_TEXT.system;
  const s = SIZE_MAP[size];
  const initial = label.charAt(0).toUpperCase();

  return (
    <div className="flex items-center gap-2">
      <div
        className={`${s.wrapper} rounded-full ring-2 ${ringClass} bg-gray-100 flex items-center justify-center`}
      >
        <span className={`${s.text} font-semibold ${textClass}`}>
          {initial}
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className={`${s.dot} rounded-full ${dotClass}`} />
        <span className={`${s.text} text-gray-600 font-medium`}>{label}</span>
      </div>
    </div>
  );
}
