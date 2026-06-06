import type { AnalysisData } from '../../contexts/DebateContext';

interface Props {
  data: AnalysisData;
}

const COMPLEXITY_CONFIG: Record<string, { label: string; color: string; dot: string }> = {
  simple: { label: '简单', color: 'text-green-600 bg-green-50 border-green-200', dot: '🟢' },
  medium: { label: '中等', color: 'text-yellow-600 bg-yellow-50 border-yellow-200', dot: '🟡' },
  hard: { label: '困难', color: 'text-red-600 bg-red-50 border-red-200', dot: '🔴' },
};

function extractIssueTitle(content: string): string {
  const lines = content.split('\n');
  const issueLine = lines.find((l) => l.startsWith('Issue:'));
  if (issueLine) {
    const text = issueLine.replace('Issue:', '').trim();
    if (text) return text;
  }
  const catLine = lines.find((l) => l.startsWith('Category:'));
  const cat = catLine ? catLine.replace('Category:', '').trim() : '';
  return cat || content.slice(0, 60);
}

export default function AnalysisCard({ data }: Props) {
  const { parsed_requirement: req, complexity, experiences } = data;
  const cplx = COMPLEXITY_CONFIG[complexity] ?? COMPLEXITY_CONFIG.medium;

  const hasContent =
    req.functional.length > 0 || req.implicit.length > 0 || req.edge_cases.length > 0;

  if (!hasContent && experiences.length === 0) return null;

  return (
    <div className="rounded-xl border border-indigo-100 bg-gradient-to-br from-indigo-50/60 to-white overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center">
            <span className="text-white text-sm">🧠</span>
          </div>
          <span className="text-white font-semibold text-sm">智能需求分析</span>
        </div>
        <span className={`px-2.5 py-1 rounded-full text-xs font-bold border ${cplx.color}`}>
          {cplx.dot} {cplx.label}
        </span>
      </div>

      <div className="p-5 space-y-4">
        {/* Functional requirements */}
        {req.functional.length > 0 && (
          <Section icon="📋" title="识别到的功能点">
            {req.functional.map((item, i) => (
              <BulletItem key={i} text={item} color="text-indigo-500" />
            ))}
          </Section>
        )}

        {/* Implicit requirements */}
        {req.implicit.length > 0 && (
          <Section icon="💡" title="系统自动补全的隐含需求">
            {req.implicit.map((item, i) => (
              <BulletItem key={i} text={item} color="text-amber-500" />
            ))}
          </Section>
        )}

        {/* Edge cases */}
        {req.edge_cases.length > 0 && (
          <Section icon="🎯" title="将特别关注的边界场景">
            <div className="flex flex-wrap gap-1.5">
              {req.edge_cases.map((item, i) => (
                <span
                  key={i}
                  className="text-xs px-2.5 py-1 rounded-full bg-orange-50 text-orange-700 border border-orange-200"
                >
                  {item}
                </span>
              ))}
            </div>
          </Section>
        )}

        {/* Constraints */}
        {req.constraints.length > 0 && (
          <Section icon="📐" title="约束条件">
            {req.constraints.map((item, i) => (
              <BulletItem key={i} text={item} color="text-gray-400" />
            ))}
          </Section>
        )}

        {/* Historical experiences */}
        {experiences.length > 0 && (
          <div className="border-t border-indigo-100 pt-4">
            <div className="flex items-center gap-2 mb-2.5">
              <span className="text-sm">📚</span>
              <span className="text-xs font-semibold text-gray-700">
                匹配到 {experiences.length} 条历史经验
              </span>
            </div>
            <div className="space-y-2">
              {experiences.map((exp, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2.5 px-3 py-2 rounded-lg bg-white border border-gray-100 hover:border-indigo-200 transition-colors"
                >
                  <SeverityBadge severity={exp.severity} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-gray-700 leading-relaxed">
                      {extractIssueTitle(exp.content)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {exp.similarity != null && exp.similarity > 0 && (
                      <span className="text-xs text-indigo-500 font-mono">{exp.similarity}%</span>
                    )}
                    {exp.session_id && (
                      <a
                        href={`/workspace/${exp.session_id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="text-xs text-indigo-400 hover:text-indigo-600 underline"
                      >
                        查看来源
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ icon, title, children }: { icon: string; title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm">{icon}</span>
        <span className="text-xs font-semibold text-gray-700">{title}</span>
      </div>
      <div className="space-y-1 pl-6">{children}</div>
    </div>
  );
}

function BulletItem({ text, color }: { text: string; color: string }) {
  return (
    <div className="flex items-start gap-2 text-xs text-gray-600 leading-relaxed">
      <span className={`mt-1 shrink-0 ${color}`}>●</span>
      <span>{text}</span>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const config: Record<string, { bg: string; text: string }> = {
    high: { bg: 'bg-red-100', text: 'text-red-700' },
    medium: { bg: 'bg-yellow-100', text: 'text-yellow-700' },
    low: { bg: 'bg-green-100', text: 'text-green-700' },
  };
  const c = config[severity] ?? config.medium;
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded ${c.bg} ${c.text} font-medium shrink-0 mt-0.5`}>
      {severity === 'high' ? '高危' : severity === 'low' ? '低危' : '中危'}
    </span>
  );
}
