import { useState } from 'react';

export interface Finding {
  category: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  description: string;
  test_input?: string;
}

const SEVERITY_STYLES: Record<Finding['severity'], string> = {
  critical: 'bg-red-50 text-red-600 border-red-200',
  high: 'bg-orange-50 text-orange-600 border-orange-200',
  medium: 'bg-yellow-50 text-yellow-600 border-yellow-200',
  low: 'bg-gray-50 text-gray-500 border-gray-200',
};

const SEVERITY_DOT: Record<Finding['severity'], string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-gray-500',
};

interface Props {
  finding: Finding;
}

export default function FindingCard({ finding }: Props) {
  const [expanded, setExpanded] = useState(false);

  const badgeClass = SEVERITY_STYLES[finding.severity];
  const dotClass = SEVERITY_DOT[finding.severity];

  return (
    <div className="bg-white rounded-lg border border-gray-200">
      <button
        type="button"
        className="w-full p-3 flex items-start gap-3 text-left"
        onClick={() => setExpanded((prev) => !prev)}
      >
        <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${dotClass}`} />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded border ${badgeClass}`}
            >
              {finding.severity}
            </span>
            <span className="text-xs text-gray-500">{finding.category}</span>
          </div>
          <p className="text-sm text-gray-600 leading-relaxed truncate">
            {finding.description}
          </p>
        </div>

        <span className="text-gray-600 text-xs mt-1 shrink-0">
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 pt-0 border-t border-gray-200">
          <p className="text-sm text-gray-600 whitespace-pre-wrap leading-relaxed mt-3">
            {finding.description}
          </p>
          {finding.test_input && (
            <div className="mt-3">
              <span className="text-xs text-gray-500 font-medium">
                Test Input
              </span>
              <pre className="mt-1 p-2 bg-gray-50 rounded text-xs text-gray-400 overflow-x-auto">
                {finding.test_input}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
