import { useEffect, useRef } from 'react';
import type { DebateMessage, DebateStatus, StreamingAgent } from '../types/debate';
import { AGENT_COLORS, AGENT_LABELS, AGENT_DOTS } from '../types/debate';

interface Props {
  messages: DebateMessage[];
  currentRound: number;
  status: DebateStatus;
  streamingAgents: Record<string, StreamingAgent>;
}

export default function DebatePanel({
  messages,
  currentRound,
  status,
  streamingAgents,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, streamingAgents]);

  const groupedByRound = messages.reduce<Record<number, DebateMessage[]>>(
    (acc, msg) => {
      const round = msg.round ?? 0;
      if (!acc[round]) acc[round] = [];
      acc[round].push(msg);
      return acc;
    },
    {},
  );

  const streamingEntries = Object.entries(streamingAgents);

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 max-h-[600px] overflow-y-auto">
      <div className="p-4 space-y-4">
        {Object.entries(groupedByRound).map(([round, msgs]) => (
          <div key={round}>
            <div className="flex items-center gap-2 mb-3">
              <div className="h-px flex-1 bg-gray-800" />
              <span className="text-xs text-gray-500 font-medium">
                Round {round}
              </span>
              <div className="h-px flex-1 bg-gray-800" />
            </div>

            <div className="space-y-3">
              {msgs.map((msg, i) => (
                <MessageBubble key={`${round}-${i}`} message={msg} />
              ))}
            </div>
          </div>
        ))}

        {/* Streaming agents — shown below completed messages */}
        {streamingEntries.length > 0 && (
          <div>
            {currentRound > 0 && !groupedByRound[currentRound] && (
              <div className="flex items-center gap-2 mb-3">
                <div className="h-px flex-1 bg-gray-800" />
                <span className="text-xs text-gray-500 font-medium">
                  Round {currentRound}
                </span>
                <div className="h-px flex-1 bg-gray-800" />
              </div>
            )}

            <div className="space-y-3">
              {streamingEntries.map(([agent, data]) => (
                <StreamingBubble
                  key={`streaming-${agent}`}
                  agent={agent}
                  content={data.content}
                />
              ))}
            </div>
          </div>
        )}

        {status === 'running' && streamingEntries.length === 0 && (
          <div className="flex items-center gap-2 text-gray-500 text-sm">
            <div className="flex gap-1">
              <div
                className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce"
                style={{ animationDelay: '0ms' }}
              />
              <div
                className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce"
                style={{ animationDelay: '150ms' }}
              />
              <div
                className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce"
                style={{ animationDelay: '300ms' }}
              />
            </div>
            分析中...
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

function MessageBubble({ message }: { message: DebateMessage }) {
  const { agent, content } = message;
  const colorClass = AGENT_COLORS[agent] ?? AGENT_COLORS.system;
  const dotClass = AGENT_DOTS[agent] ?? AGENT_DOTS.system;
  const label = AGENT_LABELS[agent] ?? agent;

  const isRebuttal =
    content.includes('rebut_with_evidence') || content.includes('反驳');
  const isCrossReview = content.startsWith('[交叉审阅]');

  return (
    <div className={`border-l-2 ${colorClass} rounded-r-lg p-3`}>
      <div className="flex items-center gap-2 mb-1.5">
        <div className={`w-2 h-2 rounded-full ${dotClass}`} />
        <span className="text-xs font-semibold text-gray-300">{label}</span>
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
      <div className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">
        {content}
      </div>
    </div>
  );
}

function StreamingBubble({
  agent,
  content,
}: {
  agent: string;
  content: string;
}) {
  const colorClass = AGENT_COLORS[agent] ?? AGENT_COLORS.system;
  const dotClass = AGENT_DOTS[agent] ?? AGENT_DOTS.system;
  const label = AGENT_LABELS[agent] ?? agent;

  return (
    <div className={`border-l-2 ${colorClass} rounded-r-lg p-3`}>
      <div className="flex items-center gap-2 mb-1.5">
        <div className={`w-2 h-2 rounded-full ${dotClass} animate-pulse`} />
        <span className="text-xs font-semibold text-gray-300">{label}</span>
        <span className="text-xs px-1.5 py-0.5 bg-blue-900/50 text-blue-400 rounded animate-pulse">
          生成中
        </span>
      </div>
      <div className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">
        {content || '...'}
        <span className="inline-block w-1.5 h-4 bg-blue-400 rounded-sm ml-0.5 animate-blink align-middle" />
      </div>
    </div>
  );
}
