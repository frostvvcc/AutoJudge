import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import type { DebateMessage } from '../../types/debate';
import { AGENT_LABELS, AGENT_DOTS } from '../../types/debate';
import PlanDisplayCard from './PlanDisplayCard';
import AnalysisCard from './AnalysisCard';
import AnnotatedCodeReview from './AnnotatedCodeReview';
import type { InterruptData, AnalysisData } from '../../contexts/DebateContext';

function safeFindings(raw: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(raw)) return raw;
  if (typeof raw === 'string') {
    try { const parsed = JSON.parse(raw); if (Array.isArray(parsed)) return parsed; } catch {}
  }
  return [];
}

interface Props {
  messages: DebateMessage[];
  currentRound: number;
  selectedPhase: string | null;
  interruptData: InterruptData | null;
  onRespondInterrupt: (response: Record<string, unknown>) => void;
  analysisData?: AnalysisData | null;
}

export default function AttackResponsePanel({
  messages,
  currentRound: _currentRound,
  selectedPhase,
  interruptData,
  onRespondInterrupt,
  analysisData,
}: Props) {
  const groupedByRound: Record<number, DebateMessage[]> = {};
  for (const msg of messages) {
    const r = msg.round ?? 0;
    if (!groupedByRound[r]) groupedByRound[r] = [];
    groupedByRound[r].push(msg);
  }

  const rounds = Object.keys(groupedByRound).map(Number).sort((a, b) => a - b);

  const PHASE_MAP: Record<string, string> = {
    analysis: 'analysis',
    plan: 'plan', coding: 'coding', debate: 'debate',
    arbitration: 'arbitration', fixing: 'fixing',
    judging: 'judging', user_decision: 'user_decision',
    done: 'done',
  };
  const phaseView = selectedPhase && PHASE_MAP[selectedPhase] ? PHASE_MAP[selectedPhase] : 'all';
  const filteredRounds = rounds;
  const [expandedRound, setExpandedRound] = useState<number | null>(null);

  return (
    <div className="space-y-4">
      {/* Plan selection UI */}
      {interruptData?.type === 'plan_review' && (phaseView === 'plan' || phaseView === 'all') && (
        <PlanInteractionCard
          interruptData={interruptData}
          onRespond={onRespondInterrupt}
        />
      )}

      {/* Resolution decision UI */}
      {interruptData?.type === 'resolution_decision' && (phaseView === 'user_decision' || phaseView === 'all') && (
        <ResolutionDecisionCard
          interruptData={interruptData}
          onRespond={onRespondInterrupt}
        />
      )}

      {/* Analysis card — show whenever data exists (not just during analysis phase) */}
      {analysisData && (phaseView === 'analysis' || phaseView === 'plan' || phaseView === 'coding' || phaseView === 'all') && (
        <AnalysisCard data={analysisData} />
      )}

      {phaseView === 'plan' && (
        groupedByRound[0]?.filter((m) => m.content.startsWith('[方案设计]')).map((msg, i) => (
          <div key={`plan-${i}`} className="bg-white rounded-xl border border-gray-200 p-4">
            <PlanDisplayCard content={msg.content} />
          </div>
        ))
      )}

      {phaseView === 'coding' && (() => {
        const r1Coder = (groupedByRound[1] ?? []).filter((m) =>
          m.agent === 'coder' && !m.content.startsWith('[方案设计]') &&
          !(m.structured as Record<string, unknown>)?.responses
        );
        return r1Coder.length > 0 ? (
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-lg">⌨️</span>
              <span className="text-sm font-bold text-blue-700">Coder 初版代码</span>
            </div>
            {r1Coder.map((msg, i) => (
              <div key={`coding-${i}`} className="space-y-3">
                <CoderCodeCard message={msg} round={1} defaultShowCode />
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12 text-gray-400 text-sm">编码阶段暂无记录</div>
        );
      })()}

      {phaseView === 'debate' && (() => {
        const debateRounds = rounds.filter((r) => r > 0 && (groupedByRound[r] ?? []).some((m) =>
          ['security', 'performance', 'correctness'].includes(m.agent)
        ));
        if (debateRounds.length === 0) {
          return <div className="text-center py-12 text-gray-400 text-sm">辩论阶段暂无记录</div>;
        }

        const nextRoundResponses = (round: number): Array<Record<string, string>> => {
          const nextMsgs = groupedByRound[round + 1] ?? [];
          const resps: Array<Record<string, string>> = [];
          for (const m of nextMsgs) {
            if (m.agent !== 'coder') continue;
            const s = m.structured as Record<string, unknown> | undefined;
            const r = (s?.responses as Array<Record<string, string>>) ?? [];
            resps.push(...r);
          }
          return resps;
        };

        return debateRounds.map((round) => {
          const msgs = groupedByRound[round];
          const attackerMsgs = msgs.filter((m) =>
            ['security', 'performance', 'correctness'].includes(m.agent) &&
            !m.content.startsWith('[交叉审阅]'),
          );
          const crossMsgs = msgs.filter((m) => m.content.startsWith('[交叉审阅]'));
          const isLast = round === debateRounds[debateRounds.length - 1];
          const coderResps = nextRoundResponses(round);
          const hasFindings = attackerMsgs.some((m) => {
            const st = m.structured as Record<string, unknown> | undefined;
            return ((st?.findings as unknown[]) ?? []).length > 0;
          });
          const isReviewOnly = !hasFindings;
          const isCollapsible = debateRounds.length > 1;
          const isExpanded = expandedRound === round || !isCollapsible || round === debateRounds[debateRounds.length - 1];

          const roundLabel = round <= 1
            ? `Round ${round} · 初版审查`
            : isReviewOnly
              ? `Round ${round} · 修复后复查`
              : `Round ${round} · 审查 + 回应`;

          return (
            <div key={round} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <button
                onClick={() => isCollapsible && setExpandedRound(isExpanded ? null : round)}
                className={`w-full flex items-center justify-between px-4 py-3 ${isCollapsible ? 'hover:bg-gray-50 cursor-pointer' : ''} transition-colors`}
              >
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                    round <= 1 ? 'bg-purple-100 text-purple-600' : 'bg-green-100 text-green-600'
                  }`}>
                    {round}
                  </div>
                  <span className="text-sm font-semibold text-gray-700">{roundLabel}</span>
                  <RoundSummaryChips messages={msgs} />
                </div>
                {isCollapsible && (
                  <svg className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                )}
              </button>
              {isExpanded && (() => {
                const coderMsgsThisRound = (groupedByRound[round] ?? []).filter(m => m.agent === 'coder');
                const coderMsgsPrevRound = (groupedByRound[round - 1] ?? []).filter(m => m.agent === 'coder');
                let reviewCode = coderMsgsThisRound.find(m => m.code)?.code
                  ?? coderMsgsPrevRound.find(m => m.code)?.code ?? '';

                // Bug#4: code version regression guard
                const prevRoundCode = coderMsgsPrevRound.find(m => m.code)?.code ?? '';
                if (prevRoundCode && reviewCode && reviewCode.length < prevRoundCode.length * 0.2) {
                  reviewCode = prevRoundCode;
                }

                // Collect findings from both regular attacks and cross-review messages
                const allAttackerAndCrossMsgs = msgs.filter(m =>
                  ['security', 'performance', 'correctness'].includes(m.agent)
                );
                const allFindings: Array<{ agent: string; category: string; severity: string; description: string; test_input?: string; line_start?: number; line_end?: number }> = [];
                for (const m of allAttackerAndCrossMsgs) {
                  const s = m.structured as Record<string, unknown> | undefined;
                  const findings = safeFindings(s?.findings);
                  for (const f of findings) {
                    allFindings.push({
                      agent: m.agent,
                      category: (f.category as string) ?? '',
                      severity: (f.severity as string) ?? 'medium',
                      description: (f.description as string) ?? '',
                      test_input: f.test_input as string | undefined,
                      line_start: f.line_start as number | undefined,
                      line_end: f.line_end as number | undefined,
                    });
                  }
                }

                const prevCode = round > 1
                  ? (groupedByRound[round - 1] ?? []).find(m => m.agent === 'coder' && m.code)?.code ?? ''
                  : '';
                const fixedLines = new Set<number>();
                if (prevCode && reviewCode && prevCode !== reviewCode) {
                  const prevLines = prevCode.split('\n');
                  const currLines = reviewCode.split('\n');
                  for (let i = 0; i < currLines.length; i++) {
                    if (i >= prevLines.length || currLines[i] !== prevLines[i]) {
                      fixedLines.add(i + 1);
                    }
                  }
                  if (fixedLines.size > currLines.length * 0.8) fixedLines.clear();
                }

                // Build satisfied entries with anchor lines from previous round's findings
                const prevRoundFindings: Array<{ agent: string; line_start?: number }> = [];
                for (const pm of (groupedByRound[round - 1] ?? [])) {
                  if (['security', 'performance', 'correctness'].includes(pm.agent)) {
                    const ps = pm.structured as Record<string, unknown> | undefined;
                    for (const pf of ((ps?.findings as Array<Record<string, unknown>>) ?? [])) {
                      prevRoundFindings.push({ agent: pm.agent, line_start: pf.line_start as number | undefined });
                    }
                  }
                }

                const satisfiedEntries: Array<{ agent: string; message: string; anchorLine?: number }> = [];
                for (const m of attackerMsgs) {
                  const st = m.structured as Record<string, unknown> | undefined;
                  if (st?.stance === 'satisfied') {
                    const msg = (st.message as string) ?? `${AGENT_LABELS[m.agent]} 审查通过`;
                    const prevFinding = prevRoundFindings.find(f => f.agent === m.agent);
                    satisfiedEntries.push({ agent: m.agent, message: msg, anchorLine: prevFinding?.line_start });
                  }
                }
                const roundAllSatisfied = satisfiedEntries.length > 0 && allFindings.length === 0;

                // Smart layout: if code is very short but findings are many with no line refs,
                // this is a design/plan review, not a code review — use text list instead of annotation layout
                const codeLineCount = reviewCode.replace(/\\n/g, '\n').split('\n').length;
                const allLineMissing = allFindings.length > 0 && allFindings.every(f => !f.line_start || f.line_start <= 1);
                const isPlanReview = codeLineCount < 20 && allFindings.length > codeLineCount && allLineMissing;

                return (
                  <div className="border-t border-gray-100 pt-3">
                    {isPlanReview ? (
                      <ThreadedDebateView attackerMsgs={attackerMsgs} nextRoundResponses={hasFindings ? coderResps : undefined} isLastRound={isLast && coderResps.length === 0} />
                    ) : reviewCode ? (
                      <AnnotatedCodeReview
                        code={reviewCode}
                        language="python"
                        findings={allFindings}
                        coderResponses={hasFindings ? coderResps.map(r => ({
                          finding_ref: (r as Record<string,string>).finding_ref ?? '',
                          action: (r as Record<string,string>).action ?? '',
                          explanation: (r as Record<string,string>).explanation ?? '',
                          evidence: (r as Record<string,string>).evidence,
                        })) : []}
                        round={round}
                        coderFixedLines={fixedLines.size > 0 ? fixedLines : undefined}
                        satisfiedEntries={satisfiedEntries.length > 0 ? satisfiedEntries : undefined}
                        allSatisfied={roundAllSatisfied}
                      />
                    ) : (
                      <div className="px-4 pb-4 space-y-4">
                        {attackerMsgs.length > 0 && (
                          <ThreadedDebateView attackerMsgs={attackerMsgs} nextRoundResponses={hasFindings ? coderResps : undefined} isLastRound={isLast && coderResps.length === 0} />
                        )}
                      </div>
                    )}
                    {crossMsgs.length > 0 && <div className="px-4 pb-4"><CrossReviewCard messages={crossMsgs} /></div>}
                  </div>
                );
              })()}
            </div>
          );
        });
      })()}

      {phaseView === 'arbitration' && (() => {
        const arbMsgs = messages.filter((m) => m.agent === 'arbitrator');
        return arbMsgs.length > 0 ? arbMsgs.map((msg, i) => (
          <ArbitratorCard key={`arb-${i}`} message={msg} />
        )) : <div className="text-center py-12 text-gray-400 text-sm">仲裁阶段暂无记录</div>;
      })()}

      {phaseView === 'fixing' && (() => {
        const fixMsgs = messages.filter((m) =>
          m.agent === 'coder' && (m.content.startsWith('[仲裁后修复]') || m.content.startsWith('[补修]') || m.content.startsWith('[聚焦修复'))
        );
        return fixMsgs.length > 0 ? fixMsgs.map((msg, i) => (
          <div key={`fix-${i}`} className="bg-white rounded-xl border border-gray-200 p-4">
            <CoderCodeCard message={msg} round={msg.round ?? 0} />
          </div>
        )) : <div className="text-center py-12 text-gray-400 text-sm">修复阶段暂无记录</div>;
      })()}

      {(phaseView === 'judging' || phaseView === 'user_decision') && (() => {
        const jMsgs = messages.filter((m) => m.agent === 'judge');
        return jMsgs.length > 0 ? jMsgs.map((msg, i) => (
          <JudgeCard key={`judge-${i}`} message={msg} />
        )) : <div className="text-center py-12 text-gray-400 text-sm">评审阶段暂无记录</div>;
      })()}

      {/* Done: empty here, results section in WorkspacePage shows code + report */}
      {phaseView === 'done' && null}

      {/* Default: show all rounds grouped (no specific phase selected) */}
      {phaseView === 'all' && filteredRounds.map((round) => {
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

        const isPlanRound = round === 0 && coderMsgs.some((m) => m.content.startsWith('[方案设计]'));
        const isDebateRound = round > 0 && attackerMsgs.length > 0;
        const isCollapsible = filteredRounds.length > 1;
        const isExpanded = expandedRound === round || !isCollapsible || round === filteredRounds[filteredRounds.length - 1];
        const roundLabel = isPlanRound ? '方案设计' : round === 0 ? '准备阶段' : `Round ${round}`;

        return (
          <div key={round} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <button
              onClick={() => isCollapsible && setExpandedRound(isExpanded ? null : round)}
              className={`w-full flex items-center justify-between px-4 py-3 ${isCollapsible ? 'hover:bg-gray-50 cursor-pointer' : ''} transition-colors`}
            >
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                  isPlanRound ? 'bg-blue-100 text-blue-600' : isDebateRound ? 'bg-purple-100 text-purple-600' : 'bg-gray-100 text-gray-500'
                }`}>{isPlanRound ? '💡' : round === 0 ? '▶' : round}</div>
                <span className="text-sm font-semibold text-gray-700">{roundLabel}</span>
                {isDebateRound && <RoundSummaryChips messages={msgs} />}
              </div>
              {isCollapsible && (
                <svg className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                  fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              )}
            </button>
            {isExpanded && (() => {
              let reviewCode = isDebateRound
                ? (coderMsgs.find(m => m.code)?.code
                  ?? (groupedByRound[round - 1] ?? []).find(m => m.agent === 'coder' && m.code)?.code
                  ?? '')
                : '';

              // Bug#4: code version regression guard
              const prevRoundCode2 = (groupedByRound[round - 1] ?? []).find(m => m.agent === 'coder' && m.code)?.code ?? '';
              if (prevRoundCode2 && reviewCode && reviewCode.length < prevRoundCode2.length * 0.2) {
                reviewCode = prevRoundCode2;
              }

              // Collect findings from all attacker messages including cross-review
              const allAttackerMsgs2 = msgs.filter(m => ['security', 'performance', 'correctness'].includes(m.agent));
              const allFindings: Array<{ agent: string; category: string; severity: string; description: string; test_input?: string; line_start?: number; line_end?: number }> = [];
              if (isDebateRound) {
                for (const m of allAttackerMsgs2) {
                  const s = m.structured as Record<string, unknown> | undefined;
                  for (const f of (safeFindings(s?.findings))) {
                    allFindings.push({
                      agent: m.agent,
                      category: (f.category as string) ?? '',
                      severity: (f.severity as string) ?? 'medium',
                      description: (f.description as string) ?? '',
                      test_input: f.test_input as string | undefined,
                      line_start: f.line_start as number | undefined,
                      line_end: f.line_end as number | undefined,
                    });
                  }
                }
              }

              const nextCoderMsgs = (groupedByRound[round + 1] ?? []).filter(m => m.agent === 'coder');
              const coderResps: Array<Record<string, string>> = [];
              for (const m of nextCoderMsgs) {
                const s = m.structured as Record<string, unknown> | undefined;
                coderResps.push(...((s?.responses as Array<Record<string, string>>) ?? []));
              }

              const prevCode = round > 1
                ? (groupedByRound[round - 1] ?? []).find(m => m.agent === 'coder' && m.code)?.code ?? ''
                : '';
              const fixedLines = new Set<number>();
              if (prevCode && reviewCode && prevCode !== reviewCode) {
                const prevLines = prevCode.split('\n');
                const currLines = reviewCode.split('\n');
                for (let i = 0; i < currLines.length; i++) {
                  if (i >= prevLines.length || currLines[i] !== prevLines[i]) fixedLines.add(i + 1);
                }
                if (fixedLines.size > currLines.length * 0.8) fixedLines.clear();
              }

              return (
                <div className="px-4 pb-4 space-y-4 border-t border-gray-100 pt-3">
                  {coderMsgs.filter((m) => m.content.startsWith('[方案设计]')).map((msg, i) => (
                    <PlanDisplayCard key={`plan-${round}-${i}`} content={msg.content} />
                  ))}
                  {coderMsgs.filter((m) => !m.content.startsWith('[方案设计]') && !(m.structured as Record<string, unknown>)?.responses).map((msg, i) => (
                    <CoderCodeCard key={`cc-${round}-${i}`} message={msg} round={round} />
                  ))}
                  {(() => {
                    const codeLC = reviewCode.replace(/\\n/g, '\n').split('\n').length;
                    const allLM = allFindings.length > 0 && allFindings.every(f => !f.line_start || f.line_start <= 1);
                    const planReview = codeLC < 20 && allFindings.length > codeLC && allLM;
                    if (planReview && isDebateRound) {
                      return <ThreadedDebateView attackerMsgs={attackerMsgs} coderMsgs={[]} />;
                    }
                    return null;
                  })()}
                  {isDebateRound && reviewCode ? (() => {
                    const codeLC2 = reviewCode.replace(/\\n/g, '\n').split('\n').length;
                    const allLM2 = allFindings.length > 0 && allFindings.every(f => !f.line_start || f.line_start <= 1);
                    const planReview2 = codeLC2 < 20 && allFindings.length > codeLC2 && allLM2;
                    if (planReview2) return null;

                    const thisRoundResps: Array<Record<string, string>> = [];
                    for (const m of coderMsgs) {
                      const s = m.structured as Record<string, unknown> | undefined;
                      thisRoundResps.push(...((s?.responses as Array<Record<string, string>>) ?? []));
                    }
                    const mergedResps = thisRoundResps.length > 0 ? thisRoundResps : coderResps;

                    return (
                    <AnnotatedCodeReview
                      code={reviewCode}
                      language="python"
                      findings={allFindings}
                      coderResponses={allFindings.length > 0 ? mergedResps.map(r => ({
                        finding_ref: r.finding_ref ?? '',
                        action: r.action ?? '',
                        explanation: r.explanation ?? '',
                        evidence: r.evidence,
                      })) : []}
                      round={round}
                      coderFixedLines={fixedLines.size > 0 ? fixedLines : undefined}
                    />
                    );
                  })() : attackerMsgs.length > 0 ? (
                    <div className="space-y-3">
                      <span className="text-xs font-semibold text-red-500">{round <= 1 ? '⚔️ Attacker 并行审查' : '⚔️ Attacker 复查修复'}</span>
                      <ThreadedDebateView attackerMsgs={attackerMsgs} coderMsgs={[]} />
                    </div>
                  ) : null}
                  {crossMsgs.length > 0 && <CrossReviewCard messages={crossMsgs} />}
                  {systemMsgs.map((msg, i) => (
                    <div key={`sys-${round}-${i}`} className="flex items-start gap-2 px-3 py-2 bg-gray-50 rounded-lg text-xs text-gray-500">
                      <span className="text-gray-400 shrink-0">ℹ️</span>{msg.content}
                    </div>
                  ))}
                  {arbitratorMsgs.map((msg, i) => <ArbitratorCard key={`arb-${round}-${i}`} message={msg} />)}
                  {judgeMsgs.map((msg, i) => <JudgeCard key={`judge-${round}-${i}`} message={msg} />)}
                </div>
              );
            })()}
          </div>
        );
      })}

      {filteredRounds.length === 0 && (
        <div className="text-center py-12 text-gray-400 text-sm">
          {selectedPhase ? '该阶段暂无记录' : '等待任务开始...'}
        </div>
      )}
    </div>
  );
}



function RoundSummaryChips({ messages }: { messages: DebateMessage[] }) {
  const coderMsgs = messages.filter((m) => m.agent === 'coder');
  const attackerMsgs = messages.filter((m) =>
    ['security', 'performance', 'correctness'].includes(m.agent) &&
    !m.content.startsWith('[交叉审阅]'),
  );

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
    <div className="flex items-center gap-2 text-xs">
      {acceptCount > 0 && <span className="px-1.5 py-0.5 rounded-full bg-green-100 text-green-700">{acceptCount} 修复</span>}
      {rebutCount > 0 && <span className="px-1.5 py-0.5 rounded-full bg-yellow-100 text-yellow-700">{rebutCount} 反驳</span>}
      {satisfiedCount > 0 && <span className="px-1.5 py-0.5 rounded-full bg-green-100 text-green-700">{satisfiedCount}/3 通过</span>}
    </div>
  );
}


function ThreadedDebateView({
  attackerMsgs,
  nextRoundResponses,
  isLastRound,
}: {
  attackerMsgs: DebateMessage[];
  coderMsgs?: DebateMessage[];
  nextRoundResponses?: Array<Record<string, string>>;
  isLastRound?: boolean;
}) {
  const allResponses = nextRoundResponses ?? [];

  const respsByAgent: Record<string, Array<Record<string, string>>> = {};
  for (const r of allResponses) {
    const ref = (r.finding_ref ?? '').toUpperCase();
    let agent = '';
    if (ref.includes('SECURITY')) agent = 'security';
    else if (ref.includes('PERFORMANCE')) agent = 'performance';
    else if (ref.includes('CORRECTNESS')) agent = 'correctness';
    if (agent) {
      if (!respsByAgent[agent]) respsByAgent[agent] = [];
      respsByAgent[agent].push(r);
    }
  }

  const consumedIndex: Record<string, number> = {};

  return (
    <div className="space-y-3">
      {attackerMsgs.map((msg, mi) => {
        const s = msg.structured as Record<string, unknown> | undefined;
        const findings = safeFindings(s?.findings) as Array<Record<string, string>>;
        const stance = s?.stance as string | undefined;
        const isSatisfied = stance === 'satisfied';
        const agentIcon = msg.agent === 'security' ? '🔒' : msg.agent === 'performance' ? '⚡' : '✓';
        const agentResps = respsByAgent[msg.agent] ?? [];

        return (
          <div key={`atk-${mi}`} className={`rounded-xl border p-4 transition-all ${
            isSatisfied ? 'border-green-200 bg-green-50/50' : 'border-gray-200 bg-white'
          }`}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-lg">{agentIcon}</span>
                <span className="text-sm font-bold text-gray-700">
                  {AGENT_LABELS[msg.agent]}
                </span>
              </div>
              <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                isSatisfied
                  ? 'bg-green-100 text-green-700'
                  : stance === 'attacking'
                    ? 'bg-red-100 text-red-600'
                    : 'bg-gray-100 text-gray-500'
              }`}>
                {isSatisfied ? '✓ 通过' : stance === 'attacking' ? '有问题' : '审查中'}
              </span>
            </div>

            {findings.length > 0 ? (
              <div className="space-y-2">
                {findings.map((f, fi) => {
                  const idx = consumedIndex[msg.agent] ?? 0;
                  const coderResp = agentResps[idx] ?? null;
                  if (coderResp) consumedIndex[msg.agent] = idx + 1;

                  return (
                    <div key={fi} className="space-y-0">
                      {/* Attacker finding */}
                      <div className="bg-gray-50 rounded-t-lg px-3 py-2 border border-gray-200 border-b-0">
                        <div className="flex items-center gap-2 mb-1">
                          <SeverityDot severity={f.severity} />
                          <span className={`text-xs font-semibold ${severityColor(f.severity)}`}>
                            {f.severity?.toUpperCase()}
                          </span>
                          {f.category && <span className="text-xs text-gray-500">{f.category}</span>}
                        </div>
                        <p className="text-xs text-gray-600 leading-relaxed">{f.description}</p>
                        {f.test_input && (
                          <div className="mt-1.5 px-2 py-1 bg-white rounded border border-gray-200 text-xs font-mono text-gray-500 truncate">
                            test: {f.test_input}
                          </div>
                        )}
                      </div>

                      {/* Coder's threaded response */}
                      {coderResp ? (
                        <div className={`rounded-b-lg px-3 py-2 border ${
                          coderResp.action === 'accept_and_fix'
                            ? 'bg-green-50 border-green-200'
                            : 'bg-yellow-50 border-yellow-200'
                        }`}>
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-xs">↳</span>
                            <span className="text-xs font-medium text-blue-600">Coder</span>
                            <span className={`text-xs px-1.5 py-0.5 rounded ${
                              coderResp.action === 'accept_and_fix'
                                ? 'bg-green-100 text-green-700'
                                : 'bg-yellow-100 text-yellow-700'
                            }`}>
                              {coderResp.action === 'accept_and_fix' ? '✅ 接受修复' : '❌ 反驳'}
                            </span>
                          </div>
                          {coderResp.explanation && (
                            <p className="text-xs text-gray-600 leading-relaxed ml-4">{coderResp.explanation}</p>
                          )}
                          {coderResp.evidence && (
                            <div className="ml-4 mt-1 px-2 py-1 bg-white rounded border border-gray-200 text-xs font-mono text-gray-600">
                              {coderResp.evidence}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="rounded-b-lg px-3 py-1.5 border border-gray-200 border-t-0 bg-gray-50">
                          <span className="text-xs text-gray-400 italic">
                            {isLastRound ? '已进入仲裁阶段' : '等待 Coder 回应...'}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="flex items-center gap-1.5 text-xs text-gray-500 py-1">
                {isSatisfied ? '✓ 审查通过，无问题' : '未发现新问题'}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}


function SeverityDot({ severity }: { severity?: string }) {
  const color = severity === 'critical' ? 'bg-red-500' :
    severity === 'high' ? 'bg-orange-500' :
    severity === 'medium' ? 'bg-yellow-500' : 'bg-gray-400';
  return <span className={`w-2 h-2 rounded-full ${color}`} />;
}

function severityColor(severity?: string): string {
  if (severity === 'critical') return 'text-red-600';
  if (severity === 'high') return 'text-orange-600';
  if (severity === 'medium') return 'text-yellow-600';
  return 'text-gray-500';
}


function CoderResponsesSection({
  coderMsgs,
  allMessages,
  currentRound,
}: {
  coderMsgs: DebateMessage[];
  allMessages: DebateMessage[];
  currentRound: number;
}) {
  const allResponses: Array<Record<string, string>> = [];
  for (const m of coderMsgs) {
    const s = m.structured as Record<string, unknown> | undefined;
    const resps = (s?.responses as Array<Record<string, string>>) ?? [];
    allResponses.push(...resps);
  }

  if (allResponses.length === 0) return null;

  const prevRoundFindings: Map<string, { finding: Record<string, string>; agent: string }> = new Map();
  for (const msg of allMessages) {
    if (!['security', 'performance', 'correctness'].includes(msg.agent)) continue;
    if ((msg.round ?? 0) >= currentRound) continue;
    const s = msg.structured as Record<string, unknown> | undefined;
    const findings = safeFindings(s?.findings) as Array<Record<string, string>>;
    findings.forEach((f, i) => {
      const ref = `${msg.agent.toUpperCase()}-${String(i + 1).padStart(3, '0')}`;
      prevRoundFindings.set(ref, { finding: f, agent: msg.agent });
    });
  }

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50/30 p-4 space-y-3">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-sm">💬</span>
        <span className="text-sm font-bold text-blue-700">Coder 逐条回应</span>
        <div className="flex items-center gap-2 text-xs ml-2">
          <span className="px-1.5 py-0.5 rounded-full bg-green-100 text-green-700">
            {allResponses.filter((r) => r.action === 'accept_and_fix').length} 修复
          </span>
          <span className="px-1.5 py-0.5 rounded-full bg-yellow-100 text-yellow-700">
            {allResponses.filter((r) => r.action === 'rebut_with_evidence').length} 反驳
          </span>
        </div>
      </div>

      <div className="space-y-2">
        {allResponses.map((resp, i) => {
          const isAccept = resp.action === 'accept_and_fix';
          const ref = resp.finding_ref;
          const originalFinding = ref ? prevRoundFindings.get(ref) : null;

          return (
            <div key={i} className="space-y-0">
              {/* Quoted original attacker finding */}
              {originalFinding ? (
                <div className="bg-gray-100 rounded-t-lg px-3 py-2 border border-gray-200 border-b-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs text-gray-400">引用</span>
                    <span className="text-xs font-medium text-gray-500">
                      {AGENT_LABELS[originalFinding.agent] ?? originalFinding.agent}
                    </span>
                    {originalFinding.finding.severity && (
                      <span className={`text-xs ${severityColor(originalFinding.finding.severity)}`}>
                        [{originalFinding.finding.severity.toUpperCase()}]
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 leading-relaxed line-clamp-2">
                    {originalFinding.finding.description}
                  </p>
                </div>
              ) : ref ? (
                <div className="bg-gray-100 rounded-t-lg px-3 py-1.5 border border-gray-200 border-b-0">
                  <span className="text-xs text-gray-400">回复 {ref}</span>
                </div>
              ) : null}

              {/* Coder's response */}
              <div className={`${originalFinding || ref ? 'rounded-b-lg' : 'rounded-lg'} px-3 py-2 border ${
                isAccept ? 'bg-green-50 border-green-200' : 'bg-yellow-50 border-yellow-200'
              }`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs">{originalFinding || ref ? '↳' : ''}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                    isAccept ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                  }`}>
                    {isAccept ? '✅ 接受修复' : '❌ 反驳'}
                  </span>
                </div>
                {resp.explanation && (
                  <p className="text-xs text-gray-600 leading-relaxed ml-4">{resp.explanation}</p>
                )}
                {resp.evidence && (
                  <div className="ml-4 mt-1 px-2 py-1 bg-white rounded border border-gray-200 text-xs font-mono text-gray-600">
                    {resp.evidence}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


function CoderCodeCard({ message, round, defaultShowCode }: { message: DebateMessage; round: number; defaultShowCode?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [showCode, setShowCode] = useState(!!defaultShowCode);
  const isFix = message.content.startsWith('[仲裁后修复]') || message.content.startsWith('[补修]') || message.content.startsWith('[聚焦修复');
  const hasCode = !!message.code;
  const content = message.content.replace(/^\[.*?\]\s*/, '');
  const isLong = content.length > 300;

  return (
    <div className={`rounded-xl border p-4 ${isFix ? 'border-amber-200 bg-amber-50/50' : 'border-blue-200 bg-blue-50/50'}`}>
      <div className="flex items-center gap-2 mb-3">
        <div className={`w-7 h-7 rounded-full flex items-center justify-center text-sm ${
          isFix ? 'bg-amber-100' : 'bg-blue-100'
        }`}>
          {isFix ? '🔧' : '⌨️'}
        </div>
        <span className={`text-sm font-bold ${isFix ? 'text-amber-700' : 'text-blue-700'}`}>
          {isFix ? 'Coder 修复' : round <= 1 ? 'Coder 初版代码' : 'Coder 回应'}
        </span>
        {hasCode && (
          <button
            onClick={() => setShowCode(!showCode)}
            className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
              showCode ? 'bg-blue-100 border-blue-300 text-blue-700' : 'bg-white border-gray-200 text-gray-500 hover:bg-gray-50'
            }`}
          >
            {showCode ? '隐藏代码' : '查看代码'}
          </button>
        )}
      </div>

      {/* Code preview */}
      {hasCode && showCode && (
        <div className="mb-3 rounded-lg overflow-hidden border border-gray-300">
          <SyntaxHighlighter
            language="python"
            style={oneDark}
            customStyle={{ margin: 0, padding: '0.75rem', fontSize: '0.75rem', maxHeight: '350px' }}
            showLineNumbers
            lineNumberStyle={{ color: '#4a5568', fontSize: '0.65rem' }}
          >
            {message.code!}
          </SyntaxHighlighter>
        </div>
      )}

      <div className={`text-sm text-gray-700 prose prose-sm max-w-none
                       prose-headings:text-gray-800 prose-headings:text-sm prose-headings:font-semibold
                       prose-code:text-blue-600 prose-code:bg-white prose-code:px-1 prose-code:rounded
                       ${isLong && !expanded ? 'max-h-[200px] overflow-hidden relative' : ''}`}>
        <ReactMarkdown>{content}</ReactMarkdown>
        {isLong && !expanded && (
          <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-blue-50 to-transparent" />
        )}
      </div>
      {isLong && (
        <button onClick={() => setExpanded(!expanded)} className="mt-2 text-xs text-blue-600 hover:text-blue-500">
          {expanded ? '↑ 收起' : '↓ 展开全文'}
        </button>
      )}
    </div>
  );
}


function CrossReviewCard({ messages }: { messages: DebateMessage[] }) {
  const [show, setShow] = useState(false);
  return (
    <div className="rounded-xl border border-purple-200 bg-purple-50/50 overflow-hidden">
      <button
        onClick={() => setShow(!show)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-purple-100/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm">🔄</span>
          <span className="text-xs font-semibold text-purple-600">交叉审阅</span>
          <span className="text-xs text-purple-400">{messages.length} 条补充观点</span>
        </div>
        <svg className={`w-3.5 h-3.5 text-purple-400 transition-transform ${show ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {show && (
        <div className="px-4 pb-3 space-y-2 border-t border-purple-100">
          {messages.map((msg, i) => (
            <div key={i} className="flex items-start gap-2 pt-2">
              <div className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${AGENT_DOTS[msg.agent] ?? 'bg-gray-500'}`} />
              <div>
                <span className="text-xs font-medium text-purple-600">{AGENT_LABELS[msg.agent]}</span>
                <div className="text-xs text-gray-600 mt-0.5 leading-relaxed prose prose-xs max-w-none">
                  <ReactMarkdown>{msg.content.replace('[交叉审阅] ', '')}</ReactMarkdown>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


function ArbitratorCard({ message }: { message: DebateMessage }) {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">⚖️</span>
        <span className="text-sm font-bold text-amber-700">Arbitrator 仲裁</span>
      </div>
      <div className="text-sm text-gray-700 prose prose-sm max-w-none prose-headings:text-amber-700">
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>
    </div>
  );
}


function JudgeCard({ message }: { message: DebateMessage }) {
  return (
    <div className="rounded-xl border border-purple-200 bg-purple-50/50 p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">📋</span>
        <span className="text-sm font-bold text-purple-700">Judge 评审报告</span>
      </div>
      <div className="text-sm text-gray-700 prose prose-sm max-w-none">
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>
    </div>
  );
}


function PlanInteractionCard({
  interruptData,
  onRespond,
}: {
  interruptData: InterruptData;
  onRespond: (response: Record<string, unknown>) => void;
}) {
  const [feedback, setFeedback] = useState('');
  const [mode, setMode] = useState<'select' | 'chat'>('select');
  const [selectedPlan, setSelectedPlan] = useState<number | null>(null);

  const planContent = typeof interruptData.content === 'string' ? interruptData.content : '';

  return (
    <div className="rounded-xl border-2 border-blue-300 bg-white p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl">🎯</span>
          <h3 className="text-sm font-bold text-blue-700">请选择方案</h3>
          <span className="text-xs text-blue-400">
            点击方案卡片选择 · 第 {(interruptData.round ?? 0) + 1}/{interruptData.max_rounds ?? 7} 轮
          </span>
        </div>
      </div>

      {planContent && (
        <PlanDisplayCard
          content={`[方案设计] ${planContent}`}
          selectable
          selectedIndex={selectedPlan}
          onSelect={setSelectedPlan}
        />
      )}

      <div className="flex gap-3 pt-2 border-t border-gray-100">
        <button
          onClick={() => onRespond({ action: 'select', plan_index: selectedPlan })}
          disabled={selectedPlan === null}
          className={`flex-1 px-4 py-2.5 text-sm font-medium rounded-lg transition-all ${
            selectedPlan !== null
              ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-sm'
              : 'bg-gray-200 text-gray-400 cursor-not-allowed'
          }`}
        >
          {selectedPlan !== null ? `确认选择方案 ${String.fromCharCode(65 + selectedPlan)}` : '请先点击上方卡片选择'}
        </button>
        <button
          onClick={() => onRespond({ action: 'auto_select' })}
          className="px-4 py-2.5 bg-white hover:bg-gray-50 border border-gray-200 text-sm text-gray-600 rounded-lg transition-colors"
        >
          自动选最佳
        </button>
        <button
          onClick={() => setMode(mode === 'chat' ? 'select' : 'chat')}
          className={`px-4 py-2.5 border text-sm rounded-lg transition-colors ${
            mode === 'chat' ? 'bg-blue-100 border-blue-300 text-blue-700' : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
          }`}
        >
          我有意见
        </button>
      </div>

      {mode === 'chat' && (
        <div className="flex gap-2">
          <input
            type="text"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="输入你对方案的调整意见..."
            className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && feedback.trim()) {
                onRespond({ action: 'chat', message: feedback });
                setFeedback('');
              }
            }}
          />
          <button
            onClick={() => {
              if (feedback.trim()) {
                onRespond({ action: 'chat', message: feedback });
                setFeedback('');
              }
            }}
            disabled={!feedback.trim()}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-300 text-white text-sm rounded-lg transition-colors"
          >
            发送
          </button>
        </div>
      )}
    </div>
  );
}


function ResolutionDecisionCard({
  interruptData,
  onRespond,
}: {
  interruptData: InterruptData;
  onRespond: (response: Record<string, unknown>) => void;
}) {
  const unresolved = (interruptData.unresolved_issues ?? []) as Array<Record<string, string>>;
  const retryCount = interruptData.retry_count ?? 0;
  const [extraContext, setExtraContext] = useState('');

  return (
    <div className="rounded-xl border-2 border-amber-300 bg-amber-50 p-5 space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-xl">🤔</span>
        <h3 className="text-sm font-bold text-amber-700">需要你的决定</h3>
        <span className="text-xs text-amber-500">已重试 {retryCount} 次</span>
      </div>

      {unresolved.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-gray-600">以下 {unresolved.length} 个问题仍未解决：</p>
          {unresolved.map((item, i) => (
            <div key={i} className="bg-white rounded-lg border border-amber-200 px-3 py-2">
              <p className="text-xs font-medium text-amber-700">{item.issue}</p>
              <p className="text-xs text-gray-500 mt-0.5">影响: {item.impact}</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <button
          onClick={() => onRespond({ action: 'accept' })}
          className="w-full px-4 py-2.5 bg-green-600 hover:bg-green-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          接受当前结果
        </button>
        <div className="flex gap-2">
          <input
            type="text"
            value={extraContext}
            onChange={(e) => setExtraContext(e.target.value)}
            placeholder="补充上下文信息帮助修复..."
            className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400"
          />
          <button
            onClick={() => onRespond({ action: 'retry_with_context', context: extraContext })}
            className="px-4 py-2.5 bg-amber-600 hover:bg-amber-500 text-white text-sm rounded-lg transition-colors whitespace-nowrap"
          >
            重试
          </button>
        </div>
        <button
          onClick={() => onRespond({ action: 'stop' })}
          className="w-full px-4 py-2.5 bg-white hover:bg-gray-50 border border-gray-200 text-sm text-gray-600 rounded-lg transition-colors"
        >
          停止，手动修复
        </button>
      </div>
    </div>
  );
}
