export interface DebateMessage {
  agent: string;
  content: string;
  round?: number;
  code?: string;
  structured?: Record<string, unknown>;
}

export interface RoundData {
  round: number;
  messages: DebateMessage[];
}

export interface DebateSummary {
  total_issues_raised: number;
  accepted_and_fixed: number;
  rejected_by_coder: number;
  suggestions_noted: number;
  key_improvements: string[];
}

export interface RiskAssessment {
  security: string;
  performance: string;
  correctness: string;
}

export interface DebateMetrics {
  total_rounds: number;
  total_tokens: number;
  total_latency_ms: number;
  cost_usd: number;
}

export interface UnresolvedIssue {
  issue: string;
  current_status: string;
  impact: string;
  suggestion: string;
}

export interface QualityReport {
  star_rating: number;
  star_comment: string;
  resolved_issues: string[];
  unresolved_issues: UnresolvedIssue[];
  score_security: number;
  score_performance: number;
  score_correctness: number;
  usage_advice: string;
}

export interface DebateResult {
  code: string;
  language: string;
  confidence: number;
  debate: {
    total_rounds: number;
    converged: boolean;
    consensus_reason: string;
    transcript: RoundData[];
  };
  summary: DebateSummary;
  risk_assessment: RiskAssessment;
  metrics: DebateMetrics;
  quality_report: QualityReport;
  converged: boolean;
  convergence_reason: string;
  metadata?: Record<string, unknown>;
}

export interface WSEvent {
  type: string;
  agent?: string;
  content?: string;
  code?: string;
  round?: number;
  reason?: string;
  data?: DebateResult;
  message?: string;
  structured?: Record<string, unknown>;
  session_sid?: string;
  phase?: string;
  disputes_count?: number;
  overall_verdict?: string;
  summary?: string;
}

export type DebatePhase =
  | 'idle'
  | 'analysis'
  | 'plan'
  | 'coding'
  | 'debate'
  | 'arbitration'
  | 'fixing'
  | 'judging'
  | 'user_decision'
  | 'done'
  | 'error';

export type DebateStatus = 'idle' | 'connecting' | 'running' | 'converged' | 'done' | 'error';

export const AGENT_COLORS: Record<string, string> = {
  coder: 'border-blue-500 bg-blue-500/10',
  security: 'border-red-500 bg-red-500/10',
  performance: 'border-orange-500 bg-orange-500/10',
  correctness: 'border-green-500 bg-green-500/10',
  system: 'border-gray-500 bg-gray-500/10',
  judge: 'border-purple-500 bg-purple-500/10',
  arbitrator: 'border-amber-500 bg-amber-500/10',
};

export const AGENT_LABELS: Record<string, string> = {
  coder: 'Coder',
  security: 'Security',
  performance: 'Performance',
  correctness: 'Correctness',
  system: 'System',
  judge: 'Judge',
  arbitrator: 'Arbitrator',
};

export const AGENT_DOTS: Record<string, string> = {
  coder: 'bg-blue-500',
  security: 'bg-red-500',
  performance: 'bg-orange-500',
  correctness: 'bg-green-500',
  system: 'bg-gray-500',
  judge: 'bg-purple-500',
  arbitrator: 'bg-amber-500',
};

export const LANGUAGE_GROUPS = [
  {
    group: '常用',
    languages: [
      { value: 'python', label: 'Python' },
      { value: 'javascript', label: 'JavaScript' },
      { value: 'typescript', label: 'TypeScript' },
      { value: 'java', label: 'Java' },
    ],
  },
  {
    group: '系统级',
    languages: [
      { value: 'c', label: 'C' },
      { value: 'cpp', label: 'C++' },
      { value: 'csharp', label: 'C#' },
      { value: 'rust', label: 'Rust' },
      { value: 'go', label: 'Go' },
    ],
  },
  {
    group: '其他',
    languages: [
      { value: 'kotlin', label: 'Kotlin' },
      { value: 'swift', label: 'Swift' },
      { value: 'php', label: 'PHP' },
      { value: 'ruby', label: 'Ruby' },
      { value: 'scala', label: 'Scala' },
      { value: 'shell', label: 'Shell/Bash' },
      { value: 'sql', label: 'SQL' },
    ],
  },
];
