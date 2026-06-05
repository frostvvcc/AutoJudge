import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import type { DebateMessage } from '../../types/debate';
import PlanDisplayCard from './PlanDisplayCard';

interface Props {
  messages: DebateMessage[];
  currentRound: number;
}

const AGENT_META: Record<string, { label: string; color: string; bgColor: string; icon: string }> = {
  coder: {
    label: 'Coder',
    color: 'text-blue-400',
    bgColor: 'bg-blue-500',
    icon: '< >',
  },
  security: {
    label: 'Security',
    color: 'text-red-400',
    bgColor: 'bg-red-500',
    icon: '\u{1F6E1}',
  },
  performance: {
    label: 'Performance',
    color: 'text-orange-400',
    bgColor: 'bg-orange-500',
    icon: '⚡',
  },
  correctness: {
    label: 'Correctness',
    color: 'text-green-400',
    bgColor: 'bg-green-500',
    icon: '✓',
  },
  arbitrator: {
    label: 'Arbitrator',
    color: 'text-amber-400',
    bgColor: 'bg-amber-500',
    icon: '⚖',
  },
  judge: {
    label: 'Judge',
    color: 'text-purple-400',
    bgColor: 'bg-purple-500',
    icon: '\u{1F4CB}',
  },
  system: {
    label: 'System',
    color: 'text-gray-400',
    bgColor: 'bg-gray-500',
    icon: 'i',
  },
};

function AgentAvatar({ agent }: { agent: string }) {
  const meta = AGENT_META[agent] ?? AGENT_META.system;
  return (
    <div className={`w-8 h-8 rounded-full ${meta.bgColor} flex items-center justify-center text-white text-xs font-bold shrink-0 shadow-lg shadow-black/20`}>
      {meta.icon}
    </div>
  );
}

function RoundDivider({ round }: { round: number }) {
  return (
    <div className="flex items-center gap-4 py-3">
      <div className="flex-1 h-px bg-gradient-to-r from-transparent via-gray-700/50 to-transparent" />
      <span className="text-xs text-gray-500 font-medium px-3 py-1 rounded-full bg-gray-800/60 border border-gray-700/30">
        {round === 0 ? '\u{1F680} 准备阶段' : `Round ${round}`}
      </span>
      <div className="flex-1 h-px bg-gradient-to-r from-transparent via-gray-700/50 to-transparent" />
    </div>
  );
}

function MessageBubble({ message, round }: { message: DebateMessage; round: number }) {
  const [expanded, setExpanded] = useState(false);
  const agent = message.agent;
  const meta = AGENT_META[agent] ?? AGENT_META.system;
  const structured = message.structured as Record<string, unknown> | undefined;
  const responses = (structured?.responses as Array<Record<string, string>>) ?? [];
  const findings = (structured?.findings as Array<Record<string, string>>) ?? [];
  const stance = structured?.stance as string | undefined;
  const isCross = message.content.startsWith('[交叉审阅]');
  const isPlan = message.content.startsWith('[方案设计]');
  const isFix = message.content.startsWith('[仲裁后修复]') || message.content.startsWith('[补修]');
  const hasCode = !!message.code;

  const content = message.content.replace(/^\[.*?\]\s*/, '');
  const isLong = content.length > 600;

  if (agent === 'system') {
    return (
      <div className="flex justify-center py-2">
        <div className="flex items-center gap-2 px-4 py-2 bg-gray-800/40 rounded-full border border-gray-700/30 max-w-lg">
          <svg className="w-3.5 h-3.5 text-gray-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
          </svg>
          <span className="text-xs text-gray-400">{message.content}</span>
        </div>
      </div>
    );
  }

  if (isPlan) {
    return (
      <div className="flex gap-3 py-3 group">
        <AgentAvatar agent={agent} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className={`text-sm font-semibold ${meta.color}`}>{meta.label}</span>
            <span className="text-xs text-gray-600">{isFix ? '仲裁修复' : round === 1 ? '初版代码' : '方案设计'}</span>
          </div>
          <PlanDisplayCard content={message.content} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 py-3 group hover:bg-gray-800/20 -mx-4 px-4 rounded-xl transition-colors">
      <AgentAvatar agent={agent} />
      <div className="flex-1 min-w-0">
        {/* Agent name and badges */}
        <div className="flex items-center gap-2 mb-1.5">
          <span className={`text-sm font-semibold ${meta.color}`}>{meta.label}</span>
          {isCross && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-purple-900/40 text-purple-300 border border-purple-700/30">
              交叉审阅
            </span>
          )}
          {isFix && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-amber-900/40 text-amber-300 border border-amber-700/30">
              仲裁修复
            </span>
          )}
          {hasCode && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-900/40 text-blue-300 border border-blue-700/30">
              代码已更新
            </span>
          )}
          {stance && (
            <span className={`text-xs px-2 py-0.5 rounded-full border ${
              stance === 'satisfied'
                ? 'bg-green-900/40 text-green-300 border-green-700/30'
                : stance === 'attacking'
                  ? 'bg-red-900/40 text-red-300 border-red-700/30'
                  : 'bg-gray-800 text-gray-400 border-gray-700/30'
            }`}>
              {stance === 'satisfied' ? '✓ 通过' : stance === 'attacking' ? '有问题' : '审查中'}
            </span>
          )}
        </div>

        {/* Structured responses (accept/rebut) */}
        {responses.length > 0 && (
          <div className="space-y-2 mb-3">
            {responses.map((resp, i) => {
              const isAccept = resp.action === 'accept_and_fix';
              return (
                <div key={i} className={`rounded-xl px-4 py-3 ${
                  isAccept
                    ? 'bg-green-900/15 border border-green-800/25'
                    : 'bg-yellow-900/15 border border-yellow-800/25'
                }`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-sm font-medium ${isAccept ? 'text-green-300' : 'text-yellow-300'}`}>
                      {isAccept ? '✅ 接受并修复' : '❌ 用证据反驳'}
                    </span>
                    {resp.finding_ref && (
                      <span className="text-xs text-gray-500 bg-gray-800/60 px-2 py-0.5 rounded-full">
                        {resp.finding_ref}
                      </span>
                    )}
                  </div>
                  {resp.explanation && (
                    <p className="text-sm text-gray-300 leading-relaxed">{resp.explanation}</p>
                  )}
                  {resp.evidence && (
                    <div className="mt-2 px-3 py-2 bg-gray-900/60 rounded-lg text-xs text-gray-400 font-mono">
                      {resp.evidence}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Structured findings */}
        {findings.length > 0 && (
          <div className="space-y-2 mb-3">
            {findings.map((f, i) => (
              <div key={i} className="bg-gray-800/30 rounded-xl px-4 py-3 border border-gray-700/20">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`w-2 h-2 rounded-full ${
                    f.severity === 'critical' ? 'bg-red-500' :
                    f.severity === 'high' ? 'bg-orange-500' :
                    f.severity === 'medium' ? 'bg-yellow-500' : 'bg-gray-500'
                  }`} />
                  <span className={`text-xs font-semibold uppercase ${
                    f.severity === 'critical' ? 'text-red-400' :
                    f.severity === 'high' ? 'text-orange-400' :
                    f.severity === 'medium' ? 'text-yellow-400' : 'text-gray-400'
                  }`}>
                    {f.severity}
                  </span>
                  {f.category && <span className="text-xs text-gray-500">{f.category}</span>}
                </div>
                <p className="text-sm text-gray-300 leading-relaxed">{f.description}</p>
                {f.test_input && (
                  <div className="mt-2 px-3 py-2 bg-gray-900/60 rounded-lg text-xs text-gray-400 font-mono truncate">
                    test: {f.test_input}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Main content */}
        <div className={`text-sm text-gray-200 leading-relaxed prose prose-invert prose-sm max-w-none
                         prose-headings:text-gray-100 prose-headings:font-semibold
                         prose-code:text-blue-300 prose-code:bg-gray-800/60 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:text-xs
                         prose-pre:bg-gray-900/80 prose-pre:rounded-xl prose-pre:border prose-pre:border-gray-700/30
                         prose-a:text-blue-400 prose-strong:text-gray-100
                         prose-li:marker:text-gray-500
                         ${isLong && !expanded ? 'max-h-[300px] overflow-hidden relative' : ''}`}>
          <ReactMarkdown>{isCross ? content.replace('[交叉审阅] ', '') : content}</ReactMarkdown>
          {isLong && !expanded && (
            <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-gray-950 to-transparent" />
          )}
        </div>
        {isLong && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-2 text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors"
          >
            {expanded ? '↑ 收起' : '↓ 展开全文'}
          </button>
        )}
      </div>
    </div>
  );
}

export default function AttackResponsePanel({ messages, currentRound: _currentRound }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

  useEffect(() => {
    if (shouldAutoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, shouldAutoScroll]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    setShouldAutoScroll(scrollHeight - scrollTop - clientHeight < 100);
  };

  const groupedByRound: Record<number, DebateMessage[]> = {};
  for (const msg of messages) {
    const r = msg.round ?? 0;
    if (!groupedByRound[r]) groupedByRound[r] = [];
    groupedByRound[r].push(msg);
  }

  const rounds = Object.keys(groupedByRound).map(Number).sort((a, b) => a - b);

  if (messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 border border-gray-700/30 flex items-center justify-center mb-4">
          <svg className="w-8 h-8 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
          </svg>
        </div>
        <h3 className="text-base font-medium text-gray-300 mb-1">{'等待 Agent 开始工作...'}</h3>
        <p className="text-sm text-gray-500">{'提交任务后，多个 AI Agent 将开始对话式审查'}</p>
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto scroll-smooth"
      style={{ scrollbarGutter: 'stable' }}
    >
      <div className="max-w-3xl mx-auto px-4 py-4">
        {rounds.map((round) => {
          const msgs = groupedByRound[round];
          return (
            <div key={round}>
              <RoundDivider round={round} />
              {msgs.map((msg, i) => (
                <MessageBubble key={`${round}-${i}`} message={msg} round={round} />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
