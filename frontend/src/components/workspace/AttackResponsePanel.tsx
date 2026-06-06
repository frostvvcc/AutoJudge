import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import type { DebateMessage } from '../../types/debate';
import PlanDisplayCard from './PlanDisplayCard';
import { AGENT_LABELS, AGENT_DOTS } from '../../types/debate';

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
    <div className="space-y-5 max-h-[650px] overflow-y-auto pr-1 scroll-smooth">
      {rounds.map((round) => {
        const msgs = groupedByRound[round];
        const coderMsgs = msgs.filter((m) => m.agent === 'coder');
        const attackerMsgs = msgs.filter((m) =>
          ['security', 'performance', 'correctness'].includes(m.agent) &&
          !m.content.startsWith('[交叉审阅]'),
        );
        const crossMsgs = msgs.filter((m) => m.content.startsWith('[交叉审阅]'));
        const systemMsgs = msgs.filter((m) => m.agent === 'system');
        const arbitratorMsgs = msgs.filter((m) => m.agent === 'arbitrator');
        const judgeMsgs = msgs.filter((m) => m.agent === 'judge');

        const acceptCount = coderMsgs.reduce((n, m) => {
          const s = m.structured as Record<string, unknown> | undefined;
          const resps = (s?.responses as Array<Record<string, string>>) ?? [];
          return n + resps.filter((r) => r.action === 'accept_and_fix').length;
        }, 0);
        const rebutCount = coderMsgs.reduce((n, m) => {
          const s = m.structured as Record<string, unknown> | undefined;
          const resps = (s?.responses as Array<Record<string, string>>) ?? [];
          return n + resps.filter((r) => r.action === 'rebut_with_evidence').length;
        }, 0);
        const satisfiedCount = attackerMsgs.filter((m) => {
          const s = m.structured as Record<string, unknown> | undefined;
          return s?.stance === 'satisfied';
        }).length;

        return (
          <div key={round}>
            {/* Round header */}
            {round > 0 && (
              <div className="flex items-center gap-3 mb-3">
                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-gray-200 to-transparent" />
                <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-100 rounded-full">
                  <div className="w-2 h-2 rounded-full bg-blue-500" />
                  <span className="text-xs font-semibold text-gray-600">Round {round}</span>
                  {(acceptCount > 0 || rebutCount > 0) && (
                    <span className="text-xs text-gray-500">
                      {acceptCount > 0 && <span className="text-green-600">{acceptCount} 修复</span>}
                      {acceptCount > 0 && rebutCount > 0 && ' · '}
                      {rebutCount > 0 && <span className="text-yellow-600">{rebutCount} 反驳</span>}
                    </span>
                  )}
                  {satisfiedCount > 0 && (
                    <span className="text-xs text-green-600">{satisfiedCount}/3 满意</span>
                  )}
                </div>
                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-gray-200 to-transparent" />
              </div>
            )}

            {round === 0 && (
              <div className="flex items-center gap-3 mb-3">
                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-gray-200 to-transparent" />
                <div className="px-3 py-1 bg-gray-100 rounded-full">
                  <span className="text-xs text-gray-500">准备阶段</span>
                </div>
                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-gray-200 to-transparent" />
              </div>
            )}

            <div className="space-y-3">
              {/* Coder responses */}
              {coderMsgs.map((msg, i) =>
                msg.content.startsWith('[方案设计]') ? (
                  <PlanDisplayCard key={`plan-${round}-${i}`} content={msg.content} />
                ) : (
                  <CoderResponseCard key={`coder-${round}-${i}`} message={msg} round={round} />
                ),
              )}

              {/* Attackers */}
              {attackerMsgs.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <svg className="w-4 h-4 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                    </svg>
                    <span className="text-xs font-medium text-gray-500">
                      {round === 1 ? 'Attacker 并行审查' : 'Attacker 复查修复'}
                    </span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                    {attackerMsgs.map((msg, i) => (
                      <AttackerCard key={`atk-${round}-${i}`} message={msg} />
                    ))}
                  </div>
                </div>
              )}

              {/* Cross review */}
              {crossMsgs.length > 0 && (
                <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <svg className="w-4 h-4 text-purple-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
                    </svg>
                    <span className="text-xs font-semibold text-purple-600">交叉审阅</span>
                    <span className="text-xs text-purple-400">Attacker 互相补充观点</span>
                  </div>
                  <div className="space-y-2">
                    {crossMsgs.map((msg, i) => (
                      <div key={`cross-${round}-${i}`} className="flex items-start gap-2">
                        <div className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${AGENT_DOTS[msg.agent] ?? 'bg-gray-500'}`} />
                        <div>
                          <span className="text-xs font-medium text-purple-600">{AGENT_LABELS[msg.agent]}</span>
                          <div className="text-xs text-gray-600 mt-0.5 prose prose-xs max-w-none">
                            <ReactMarkdown>{msg.content.replace('[交叉审阅] ', '')}</ReactMarkdown>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* System messages */}
              {systemMsgs.map((msg, i) => (
                <div key={`sys-${round}-${i}`} className="flex items-start gap-2 px-3 py-2 bg-gray-50 rounded text-xs text-gray-500">
                  <svg className="w-3.5 h-3.5 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
                  </svg>
                  {msg.content}
                </div>
              ))}

              {/* Arbitrator messages */}
              {arbitratorMsgs.map((msg, i) => (
                <div key={`arb-${round}-${i}`} className="border border-amber-200 bg-amber-50 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-6 h-6 rounded-full bg-amber-100 flex items-center justify-center">
                      <svg className="w-3.5 h-3.5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v17.25m0 0c-1.472 0-2.882.265-4.185.75M12 20.25c1.472 0 2.882.265 4.185.75M18.75 4.97A48.416 48.416 0 0012 4.5c-2.291 0-4.545.16-6.75.47m13.5 0c1.01.143 2.01.317 3 .52m-3-.52l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.988 5.988 0 01-2.031.352 5.988 5.988 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L18.75 4.971zm-16.5.52c.99-.203 1.99-.377 3-.52m0 0l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.989 5.989 0 01-2.031.352 5.989 5.989 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L5.25 4.971z" />
                      </svg>
                    </div>
                    <span className="text-sm font-semibold text-amber-700">Arbitrator 仲裁</span>
                  </div>
                  <div className="text-sm text-gray-700 prose prose-sm max-w-none prose-headings:text-amber-700">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                </div>
              ))}

              {/* Judge messages */}
              {judgeMsgs.map((msg, i) => (
                <div key={`judge-${round}-${i}`} className="border border-purple-200 bg-purple-50 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-6 h-6 rounded-full bg-purple-100 flex items-center justify-center">
                      <svg className="w-3.5 h-3.5 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                      </svg>
                    </div>
                    <span className="text-sm font-semibold text-purple-700">Judge 报告</span>
                  </div>
                  <div className="text-sm text-gray-700 prose prose-sm max-w-none">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}


function CoderResponseCard({ message, round }: { message: DebateMessage; round: number }) {
  const [expanded, setExpanded] = useState(false);
  const structured = message.structured as Record<string, unknown> | undefined;
  const responses = (structured?.responses as Array<Record<string, string>>) ?? [];
  const isLong = message.content.length > 400;
  const hasCode = !!message.code;

  const isFix = message.content.startsWith('[仲裁后修复]') || message.content.startsWith('[补修]');

  return (
    <div className={`rounded-lg border ${isFix ? 'border-amber-200 bg-amber-50' : 'border-blue-200 bg-blue-50'} p-4`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={`w-6 h-6 rounded-full ${isFix ? 'bg-amber-100' : 'bg-blue-100'} flex items-center justify-center`}>
            <svg className={`w-3.5 h-3.5 ${isFix ? 'text-amber-600' : 'text-blue-600'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
            </svg>
          </div>
          <span className={`text-sm font-semibold ${isFix ? 'text-amber-700' : 'text-blue-700'}`}>
            {isFix ? 'Coder 仲裁修复' : round === 1 ? 'Coder 初版代码' : 'Coder 回应'}
          </span>
          {hasCode && (
            <span className="text-xs px-1.5 py-0.5 bg-white text-gray-500 rounded border border-gray-200">
              代码已更新
            </span>
          )}
        </div>
        {responses.length > 0 && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-green-600">
              {responses.filter((r) => r.action === 'accept_and_fix').length} 修复
            </span>
            <span className="text-gray-300">·</span>
            <span className="text-yellow-600">
              {responses.filter((r) => r.action === 'rebut_with_evidence').length} 反驳
            </span>
          </div>
        )}
      </div>

      {/* Structured accept/rebut cards */}
      {responses.length > 0 && (
        <div className="space-y-1.5 mb-3">
          {responses.map((resp, i) => {
            const isAccept = resp.action === 'accept_and_fix';
            return (
              <div
                key={i}
                className={`rounded-lg px-3 py-2 ${
                  isAccept ? 'bg-green-50 border border-green-200' : 'bg-yellow-50 border border-yellow-200'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm">{isAccept ? '✅' : '❌'}</span>
                  <span className={`text-xs font-semibold ${isAccept ? 'text-green-700' : 'text-yellow-700'}`}>
                    {isAccept ? '接受并修复' : '用证据反驳'}
                  </span>
                  {resp.finding_ref && (
                    <span className="text-xs text-gray-500 bg-white px-1.5 py-0.5 rounded border border-gray-200">
                      {resp.finding_ref}
                    </span>
                  )}
                </div>
                {resp.explanation && (
                  <p className="text-xs text-gray-600 leading-relaxed ml-6">{resp.explanation}</p>
                )}
                {resp.evidence && (
                  <div className="ml-6 mt-1 px-2 py-1 bg-white rounded border border-gray-200 text-xs text-gray-600 font-mono">
                    {resp.evidence}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Content */}
      <div className={`text-sm text-gray-700 prose prose-sm max-w-none
                       prose-headings:text-gray-800 prose-code:text-blue-600 prose-code:bg-white prose-code:px-1 prose-code:rounded
                       ${isLong && !expanded ? 'max-h-[180px] overflow-hidden relative' : ''}`}>
        <ReactMarkdown>{message.content.replace(/^\[.*?\]\s*/, '')}</ReactMarkdown>
        {isLong && !expanded && (
          <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-blue-50 to-transparent" />
        )}
      </div>
      {isLong && (
        <button onClick={() => setExpanded(!expanded)} className="mt-2 text-xs text-blue-600 hover:text-blue-500 flex items-center gap-1">
          {expanded ? '↑ 收起' : '↓ 展开全文'}
        </button>
      )}
    </div>
  );
}


function AttackerCard({ message }: { message: DebateMessage }) {
  const structured = message.structured as Record<string, unknown> | undefined;
  const stance = structured?.stance as string | undefined;
  const findings = (structured?.findings as Array<Record<string, string>>) ?? [];


  const isSatisfied = stance === 'satisfied';
  const agentIcon = message.agent === 'security' ? '🔒' : message.agent === 'performance' ? '⚡' : '✓';

  return (
    <div className={`rounded-lg border p-3 transition-colors ${
      isSatisfied ? 'border-green-200 bg-green-50' : 'border-gray-200 bg-white'
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <span className="text-sm">{agentIcon}</span>
          <span className="text-xs font-semibold text-gray-700">
            {AGENT_LABELS[message.agent]}
          </span>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          isSatisfied
            ? 'bg-green-100 text-green-700 border border-green-300'
            : stance === 'attacking'
              ? 'bg-red-50 text-red-600 border border-red-200'
              : 'bg-gray-100 text-gray-500'
        }`}>
          {isSatisfied ? '✓ 通过' : stance === 'attacking' ? '有问题' : '审查中'}
        </span>
      </div>

      {/* Findings */}
      {findings.length > 0 ? (
        <div className="space-y-1.5">
          {findings.map((f, i) => (
            <div key={i} className="bg-gray-50 rounded px-2.5 py-1.5">
              <div className="flex items-center gap-1.5 mb-0.5">
                <span className={`w-1.5 h-1.5 rounded-full ${
                  f.severity === 'critical' ? 'bg-red-500' :
                  f.severity === 'high' ? 'bg-orange-500' :
                  f.severity === 'medium' ? 'bg-yellow-500' : 'bg-gray-400'
                }`} />
                <span className={`text-xs font-medium ${
                  f.severity === 'critical' ? 'text-red-600' :
                  f.severity === 'high' ? 'text-orange-600' :
                  f.severity === 'medium' ? 'text-yellow-600' : 'text-gray-500'
                }`}>
                  {f.severity?.toUpperCase()}
                </span>
                {f.category && <span className="text-xs text-gray-600">{f.category}</span>}
              </div>
              <p className="text-xs text-gray-600 leading-relaxed">{f.description}</p>
              {f.test_input && (
                <div className="mt-1 px-2 py-1 bg-white rounded border border-gray-200 text-xs text-gray-600 font-mono truncate">
                  test: {f.test_input}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="flex items-center gap-1.5 text-xs text-gray-500 py-2">
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {isSatisfied ? '审查通过，无问题' : '未发现新问题'}
        </div>
      )}
    </div>
  );
}
