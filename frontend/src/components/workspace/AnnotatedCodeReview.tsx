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

interface Props {
  code: string;
  language: string;
  findings: Finding[];
  coderResponses: CoderResponse[];
  round: number;
  coderFixedLines?: Set<number>;
}

const AGENT_COLORS: Record<string, { border: string; bg: string; text: string; dot: string }> = {
  security:    { border: 'border-red-200',    bg: 'bg-red-50',    text: 'text-red-700',    dot: 'bg-red-500' },
  performance: { border: 'border-orange-200', bg: 'bg-orange-50', text: 'text-orange-700', dot: 'bg-orange-500' },
  correctness: { border: 'border-green-200',  bg: 'bg-green-50',  text: 'text-green-700',  dot: 'bg-green-500' },
};

const SEVERITY_STYLES: Record<string, string> = {
  critical: 'bg-red-100 text-red-700',
  high:     'bg-red-100 text-red-600',
  medium:   'bg-orange-100 text-orange-700',
  low:      'bg-gray-100 text-gray-600',
};

const AGENT_ICONS: Record<string, string> = {
  security: '\u{1F512}',
  performance: '⚡',
  correctness: '✔',
};

function matchResponseToFinding(finding: Finding, fIdx: number, responses: CoderResponse[]): CoderResponse | null {
  const ref = `${finding.agent.toUpperCase()}-${String(fIdx + 1).padStart(3, '0')}`;
  return responses.find(r => (r.finding_ref ?? '').toUpperCase() === ref) ?? null;
}

export default function AnnotatedCodeReview({ code, findings, coderResponses, coderFixedLines }: Props) {
  const [fontSize, setFontSize] = useState(12);
  const [openAnns, setOpenAnns] = useState<Set<number>>(() => new Set(findings.length > 0 ? [0] : []));
  const [copied, setCopied] = useState(false);
  const codeColRef = useRef<HTMLDivElement>(null);
  const annColRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const toggleAnn = useCallback((idx: number) => {
    setOpenAnns(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }, []);

  const copyCode = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [code]);

  // Layout engine: position annotations to align with anchor code lines
  useEffect(() => {
    const layout = () => {
      const codeCol = codeColRef.current;
      const annCol = annColRef.current;
      if (!codeCol || !annCol) return;

      const annCards = annCol.querySelectorAll<HTMLElement>('[data-ann-idx]');
      const connectors = annCol.querySelectorAll<HTMLElement>('.conn-element');
      connectors.forEach(c => c.remove());

      const codeRect = codeCol.getBoundingClientRect();
      let prevBottom = 0;
      const GAP = 6;

      annCards.forEach(card => {
        const idx = parseInt(card.dataset.annIdx!);
        const finding = findings[idx];
        if (!finding) return;

        const anchorLine = finding.line_start ?? 1;
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

        const cardHeight = card.getBoundingClientRect().height;
        prevBottom = actualTop + cardHeight;

        // Draw connector dot at anchor level
        const bridgeY = idealTop + lineRect.height / 2;
        const colors = AGENT_COLORS[finding.agent];
        const dotColor = colors?.dot ?? 'bg-gray-400';

        const dot = document.createElement('div');
        dot.className = `conn-element absolute w-1.5 h-1.5 rounded-full ${dotColor}`;
        dot.style.cssText = `position:absolute;left:-1px;top:${bridgeY - 3}px;width:6px;height:6px;border-radius:50%;`;
        annCol.appendChild(dot);

        // Horizontal bridge
        const bridge = document.createElement('div');
        bridge.className = 'conn-element';
        bridge.style.cssText = `position:absolute;left:0;top:${bridgeY}px;width:8px;height:1.5px;background:${getAgentCSSColor(finding.agent)};`;
        annCol.appendChild(bridge);

        // Vertical dashed line if pushed down
        if (actualTop > idealTop + 2) {
          const vLine = document.createElement('div');
          vLine.className = 'conn-element';
          vLine.style.cssText = `position:absolute;left:2px;top:${bridgeY}px;height:${actualTop - bridgeY + 8}px;border-left:1.5px dashed ${getAgentCSSColor(finding.agent)};`;
          annCol.appendChild(vLine);
        }
      });

      if (prevBottom > 0) {
        annCol.style.minHeight = `${prevBottom + 20}px`;
      }
    };

    // Double RAF for stable layout after DOM changes
    requestAnimationFrame(() => {
      requestAnimationFrame(layout);
    });
  }, [findings, openAnns, fontSize]);

  const codeLines = code.split('\n');

  // Build highlight map: line number -> agent
  const highlightMap = new Map<number, string>();
  for (const f of findings) {
    if (f.line_start && f.line_end) {
      for (let i = f.line_start; i <= f.line_end; i++) {
        highlightMap.set(i, f.agent);
      }
    }
  }

  const hlBorderClass = (agent: string) => {
    switch (agent) {
      case 'security': return 'border-l-[3px] border-l-red-400 bg-red-500/[0.08]';
      case 'performance': return 'border-l-[3px] border-l-orange-400 bg-orange-500/[0.08]';
      case 'correctness': return 'border-l-[3px] border-l-green-400 bg-green-500/[0.08]';
      default: return '';
    }
  };

  const fixedLineClass = 'border-l-[3px] border-l-blue-400 bg-blue-500/[0.06]';

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-500 font-medium">字号</span>
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => setFontSize(s => Math.max(10, s - 1))}
              className="w-5 h-5 border border-gray-300 bg-white rounded text-xs flex items-center justify-center hover:bg-gray-100"
            >-</button>
            <span className="text-[10px] text-gray-500 min-w-[26px] text-center">{fontSize}px</span>
            <button
              onClick={() => setFontSize(s => Math.min(18, s + 1))}
              className="w-5 h-5 border border-gray-300 bg-white rounded text-xs flex items-center justify-center hover:bg-gray-100"
            >+</button>
          </div>
        </div>
        <button
          onClick={copyCode}
          className={`px-2 py-0.5 border rounded text-[10px] flex items-center gap-1 ${
            copied ? 'border-green-300 text-green-600' : 'border-gray-300 text-gray-500 hover:bg-gray-100'
          }`}
        >
          {copied ? '✓ 已复制' : '\u{1F4CB} 复制代码'}
        </button>
      </div>

      {/* Main split view: code + annotations */}
      <div ref={containerRef} className="flex max-h-[520px] overflow-y-auto overflow-x-hidden">
        {/* Code column */}
        <div
          ref={codeColRef}
          className="flex-[0_0_62%] border-r border-gray-200 bg-[#fafbfc] overflow-x-auto"
          style={{ fontSize: `${fontSize}px` }}
        >
          <pre className="m-0 py-1.5 font-mono">
            {codeLines.map((line, i) => {
              const ln = i + 1;
              const hlAgent = highlightMap.get(ln);
              const isFixed = coderFixedLines?.has(ln);
              const lineClass = hlAgent ? hlBorderClass(hlAgent) : isFixed ? fixedLineClass : '';
              return (
                <div
                  key={ln}
                  data-ln={ln}
                  className={`flex pr-2.5 leading-[1.45] ${lineClass}`}
                >
                  <span
                    className="inline-block w-[30px] text-right pr-2.5 text-gray-400 select-none shrink-0"
                    style={{ fontSize: '0.82em' }}
                  >{ln}</span>
                  <span className="whitespace-pre flex-1 px-1">{line || ' '}</span>
                </div>
              );
            })}
          </pre>
        </div>

        {/* Annotation column */}
        <div
          ref={annColRef}
          className="flex-[0_0_38%] relative min-h-full"
          style={{ fontSize: `${fontSize}px` }}
        >
          {findings.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center text-gray-300 text-xs">
              无审查批注
            </div>
          )}
          {findings.map((f, idx) => {
            const colors = AGENT_COLORS[f.agent] ?? { border: 'border-gray-200', bg: 'bg-gray-50', text: 'text-gray-700' };
            const isOpen = openAnns.has(idx);
            const resp = matchResponseToFinding(f, idx, coderResponses);
            const icon = AGENT_ICONS[f.agent] ?? '•';

            return (
              <div
                key={idx}
                data-ann-idx={idx}
                className={`absolute left-2 right-2 rounded-lg border ${colors.border} bg-white shadow-sm cursor-pointer hover:shadow-md transition-shadow`}
              >
                {/* Summary header — always visible */}
                <div
                  className="flex items-center gap-1 px-2 py-1.5"
                  onClick={() => toggleAnn(idx)}
                >
                  <span style={{ fontSize: '1em' }}>{icon}</span>
                  <span className={`font-bold ${colors.text}`} style={{ fontSize: '0.92em' }}>
                    {AGENT_LABELS[f.agent] ?? f.agent}
                  </span>
                  <span className={`px-1 rounded text-[0.72em] font-bold ${SEVERITY_STYLES[f.severity] ?? 'bg-gray-100 text-gray-600'}`}>
                    {f.severity?.toUpperCase()}
                  </span>
                  <span className="text-gray-700 font-semibold truncate flex-1" style={{ fontSize: '0.92em' }}>
                    {f.category}
                  </span>
                  {resp && (
                    <span className={`px-1 rounded text-[0.72em] font-bold ${
                      resp.action === 'accept_and_fix'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-yellow-100 text-yellow-700'
                    }`}>
                      {resp.action === 'accept_and_fix' ? '✓ 修复' : '✗ 反驳'}
                    </span>
                  )}
                  <span className={`text-gray-400 text-[0.72em] transition-transform ${isOpen ? 'rotate-180' : ''}`}>
                    ▼
                  </span>
                </div>

                {/* Detail body — expandable */}
                {isOpen && (
                  <div className="px-2 pb-2 border-t border-gray-100">
                    <p className="text-gray-600 leading-relaxed my-1" style={{ fontSize: '0.92em' }}>
                      {f.description}
                    </p>
                    {f.test_input && (
                      <div className="px-1.5 py-0.5 bg-gray-50 border border-gray-200 rounded font-mono text-gray-500 my-1" style={{ fontSize: '0.85em' }}>
                        test: <code>{f.test_input}</code>
                      </div>
                    )}
                    {resp && (
                      <div className={`mt-1.5 px-2 py-1.5 rounded-md flex items-start gap-1 ${
                        resp.action === 'accept_and_fix'
                          ? 'bg-green-50 border border-green-200'
                          : 'bg-yellow-50 border border-yellow-200'
                      }`}>
                        <span className={`px-1 rounded font-bold whitespace-nowrap ${
                          resp.action === 'accept_and_fix'
                            ? 'bg-green-100 text-green-700'
                            : 'bg-yellow-100 text-yellow-700'
                        }`} style={{ fontSize: '0.72em' }}>
                          {resp.action === 'accept_and_fix' ? '✓ Coder' : '✗ Coder'}
                        </span>
                        <span className="text-gray-600 leading-snug" style={{ fontSize: '0.92em' }}>
                          {resp.explanation}
                          {resp.evidence && (
                            <code className="block mt-1 px-1 py-0.5 bg-white border border-gray-200 rounded text-gray-600" style={{ fontSize: '0.88em' }}>
                              {resp.evidence}
                            </code>
                          )}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Legend */}
      <div className="flex gap-3 px-3 py-1.5 bg-gray-50 border-t border-gray-200">
        <div className="flex items-center gap-1 text-[9px] text-gray-500">
          <div className="w-2 h-0.5 rounded bg-red-500" />Security
        </div>
        <div className="flex items-center gap-1 text-[9px] text-gray-500">
          <div className="w-2 h-0.5 rounded bg-orange-500" />Performance
        </div>
        <div className="flex items-center gap-1 text-[9px] text-gray-500">
          <div className="w-2 h-0.5 rounded bg-green-500" />Correctness
        </div>
        {coderFixedLines && coderFixedLines.size > 0 && (
          <div className="flex items-center gap-1 text-[9px] text-gray-500">
            <div className="w-2 h-0.5 rounded bg-blue-500" />✎ Coder 修改
          </div>
        )}
        <span className="ml-auto text-[9px] text-gray-400">点击批注展开详情</span>
      </div>
    </div>
  );
}

function getAgentCSSColor(agent: string): string {
  switch (agent) {
    case 'security': return '#f87171';
    case 'performance': return '#fb923c';
    case 'correctness': return '#4ade80';
    default: return '#9ca3af';
  }
}
