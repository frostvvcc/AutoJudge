import { useState } from 'react';

type AttemptStatus = 'pending' | 'running' | 'success' | 'failed';

interface FixAttempt {
  attempt: number;
  strategy: string;
  status: AttemptStatus;
  content: string;
}

interface MustFixItem {
  id: string;
  severity: string;
  description: string;
}

interface Props {
  attempts: FixAttempt[];
  mustFixItems: MustFixItem[];
  currentAttempt: number;
}

const STATUS_STYLES: Record<AttemptStatus, { bg: string; text: string; border: string; label: string }> = {
  pending: { bg: 'bg-gray-100', text: 'text-gray-500', border: 'border-gray-300/40', label: 'Pending' },
  running: { bg: 'bg-blue-50', text: 'text-blue-600', border: 'border-blue-200', label: 'Running' },
  success: { bg: 'bg-green-50', text: 'text-green-600', border: 'border-green-200', label: 'Success' },
  failed: { bg: 'bg-red-50', text: 'text-red-600', border: 'border-red-200', label: 'Failed' },
};

const SEVERITY_DOT: Record<string, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-gray-500',
};

export default function FixProgressPanel({ attempts, mustFixItems, currentAttempt }: Props) {
  const [expandedAttempt, setExpandedAttempt] = useState<number | null>(null);

  const resolved = attempts.filter((a) => a.status === 'success').length;

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17l-5.1-3.184M17.64 5.906A2.04 2.04 0 0116.77 4.5c-.648 0-1.24.32-1.592.828l-4.178 6.56-1.496-1.498a1.5 1.5 0 10-2.121 2.121l2.657 2.657a1.5 1.5 0 002.286-.21l4.904-7.698a2.04 2.04 0 00-.69-2.854z" />
            </svg>
            <span className="text-sm font-semibold text-gray-600">Fix Progress</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-gray-500">Attempt</span>
            <span className="text-blue-400 font-semibold">{currentAttempt}</span>
            <span className="text-gray-700">|</span>
            <span className="text-green-400">{resolved} resolved</span>
          </div>
        </div>
      </div>

      {/* Must-fix checklist */}
      {mustFixItems.length > 0 && (
        <div className="px-4 py-3 border-b border-gray-200/60">
          <div className="flex items-center gap-2 mb-2">
            <svg className="w-3.5 h-3.5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
            <span className="text-xs font-medium text-gray-400">Must Fix Items</span>
            <span className="text-xs text-gray-600">({mustFixItems.length})</span>
          </div>
          <div className="space-y-1.5">
            {mustFixItems.map((item) => {
              const dotColor = SEVERITY_DOT[item.severity] ?? 'bg-gray-500';
              const isResolved = attempts.some(
                (a) => a.status === 'success' && a.content.includes(item.id),
              );
              return (
                <div
                  key={item.id}
                  className={`flex items-start gap-2 px-2.5 py-1.5 rounded ${
                    isResolved ? 'bg-green-50 border border-green-200' : 'bg-gray-50'
                  }`}
                >
                  <div className="mt-1 shrink-0">
                    {isResolved ? (
                      <svg className="w-3.5 h-3.5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    ) : (
                      <span className={`block w-3.5 h-3.5 rounded-full border-2 border-gray-600`} />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
                      <span className="text-xs text-gray-500 bg-gray-50 px-1 py-0.5 rounded">{item.id}</span>
                      <span className="text-xs text-gray-600">{item.severity}</span>
                    </div>
                    <p className={`text-xs mt-0.5 leading-relaxed ${isResolved ? 'text-gray-500 line-through' : 'text-gray-400'}`}>
                      {item.description}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Attempt timeline */}
      <div className="p-4">
        {attempts.length === 0 ? (
          <div className="text-center text-xs text-gray-600 py-4">
            等待修复尝试...
          </div>
        ) : (
          <div className="space-y-0">
            {attempts.map((attempt, idx) => {
              const style = STATUS_STYLES[attempt.status];
              const isExpanded = expandedAttempt === attempt.attempt;
              const isLast = idx === attempts.length - 1;

              return (
                <div key={attempt.attempt} className="flex gap-3">
                  {/* Timeline spine */}
                  <div className="flex flex-col items-center shrink-0">
                    <div
                      className={`w-3 h-3 rounded-full border-2 shrink-0 ${
                        attempt.status === 'running'
                          ? 'border-blue-400 bg-blue-400/30 animate-pulse'
                          : attempt.status === 'success'
                            ? 'border-green-400 bg-green-400/30'
                            : attempt.status === 'failed'
                              ? 'border-red-400 bg-red-400/30'
                              : 'border-gray-300 bg-gray-100'
                      }`}
                    />
                    {!isLast && (
                      <div className={`w-px flex-1 min-h-[24px] ${
                        attempt.status === 'success' ? 'bg-green-300' : 'bg-gray-200'
                      }`} />
                    )}
                  </div>

                  {/* Attempt card */}
                  <div className={`flex-1 mb-3 rounded-lg border p-3 transition-colors ${style.border} ${style.bg}`}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-gray-600">
                          Attempt #{attempt.attempt}
                        </span>
                        <span className="text-xs text-gray-500 bg-gray-50 px-1.5 py-0.5 rounded">
                          {attempt.strategy}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium border ${style.bg} ${style.text} ${style.border}`}>
                          {attempt.status === 'running' && (
                            <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse mr-1.5" />
                          )}
                          {style.label}
                        </span>
                        <button
                          onClick={() => setExpandedAttempt(isExpanded ? null : attempt.attempt)}
                          className="text-gray-500 hover:text-gray-600 transition-colors"
                        >
                          <svg
                            className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={1.5}
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                          </svg>
                        </button>
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="mt-2 pt-2 border-t border-gray-200">
                        <pre className="text-xs text-gray-400 whitespace-pre-wrap leading-relaxed font-mono bg-gray-50 rounded p-2 max-h-[200px] overflow-y-auto">
                          {attempt.content}
                        </pre>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
