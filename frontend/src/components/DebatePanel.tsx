import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import type { DebateMessage, DebateStatus } from '../types/debate';
import { AGENT_COLORS, AGENT_LABELS, AGENT_DOTS } from '../types/debate';

interface Props {
  messages: DebateMessage[];
  currentRound: number;
  status: DebateStatus;
  statusText?: string;
}

export default function DebatePanel({ messages, currentRound, status, statusText }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  const groupedByRound = messages.reduce<Record<number, DebateMessage[]>>(
    (acc, msg) => {
      const round = msg.round ?? 0;
      if (!acc[round]) acc[round] = [];
      acc[round].push(msg);
      return acc;
    },
    {},
  );

  return (
    <div className="bg-white rounded-lg border border-gray-200 max-h-[600px] overflow-y-auto">
      <div className="p-4 space-y-4">
        {Object.entries(groupedByRound).map(([round, msgs]) => (
          <div key={round}>
            <div className="flex items-center gap-2 mb-3">
              <div className="h-px flex-1 bg-gray-100" />
              <span className="text-xs text-gray-500 font-medium">
                Round {round}
              </span>
              <div className="h-px flex-1 bg-gray-100" />
            </div>

            <div className="space-y-3">
              {msgs.map((msg, i) => (
                <MessageBubble key={`${round}-${i}`} message={msg} />
              ))}
            </div>
          </div>
        ))}

        {status === 'running' && (
          <div className="flex items-center gap-2 text-gray-500 text-sm">
            <div className="flex gap-1">
              <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            {statusText || '分析中...'}
          </div>
        )}

        {status === 'converged' && (
          <div className="text-center py-3">
            <span className="text-green-400 text-sm font-medium">
              共识达成 ({currentRound} 轮)
            </span>
          </div>
        )}

        <div ref={scrollRef} />
      </div>
    </div>
  );
}

const COLLAPSE_THRESHOLD = 400;

function MessageBubble({ message }: { message: DebateMessage }) {
  const { agent, content } = message;
  const [expanded, setExpanded] = useState(false);
  const isLong = content.length > COLLAPSE_THRESHOLD;

  const colorClass = AGENT_COLORS[agent] ?? AGENT_COLORS.system;
  const dotClass = AGENT_DOTS[agent] ?? AGENT_DOTS.system;
  const label = AGENT_LABELS[agent] ?? agent;

  const isRebuttal = content.includes('rebut_with_evidence') || content.includes('反驳');
  const isCrossReview = content.startsWith('[交叉审阅]');

  return (
    <div className={`border-l-2 ${colorClass} rounded-r-lg p-3`}>
      <div className="flex items-center gap-2 mb-1.5">
        <div className={`w-2 h-2 rounded-full ${dotClass}`} />
        <span className="text-xs font-semibold text-gray-600">{label}</span>
        {isRebuttal && (
          <span className="text-xs px-1.5 py-0.5 bg-yellow-900/50 text-yellow-400 rounded">
            反驳
          </span>
        )}
        {isCrossReview && (
          <span className="text-xs px-1.5 py-0.5 bg-purple-900/50 text-purple-400 rounded">
            交叉审阅
          </span>
        )}
      </div>
      <div
        className={`text-sm text-gray-600 leading-relaxed prose prose-sm max-w-none ${
          isLong && !expanded ? 'max-h-[200px] overflow-hidden relative' : ''
        }`}
      >
        <ReactMarkdown>{content}</ReactMarkdown>
        {isLong && !expanded && (
          <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-gray-100/90 to-transparent" />
        )}
      </div>
      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-1 text-xs text-blue-400 hover:text-blue-300"
        >
          {expanded ? '收起' : '展开全文'}
        </button>
      )}
    </div>
  );
}
