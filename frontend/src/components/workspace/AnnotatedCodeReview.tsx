import { useCallback, useEffect, useRef, useState } from 'react';
import { AGENT_LABELS } from '../../types/debate';

interface Finding {
  agent: string;
  category: string;
  severity: string;
  description: string;
  test_input?: string;
  line_start?: number;
  line_end?: number;
}

interface CoderResponse {
  finding_ref: string;
  action: string;
  explanation: string;
  evidence?: string;
}

interface SatisfiedEntry {
  agent: string;
  message: string;
  anchorLine?: number;
}

interface Props {
  code: string;
  language: string;
  findings: Finding[];
  coderResponses: CoderResponse[];
  round: number;
  coderFixedLines?: Set<number>;
  satisfiedEntries?: SatisfiedEntry[];
  allSatisfied?: boolean;
}

const AGENT_BORDER_COLORS: Record<string, string> = {
  security: 'border-[#fecaca]',
  performance: 'border-[#fed7aa]',
  correctness: 'border-[#bbf7d0]',
};

const AGENT_TEXT_COLORS: Record<string, string> = {
  security: 'text-red-600',
  performance: 'text-orange-600',
  correctness: 'text-green-600',
};

const AGENT_DOT_CSS: Record<string, string> = {
  security: '#ef4444',
  performance: '#f97316',
  correctness: '#22c55e',
  satisfied: '#22c55e',
};

const SEVERITY_STYLES: Record<string, string> = {
  critical: 'bg-red-100 text-red-700',
  high: 'bg-red-100 text-red-600',
  medium: 'bg-orange-100 text-orange-700',
  low: 'bg-gray-100 text-gray-600',
};

const AGENT_ICONS: Record<string, string> = {
  security: '\u{1F512}',
  performance: '⚡',
  correctness: '✔',
};

function matchResponseToFinding(
  finding: Finding, fIdx: number, agentFindingIdx: number,
  responses: CoderResponse[],
): CoderResponse | null {
  // Layer 1: exact AGENT-NNN format
  const ref = `${finding.agent.toUpperCase()}-${String(agentFindingIdx + 1).padStart(3, '0')}`;
  const exact = responses.find(r => (r.finding_ref ?? '').toUpperCase() === ref);
  if (exact) return exact;

  // Layer 2: fuzzy — finding_ref contains agent name + category keyword
  const agentLower = finding.agent.toLowerCase();
  const catLower = (finding.category || '').toLowerCase().replace(/[_\s]+/g, '');
  const fuzzy = responses.find(r => {
    const rRef = (r.finding_ref || '').toLowerCase().replace(/[_\s]+/g, '');
    return rRef.includes(agentLower) && catLower && (rRef.includes(catLower) || catLower.includes(rRef.replace(agentLower, '').replace(/[-_]/g, '')));
  });
  if (fuzzy) return fuzzy;

  // Layer 3: positional — Nth response for this agent matches Nth finding for this agent
  const agentResps = responses.filter(r => (r.finding_ref || '').toLowerCase().includes(agentLower));
  if (agentResps[agentFindingIdx]) return agentResps[agentFindingIdx];

  return null;
}

export default function AnnotatedCodeReview({
  code, findings, coderResponses, coderFixedLines,
  satisfiedEntries, allSatisfied,
}: Props) {
  const [fontSize, setFontSize] = useState(12);
  const [openAnns, setOpenAnns] = useState<Set<number>>(() => new Set(findings.length > 0 ? [0] : []));
  const [copied, setCopied] = useState(false);
  const codeColRef = useRef<HTMLDivElement>(null);
  const annColRef = useRef<HTMLDivElement>(null);

  const hasFindings = findings.length > 0;
  const isReviewRound = !hasFindings && (satisfiedEntries?.length ?? 0) > 0;

  const toggleAnn = useCallback((idx: number) => {
    setOpenAnns(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }, []);

  const copyCode = useCallback(() => {
    const normalized = code.replace(/\\n/g, '\n').replace(/\\t/g, '\t').replace(/\\"/g, '"');
    navigator.clipboard.writeText(normalized).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [code]);

  // Layout engine
  useEffect(() => {
    const layout = () => {
      const codeCol = codeColRef.current;
      const annCol = annColRef.current;
      if (!codeCol || !annCol) return;

      const annCards = annCol.querySelectorAll<HTMLElement>('[data-ann-idx]');
      annCol.querySelectorAll<HTMLElement>('.conn-el').forEach(c => c.remove());

      const codeRect = codeCol.getBoundingClientRect();
      let prevBottom = 0;
      const GAP = 6;

      annCards.forEach(card => {
        const idx = parseInt(card.dataset.annIdx!);
        const anchorLine = parseInt(card.dataset.anchor ?? '1');
        const lineEl = codeCol.querySelector(`[data-ln="${anchorLine}"]`);
        if (!lineEl) {
          card.style.top = `${prevBottom + GAP}px`;
          prevBottom = prevBottom + GAP + card.getBoundingClientRect().height;
          return;
        }

        const lineRect = lineEl.getBoundingClientRect();
        const idealTop = lineRect.top - codeRect.top;
        const actualTop = Math.max(idealTop, prevBottom + GAP);
        card.style.top = `${actualTop}px`;
        prevBottom = actualTop + card.getBoundingClientRect().height;

        const agentType = card.dataset.agentType ?? 'correctness';
        const color = AGENT_DOT_CSS[agentType] ?? '#9ca3af';
        const bridgeY = idealTop + lineRect.height / 2;

        // Connector dot (6px per mockup)
        const dot = document.createElement('div');
        dot.className = 'conn-el';
        dot.style.cssText = `position:absolute;left:-1px;top:${bridgeY - 3}px;width:6px;height:6px;border-radius:50%;background:${color};pointer-events:none;`;
        annCol.appendChild(dot);

        // Horizontal bridge
        const bridge = document.createElement('div');
        bridge.className = 'conn-el';
        bridge.style.cssText = `position:absolute;left:0;top:${bridgeY}px;width:8px;height:1.5px;background:${color};pointer-events:none;`;
        annCol.appendChild(bridge);

        // Vertical dashed line if pushed down
        if (actualTop > idealTop + 2) {
          const vLine = document.createElement('div');
          vLine.className = 'conn-el';
          vLine.style.cssText = `position:absolute;left:2px;top:${bridgeY}px;height:${actualTop - bridgeY + 10}px;border-left:1.5px dashed ${color};pointer-events:none;`;
          annCol.appendChild(vLine);
        }
      });

      if (prevBottom > 0) annCol.style.minHeight = `${prevBottom + 20}px`;
    };

    requestAnimationFrame(() => requestAnimationFrame(layout));
  }, [findings, satisfiedEntries, openAnns, fontSize]);

  const normalizedCode = code.replace(/\\n/g, '\n').replace(/\\t/g, '\t').replace(/\\"/g, '"');
  const codeLines = normalizedCode.split('\n');

  const allLineStartsWeak = findings.length > 1 && findings.every(f => !f.line_start || f.line_start <= 1);

  const highlightMap = new Map<number, string>();
  for (const f of findings) {
    let start = f.line_start;
    let end = f.line_end;

    const needsFallback = !start || (allLineStartsWeak && start <= 1);
    if (needsFallback && f.description && codeLines.length > 1) {
      const keywords = f.description.split(/[\s,;.()]+/).filter(w => w.length > 4);
      for (let li = 0; li < codeLines.length; li++) {
        const lineLower = codeLines[li].toLowerCase();
        if (keywords.some(kw => lineLower.includes(kw.toLowerCase()))) {
          start = li + 1;
          end = li + 1;
          break;
        }
      }
    }

    if (start && start > 0) {
      const s = start;
      const e = end || s;
      for (let i = s; i <= e; i++) highlightMap.set(i, f.agent);
    }
  }

  const hlClass = (agent: string) => {
    switch (agent) {
      case 'security': return 'border-l-[3px] border-l-[#ef4444] bg-[rgba(239,68,68,0.09)]';
      case 'performance': return 'border-l-[3px] border-l-[#f97316] bg-[rgba(249,115,22,0.09)]';
      case 'correctness': return 'border-l-[3px] border-l-[#22c55e] bg-[rgba(34,197,94,0.09)]';
      default: return '';
    }
  };
  const fixClass = 'border-l-[3px] border-l-[#3b82f6] bg-[rgba(59,130,246,0.07)]';

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-[5px] bg-[#f6f7f9] border-b border-[#eaedf0]">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[#8b8f96] font-medium">字号</span>
          <div className="flex items-center gap-[1px]">
            <button onClick={() => setFontSize(s => Math.max(10, s - 1))} className="w-5 h-5 border border-gray-300 bg-white rounded-[3px] text-xs flex items-center justify-center hover:bg-gray-100">-</button>
            <span className="text-[10px] text-[#888] min-w-[26px] text-center">{fontSize}px</span>
            <button onClick={() => setFontSize(s => Math.min(18, s + 1))} className="w-5 h-5 border border-gray-300 bg-white rounded-[3px] text-xs flex items-center justify-center hover:bg-gray-100">+</button>
          </div>
        </div>
        <button onClick={copyCode} className={`px-2 py-[3px] border rounded text-[10px] ${copied ? 'border-green-300 text-green-600' : 'border-[#d4d7dc] text-[#6b7280] hover:bg-[#f3f4f6]'}`}>
          {copied ? '✓ 已复制' : '📋 复制代码'}
        </button>
      </div>

      {/* Split view */}
      <div className="flex max-h-[520px] overflow-y-auto overflow-x-hidden border-b border-[#eaedf0]">
        {/* Code column — mockup: #fafbfc */}
        <div ref={codeColRef} className="flex-[0_0_62%] border-r border-[#eaedf0] bg-[#fafbfc] overflow-x-auto" style={{ fontSize: `${fontSize}px` }}>
          <pre className="m-0 py-2 font-mono text-[#1a1a1a]" style={{ fontFamily: "'SF Mono','Fira Code','Consolas',monospace" }}>
            {codeLines.map((line, i) => {
              const ln = i + 1;
              const hlAgent = highlightMap.get(ln);
              const isFixed = coderFixedLines?.has(ln);
              const lineStyle = hlAgent ? hlClass(hlAgent) : isFixed ? fixClass : '';
              return (
                <div key={ln} data-ln={ln} className={`flex pr-2.5 leading-[1.45] ${lineStyle}`}>
                  <span className="inline-block w-[30px] text-right pr-2.5 text-[#bbb] select-none shrink-0" style={{ fontSize: '0.82em' }}>{ln}</span>
                  <span className="whitespace-pre flex-1 px-[5px]">{line || ' '}</span>
                </div>
              );
            })}
          </pre>
        </div>

        {/* Annotation column */}
        <div ref={annColRef} className="flex-[0_0_38%] relative min-h-full" style={{ fontSize: `${fontSize}px` }}>
          {!hasFindings && !isReviewRound && (
            <div className="absolute inset-0 flex items-center justify-center text-gray-300 text-xs">无审查批注</div>
          )}

          {/* Normal findings (Round 1 style) */}
          {(() => {
            const agentCounters: Record<string, number> = {};
            return findings.map((f, idx) => {
            const agentIdx = agentCounters[f.agent] ?? 0;
            agentCounters[f.agent] = agentIdx + 1;
            const borderColor = AGENT_BORDER_COLORS[f.agent] ?? 'border-gray-200';
            const textColor = AGENT_TEXT_COLORS[f.agent] ?? 'text-gray-700';
            const isOpen = openAnns.has(idx);
            const resp = matchResponseToFinding(f, idx, agentIdx, coderResponses);
            const icon = AGENT_ICONS[f.agent] ?? '•';

            return (
              <div
                key={`f-${idx}`}
                data-ann-idx={idx}
                data-anchor={f.line_start ?? 1}
                data-agent-type={f.agent}
                className={`absolute left-2 right-2 rounded-[7px] border ${borderColor} bg-white shadow-sm cursor-pointer hover:shadow-md transition-shadow`}
              >
                <div className="flex items-center gap-[5px] px-2 py-[6px]" onClick={() => toggleAnn(idx)}>
                  <span style={{ fontSize: '1em' }}>{icon}</span>
                  <span className={`font-bold ${textColor}`} style={{ fontSize: '0.92em' }}>{AGENT_LABELS[f.agent] ?? f.agent}</span>
                  <span className={`px-1 rounded-[3px] font-bold ${SEVERITY_STYLES[f.severity] ?? 'bg-gray-100 text-gray-600'}`} style={{ fontSize: '0.75em' }}>{f.severity?.toUpperCase()}</span>
                  <span className="text-[#374151] font-semibold truncate flex-1" style={{ fontSize: '0.92em' }}>{f.category}</span>
                  {resp && (
                    <span className={`px-[5px] rounded-[3px] font-bold ${resp.action === 'accept_and_fix' ? 'bg-green-100 text-green-700' : 'bg-[#fef3c7] text-[#92400e]'}`} style={{ fontSize: '0.75em' }}>
                      {resp.action === 'accept_and_fix' ? '✓ 修复' : '✗ 反驳'}
                    </span>
                  )}
                  <span className={`text-[#aaa] transition-transform ${isOpen ? 'rotate-180' : ''}`} style={{ fontSize: '0.75em' }}>▼</span>
                </div>

                {isOpen && (
                  <div className="px-2 pb-[7px] border-t border-[#f0f0f0]">
                    <p className="text-[#555] leading-relaxed my-1" style={{ fontSize: '0.92em' }}>{f.description}</p>
                    {f.test_input && (
                      <div className="px-1.5 py-0.5 bg-[#f9fafb] border border-[#eee] rounded font-mono text-[#777] my-1" style={{ fontSize: '0.85em' }}>
                        💻 <code>{f.test_input}</code>
                      </div>
                    )}
                    {resp && (
                      <div className={`mt-[5px] px-[7px] py-[5px] rounded-[5px] flex items-start gap-[5px] ${
                        resp.action === 'accept_and_fix' ? 'bg-[#f0fdf4] border border-[#bbf7d0]' : 'bg-[#fffbeb] border border-[#fde68a]'
                      }`}>
                        <span className={`px-[5px] rounded-[3px] font-bold whitespace-nowrap ${
                          resp.action === 'accept_and_fix' ? 'bg-green-100 text-green-700' : 'bg-[#fef3c7] text-[#92400e]'
                        }`} style={{ fontSize: '0.75em' }}>
                          {resp.action === 'accept_and_fix' ? '✓ Coder' : '✗ Coder'}
                        </span>
                        <span className="text-[#555] leading-snug" style={{ fontSize: '0.92em' }}>
                          {resp.explanation}
                          {resp.evidence && (
                            <code className="block mt-1 px-1 py-0.5 bg-[#e5e7eb] rounded text-[#555]" style={{ fontSize: '0.92em' }}>{resp.evidence}</code>
                          )}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          });
          })()}

          {/* Satisfied entries (Round 2 style — green, no expand) */}
          {satisfiedEntries?.map((s, idx) => {
            const icon = AGENT_ICONS[s.agent] ?? '✔';
            const anchorLine = s.anchorLine ?? (1 + idx * 6);

            return (
              <div
                key={`s-${idx}`}
                data-ann-idx={findings.length + idx}
                data-anchor={anchorLine}
                data-agent-type="satisfied"
                className="absolute left-2 right-2 rounded-[7px] border border-[#bbf7d0] bg-white shadow-sm"
                style={{ cursor: 'default' }}
              >
                <div className="flex items-center gap-[5px] px-2 py-[6px]">
                  <span style={{ fontSize: '1em' }}>{icon}</span>
                  <span className="font-bold text-green-600" style={{ fontSize: '0.92em' }}>{AGENT_LABELS[s.agent] ?? s.agent}</span>
                  <span className="px-1 rounded-[3px] font-bold bg-green-100 text-green-600" style={{ fontSize: '0.75em' }}>✓</span>
                  <span className="text-green-600 font-semibold truncate flex-1" style={{ fontSize: '0.92em' }}>{s.message}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Consensus bar (only when all satisfied) */}
      {allSatisfied && (
        <div className="flex items-center gap-[5px] px-4 py-2 bg-[#f0fdf4] border-t border-[#bbf7d0] text-[11px] text-green-700 font-medium">
          ✅ 所有 Attacker 通过 — 共识达成
        </div>
      )}

      {/* Legend — context-aware */}
      <div className="flex gap-3 px-3 py-[7px] bg-[#fafbfc] border-t border-[#eaedf0]">
        {hasFindings && (
          <>
            <div className="flex items-center gap-1 text-[9px] text-[#888]"><div className="w-2 h-[3px] rounded bg-[#ef4444]" />Security</div>
            <div className="flex items-center gap-1 text-[9px] text-[#888]"><div className="w-2 h-[3px] rounded bg-[#f97316]" />Performance</div>
            <div className="flex items-center gap-1 text-[9px] text-[#888]"><div className="w-2 h-[3px] rounded bg-[#22c55e]" />Correctness</div>
          </>
        )}
        {coderFixedLines && coderFixedLines.size > 0 && (
          <div className="flex items-center gap-1 text-[9px] text-[#888]"><div className="w-2 h-[3px] rounded bg-[#3b82f6]" />✎ Coder 修改</div>
        )}
        {hasFindings && <span className="ml-auto text-[9px] text-[#aaa]">点击批注展开详情</span>}
      </div>
    </div>
  );
}
