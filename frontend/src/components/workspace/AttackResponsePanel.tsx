import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import type { DebateMessage } from '../../types/debate';
import PlanDisplayCard from './PlanDisplayCard';
import { AGENT_COLORS, AGENT_LABELS, AGENT_DOTS } from '../../types/debate';

interface Props {
  messages: DebateMessage[];
  currentRound: number;
}

export default function AttackResponsePanel({ messages, currentRound: _currentRound }: Props) {
  const groupedByRound: Record<number, DebateMessage[]> = {};
  for (const msg of messages) {
    const r = msg.round ?? 0;
    if (!groupedByRound[r]) groupedByRound[r] = [];
    groupedByRound[r].push(msg);
  }

  const rounds = Object.keys(groupedByRound)
    .map(Number)
    .sort((a, b) => a - b);

  return (
    <div className="space-y-4 max-h-[600px] overflow-y-auto pr-1">
      {rounds.map((round) => {
        const msgs = groupedByRound[round];
        const coderMsgs = msgs.filter((m) => m.agent === 'coder');
        const attackerMsgs = msgs.filter((m) =>
          ['security', 'performance', 'correctness'].includes(m.agent),
        );
        const crossMsgs = msgs.filter((m) => m.content.startsWith('[交叉审阅]'));
        const otherMsgs = msgs.filter(
          (m) =>
            !coderMsgs.includes(m) &&
            !attackerMsgs.includes(m) &&
            !crossMsgs.includes(m),
        );

        return (
          <div key={round}>
            {round > 0 && (
              <div className="flex items-center gap-2 mb-3">
                <div className="h-px flex-1 bg-gray-800" />
                <span className="text-xs text-gray-500 font-medium">Round {round}</span>
                <div className="h-px flex-1 bg-gray-800" />
              </div>
            )}

            {/* Coder responses */}
            {coderMsgs.map((msg, i) =>
              msg.content.startsWith('[方案设计]') ? (
                <PlanDisplayCard key={`plan-${round}-${i}`} content={msg.content} />
              ) : (
                <CoderResponseCard key={`coder-${round}-${i}`} message={msg} />
              ),
            )}

            {/* Attackers - side by side */}
            {attackerMsgs.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-2">
                {attackerMsgs.map((msg, i) => (
                  <AttackerCard key={`atk-${round}-${i}`} message={msg} />
                ))}
              </div>
            )}

            {/* Cross review */}
            {crossMsgs.length > 0 && (
              <div className="mt-2 border-l-2 border-purple-500 bg-purple-500/5 rounded-r-lg p-3">
                <span className="text-xs font-semibold text-purple-400 mb-1 block">交叉审阅</span>
                {crossMsgs.map((msg, i) => (
                  <div key={`cross-${round}-${i}`} className="text-sm text-gray-300 mt-1">
                    <ReactMarkdown>{msg.content.replace('[交叉审阅] ', '')}</ReactMarkdown>
                  </div>
                ))}
              </div>
            )}

            {/* Other messages (system, judge, arbitrator) */}
            {otherMsgs.map((msg, i) => (
              <MessageBubble key={`other-${round}-${i}`} message={msg} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

function CoderResponseCard({ message }: { message: DebateMessage }) {
  const [expanded, setExpanded] = useState(false);
  const structured = message.structured as Record<string, unknown> | undefined;
  const responses = (structured?.responses as Array<Record<string, string>>) ?? [];
  const isLong = message.content.length > 300;

  return (
    <div className="border-l-2 border-blue-500 bg-blue-500/5 rounded-r-lg p-3">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-2 h-2 rounded-full bg-blue-500" />
        <span className="text-xs font-semibold text-blue-400">Coder</span>
        {message.content.includes('[方案设计]') && (
          <span className="text-xs px-1.5 py-0.5 bg-blue-900/50 text-blue-300 rounded">方案设计</span>
        )}
        {message.content.includes('[仲裁后修复]') && (
          <span className="text-xs px-1.5 py-0.5 bg-amber-900/50 text-amber-300 rounded">仲裁修复</span>
        )}
      </div>

      {/* Structured responses (accept/rebut per finding) */}
      {responses.length > 0 && (
        <div className="space-y-1 mb-2">
          {responses.map((resp, i) => (
            <div
              key={i}
              className={`flex items-start gap-2 px-2 py-1.5 rounded text-xs ${
                resp.action === 'accept_and_fix'
                  ? 'bg-green-900/20 text-green-300'
                  : 'bg-yellow-900/20 text-yellow-300'
              }`}
            >
              <span className="shrink-0 mt-0.5">
                {resp.action === 'accept_and_fix' ? '✅' : '❌'}
              </span>
              <div>
                <span className="font-medium">{resp.finding_ref}</span>
                <span className="text-gray-400 ml-1">
                  {resp.action === 'accept_and_fix' ? '接受并修复' : '反驳'}
                </span>
                {resp.explanation && (
                  <p className="text-gray-400 mt-0.5">{resp.explanation}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className={`text-sm text-gray-300 prose prose-invert prose-sm max-w-none ${isLong && !expanded ? 'max-h-[150px] overflow-hidden relative' : ''}`}>
        <ReactMarkdown>{message.content}</ReactMarkdown>
        {isLong && !expanded && (
          <div className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-gray-900/90 to-transparent" />
        )}
      </div>
      {isLong && (
        <button onClick={() => setExpanded(!expanded)} className="mt-1 text-xs text-blue-400 hover:text-blue-300">
          {expanded ? '收起' : '展开全文'}
        </button>
      )}
    </div>
  );
}

function AttackerCard({ message }: { message: DebateMessage }) {
  const structured = message.structured as Record<string, unknown> | undefined;
  const stance = structured?.stance as string | undefined;
  const findings = (structured?.findings as Array<Record<string, string>>) ?? [];
  const colorClass = AGENT_COLORS[message.agent] ?? AGENT_COLORS.system;
  const dotClass = AGENT_DOTS[message.agent] ?? AGENT_DOTS.system;

  return (
    <div className={`border-l-2 ${colorClass} rounded-r-lg p-2.5`}>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5">
          <div className={`w-2 h-2 rounded-full ${dotClass}`} />
          <span className="text-xs font-semibold text-gray-300">
            {AGENT_LABELS[message.agent] ?? message.agent}
          </span>
        </div>
        {stance && (
          <span
            className={`text-xs px-1.5 py-0.5 rounded ${
              stance === 'satisfied'
                ? 'bg-green-900/50 text-green-400'
                : 'bg-yellow-900/50 text-yellow-400'
            }`}
          >
            {stance === 'satisfied' ? '✓ 满意' : '攻击中'}
          </span>
        )}
      </div>
      {findings.length > 0 ? (
        <div className="space-y-1">
          {findings.map((f, i) => (
            <div key={i} className="text-xs text-gray-400">
              <span
                className={`inline-block px-1 rounded mr-1 ${
                  f.severity === 'critical' || f.severity === 'high'
                    ? 'bg-red-900/50 text-red-400'
                    : f.severity === 'medium'
                      ? 'bg-yellow-900/50 text-yellow-400'
                      : 'bg-gray-800 text-gray-500'
                }`}
              >
                {f.severity}
              </span>
              {f.description}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-500 italic">无新问题</p>
      )}
    </div>
  );
}

function MessageBubble({ message }: { message: DebateMessage }) {
  const colorClass = AGENT_COLORS[message.agent] ?? AGENT_COLORS.system;
  return (
    <div className={`border-l-2 ${colorClass} rounded-r-lg p-3 mt-2`}>
      <div className="text-xs font-medium text-gray-400 mb-1">
        {AGENT_LABELS[message.agent] ?? message.agent}
      </div>
      <div className="text-sm text-gray-300 prose prose-invert prose-sm max-w-none">
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>
    </div>
  );
}
