import ReactMarkdown from 'react-markdown';

interface Props {
  content: string;
}

function splitPlans(raw: string): { intro: string; plans: { label: string; body: string }[] } {
  const cleaned = raw.replace(/^\[方案设计\]\s*/i, '');

  const planPattern = /(?:^|\n)(?:#{1,3}\s*)?(?:方案\s*[A-Za-z]|Plan\s*[A-Za-z])[：:：\s]/gi;
  const matches = [...cleaned.matchAll(planPattern)];

  if (matches.length >= 2) {
    const intro = cleaned.slice(0, matches[0].index).trim();
    const plans: { label: string; body: string }[] = [];

    for (let i = 0; i < matches.length; i++) {
      const start = matches[i].index!;
      const end = i + 1 < matches.length ? matches[i + 1].index! : cleaned.length;
      const chunk = cleaned.slice(start, end).trim();

      const firstLine = chunk.split('\n')[0].replace(/^#{1,3}\s*/, '').trim();
      const body = chunk.split('\n').slice(1).join('\n').trim();
      plans.push({ label: firstLine, body });
    }
    return { intro, plans };
  }

  const numberPattern = /(?:^|\n)(?:#{1,3}\s*)?(?:\d+[\.\)、]|[一二三四五][\.\)、])\s*/g;
  const numMatches = [...cleaned.matchAll(numberPattern)];

  if (numMatches.length >= 2) {
    const intro = cleaned.slice(0, numMatches[0].index).trim();
    const plans: { label: string; body: string }[] = [];

    for (let i = 0; i < Math.min(numMatches.length, 3); i++) {
      const start = numMatches[i].index!;
      const end = i + 1 < numMatches.length ? numMatches[i + 1].index! : cleaned.length;
      const chunk = cleaned.slice(start, end).trim();
      const firstLine = chunk.split('\n')[0].trim();
      const body = chunk.split('\n').slice(1).join('\n').trim();
      plans.push({ label: firstLine, body });
    }
    return { intro, plans };
  }

  return { intro: '', plans: [{ label: '方案', body: cleaned }] };
}

const PLAN_COLORS = [
  { border: 'border-blue-500', bg: 'bg-blue-500/5', badge: 'bg-blue-900/60 text-blue-300', icon: 'A' },
  { border: 'border-emerald-500', bg: 'bg-emerald-500/5', badge: 'bg-emerald-900/60 text-emerald-300', icon: 'B' },
  { border: 'border-purple-500', bg: 'bg-purple-500/5', badge: 'bg-purple-900/60 text-purple-300', icon: 'C' },
];

export default function PlanDisplayCard({ content }: Props) {
  const { intro, plans } = splitPlans(content);

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2 px-1">
        <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center">
          <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <h3 className="text-sm font-semibold text-white">方案设计</h3>
        <span className="text-xs text-gray-500">Coder 为你准备了 {plans.length} 个方案</span>
      </div>

      {/* Intro */}
      {intro && (
        <p className="text-xs text-gray-400 px-1">{intro}</p>
      )}

      {/* Plan cards */}
      <div className={`grid gap-3 ${plans.length > 1 ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-1'}`}>
        {plans.map((plan, i) => {
          const color = PLAN_COLORS[i % PLAN_COLORS.length];
          return (
            <div
              key={i}
              className={`border-l-3 ${color.border} ${color.bg} rounded-r-lg p-4 border-l-[3px]`}
            >
              <div className="flex items-center gap-2 mb-3">
                <span className={`w-6 h-6 rounded-full ${color.badge} flex items-center justify-center text-xs font-bold`}>
                  {color.icon}
                </span>
                <span className="text-sm font-semibold text-gray-200">
                  {plan.label.replace(/^[#\d\.\)、一二三四五\s]+/, '').trim() || `方案 ${color.icon}`}
                </span>
              </div>
              <div className="text-xs text-gray-300 leading-relaxed prose prose-invert prose-xs max-w-none
                             prose-headings:text-gray-200 prose-headings:text-xs prose-headings:font-semibold prose-headings:mt-2 prose-headings:mb-1
                             prose-li:my-0.5 prose-ul:my-1 prose-p:my-1
                             prose-strong:text-gray-200">
                <ReactMarkdown>{plan.body || plan.label}</ReactMarkdown>
              </div>
            </div>
          );
        })}
      </div>

      {/* Auto-select note */}
      <div className="flex items-center gap-2 px-1 py-2 rounded bg-gray-800/50">
        <svg className="w-4 h-4 text-gray-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
        </svg>
        <span className="text-xs text-gray-500">Coder 已自动综合最佳方案开始编码。后续辩论阶段仍可调整方向。</span>
      </div>
    </div>
  );
}
