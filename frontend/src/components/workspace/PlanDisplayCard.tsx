import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Props {
  content: string;
  selectable?: boolean;
  selectedIndex?: number | null;
  onSelect?: (index: number) => void;
}

interface PlanSection {
  label: string;
  techStack: string[];
  operations: Array<{ op: string; impl: string }>;
  security: string[];
  excluded: string[];
  bodyText: string;
}

function parsePlans(raw: string): { intro: string; plans: PlanSection[]; comparison: string } {
  const cleaned = raw.replace(/^\[方案设计\]\s*/i, '');

  const planPattern = /(?:^|\n)(?:#{1,3}\s*)?(?:方案\s*[A-Za-z]|Plan\s*[A-Za-z])[：:：\s]/gi;
  const matches = [...cleaned.matchAll(planPattern)];

  const comparisonMatch = cleaned.match(/(?:^|\n)#{1,3}\s*方案对比[\s\S]*/m);
  const comparisonText = comparisonMatch ? comparisonMatch[0].trim() : '';
  const contentWithoutComparison = comparisonMatch
    ? cleaned.slice(0, comparisonMatch.index).trim()
    : cleaned;

  const intro = matches.length >= 2
    ? contentWithoutComparison.slice(0, matches[0].index).trim()
    : '';

  const plans: PlanSection[] = [];

  if (matches.length >= 2) {
    for (let i = 0; i < matches.length; i++) {
      const start = matches[i].index!;
      const end = i + 1 < matches.length
        ? matches[i + 1].index!
        : (comparisonMatch ? comparisonMatch.index! : contentWithoutComparison.length);
      const chunk = contentWithoutComparison.slice(start, end).trim();
      const firstLine = chunk.split('\n')[0].replace(/^#{1,3}\s*/, '').trim();
      const body = chunk.split('\n').slice(1).join('\n').trim();
      plans.push(parseSinglePlan(firstLine, body));
    }
  } else {
    plans.push(parseSinglePlan('方案', contentWithoutComparison));
  }

  return { intro, plans, comparison: comparisonText };
}

function parseSinglePlan(label: string, body: string): PlanSection {
  const techStack: string[] = [];
  const operations: Array<{ op: string; impl: string }> = [];
  const security: string[] = [];
  const excluded: string[] = [];

  const techMatch = body.match(/(?:技术选型|技术方案)[\s\S]*?(?=\n#{2,3}\s|\n---|\n\*\*[^*]+\*\*|$)/i);
  if (techMatch) {
    const lines = techMatch[0].split('\n').slice(1);
    for (const line of lines) {
      const cleaned = line.replace(/^[-*•]\s*/, '').replace(/\*\*/g, '').trim();
      if (cleaned && !cleaned.startsWith('#')) techStack.push(cleaned);
    }
  }

  const tableRegex = /\|\s*操作\s*\|[\s\S]*?(?=\n\n|\n#{2,3}|\n\*\*|$)/i;
  const tableMatch = body.match(tableRegex);
  if (tableMatch) {
    const rows = tableMatch[0].split('\n').filter((l) => l.includes('|') && !l.match(/^[\s|:-]+$/));
    for (const row of rows.slice(1)) {
      const cells = row.split('|').map((c) => c.trim()).filter(Boolean);
      if (cells.length >= 2) {
        operations.push({ op: cells[0].replace(/`/g, ''), impl: cells[1].replace(/`/g, '') });
      }
    }
  }

  const secMatch = body.match(/安全考虑[\s\S]*?(?=\n#{2,3}\s|\n\*\*不包含|\n---|\n\n#{2,3}|$)/i);
  if (secMatch) {
    const lines = secMatch[0].split('\n').slice(1);
    for (const line of lines) {
      const cleaned = line.replace(/^[-*•]\s*/, '').replace(/\*\*/g, '').trim();
      if (cleaned && !cleaned.startsWith('#')) security.push(cleaned);
    }
  }

  const exclMatch = body.match(/不包含什么[\s\S]*?(?=\n#{2,3}\s|\n---|\n\n#{2,3}|$)/i);
  if (exclMatch) {
    const lines = exclMatch[0].split('\n').slice(1);
    for (const line of lines) {
      const cleaned = line.replace(/^[-*•✗✕×]\s*/, '').replace(/\*\*/g, '').trim();
      if (cleaned && !cleaned.startsWith('#')) excluded.push(cleaned);
    }
  }

  return {
    label: label.replace(/^[#\d\.\)、一二三四五\s]+/, '').trim() || '方案',
    techStack,
    operations,
    security,
    excluded,
    bodyText: body,
  };
}

const PLAN_THEMES = [
  { border: 'border-blue-300', bg: 'bg-blue-50', accent: 'text-blue-700', badge: 'bg-blue-100 text-blue-700', selectedRing: 'ring-blue-400', icon: 'A', gradient: 'from-blue-500 to-blue-600' },
  { border: 'border-emerald-300', bg: 'bg-emerald-50', accent: 'text-emerald-700', badge: 'bg-emerald-100 text-emerald-700', selectedRing: 'ring-emerald-400', icon: 'B', gradient: 'from-emerald-500 to-emerald-600' },
  { border: 'border-purple-300', bg: 'bg-purple-50', accent: 'text-purple-700', badge: 'bg-purple-100 text-purple-700', selectedRing: 'ring-purple-400', icon: 'C', gradient: 'from-purple-500 to-purple-600' },
];

export default function PlanDisplayCard({ content, selectable, selectedIndex, onSelect }: Props) {
  const { intro, plans, comparison } = parsePlans(content);
  const [showFallback, setShowFallback] = useState<number | null>(null);
  const adoptedIndex = selectable ? selectedIndex : 0;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
          <span className="text-white text-sm">💡</span>
        </div>
        <div>
          <h3 className="text-sm font-bold text-gray-800">方案设计</h3>
          <span className="text-xs text-gray-500">Coder 为你准备了 {plans.length} 个方案</span>
        </div>
      </div>

      {intro && <p className="text-xs text-gray-400">{intro}</p>}

      {/* Plan cards */}
      <div className={`grid gap-4 ${plans.length > 1 ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1'}`}>
        {plans.map((plan, i) => {
          const theme = PLAN_THEMES[i % PLAN_THEMES.length];
          const isSelected = selectable ? selectedIndex === i : false;
          const isAdopted = !selectable && adoptedIndex === i;

          return (
            <div
              key={i}
              onClick={() => selectable && onSelect?.(i)}
              className={`
                rounded-xl border-2 overflow-hidden transition-all duration-300
                ${selectable ? 'cursor-pointer hover:shadow-lg' : ''}
                ${isSelected || isAdopted
                  ? `${theme.border} ${theme.selectedRing} ring-2 shadow-lg scale-[1.02]`
                  : (selectedIndex !== null && selectable) || (!selectable && plans.length > 1)
                    ? `border-gray-200 opacity-60`
                    : `${theme.border} border-opacity-50`
                }
              `}
            >
              {/* Plan header */}
              <div className={`bg-gradient-to-r ${theme.gradient} px-4 py-3 flex items-center justify-between`}>
                <div className="flex items-center gap-2">
                  <span className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center text-white text-sm font-bold">
                    {theme.icon}
                  </span>
                  <span className="text-white font-semibold text-sm">{plan.label}</span>
                </div>
                {selectable && isSelected && (
                  <span className="px-2.5 py-1 bg-white rounded-full text-xs font-bold text-green-600 shadow-sm animate-pulse">
                    ✅ 已选择
                  </span>
                )}
                {selectable && !isSelected && (
                  <span className="px-2.5 py-1 bg-white/20 rounded-full text-xs text-white/80">
                    点击选择
                  </span>
                )}
                {isAdopted && (
                  <span className="px-2.5 py-1 bg-white rounded-full text-xs font-bold text-green-600 shadow-sm">
                    ✅ 已采用
                  </span>
                )}
              </div>

              <div className={`${theme.bg} p-4 space-y-3`}>
                {/* Tech stack tags */}
                {plan.techStack.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 mb-2">技术选型</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {plan.techStack.map((tech, j) => (
                        <span key={j} className={`text-xs px-2 py-1 rounded-full ${theme.badge} font-medium`}>
                          {tech.split('：')[0]}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Operations flow */}
                {plan.operations.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 mb-2">核心操作</h4>
                    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-gray-50">
                            <th className="px-3 py-1.5 text-left font-semibold text-gray-600">操作</th>
                            <th className="px-3 py-1.5 text-left font-semibold text-gray-600">实现</th>
                          </tr>
                        </thead>
                        <tbody>
                          {plan.operations.map((op, j) => (
                            <tr key={j} className={j % 2 === 0 ? '' : 'bg-gray-50/50'}>
                              <td className="px-3 py-1.5 font-mono text-blue-600 whitespace-nowrap">{op.op}</td>
                              <td className="px-3 py-1.5 text-gray-600">{op.impl}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Security considerations */}
                {plan.security.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 mb-1.5">安全设计</h4>
                    <div className="space-y-1">
                      {plan.security.map((item, j) => (
                        <div key={j} className="flex items-start gap-1.5 text-xs text-gray-600">
                          <span className="text-green-500 mt-0.5 shrink-0">🛡️</span>
                          <span>{item}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Excluded features */}
                {plan.excluded.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 mb-1.5">不包含</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {plan.excluded.map((item, j) => (
                        <span key={j} className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-500">
                          {item.replace(/^✗\s*/, '')}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Fallback: show full markdown if parsing missed content */}
                {plan.techStack.length === 0 && plan.operations.length === 0 && (
                  <div className="text-xs text-gray-600 prose prose-xs max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{plan.bodyText}</ReactMarkdown>
                  </div>
                )}

                {/* Toggle raw markdown */}
                {(plan.techStack.length > 0 || plan.operations.length > 0) && (
                  <button
                    onClick={(e) => { e.stopPropagation(); setShowFallback(showFallback === i ? null : i); }}
                    className="text-xs text-gray-400 hover:text-gray-500"
                  >
                    {showFallback === i ? '收起详情' : '查看完整描述'}
                  </button>
                )}
                {showFallback === i && (
                  <div className="text-xs text-gray-600 prose prose-xs max-w-none border-t border-gray-200 pt-2 mt-2">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{plan.bodyText}</ReactMarkdown>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Comparison table */}
      {comparison && <ComparisonTable markdown={comparison} />}

    </div>
  );
}


function ComparisonTable({ markdown }: { markdown: string }) {
  const lines = markdown.split('\n').filter((l) => l.includes('|'));
  const dataRows = lines.filter((l) => !l.match(/^[\s|:-]+$/));
  if (dataRows.length < 2) return null;

  const parseRow = (line: string) =>
    line.split('|').map((c) => c.replace(/`/g, '').replace(/\*\*/g, '').trim()).filter(Boolean);

  const headers = parseRow(dataRows[0]);
  const rows = dataRows.slice(1).map(parseRow);

  const COL_COLORS = [
    'text-gray-700 font-medium',
    'text-blue-600',
    'text-emerald-600',
    'text-purple-600',
  ];

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
        <h4 className="text-sm font-semibold text-gray-700">📊 方案对比</h4>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50/50">
              {headers.map((h, i) => (
                <th key={i} className="px-4 py-2.5 text-left font-semibold text-gray-600 border-b border-gray-200 whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri} className={ri % 2 === 0 ? 'bg-white' : 'bg-gray-50/30'}>
                {row.map((cell, ci) => (
                  <td key={ci} className={`px-4 py-2.5 border-b border-gray-100 ${COL_COLORS[ci] ?? 'text-gray-600'}`}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
