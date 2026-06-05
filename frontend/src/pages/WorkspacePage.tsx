import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import NavBar from '../components/NavBar';
import { useDebate } from '../contexts/DebateContext';
import PipelineProgress from '../components/workspace/PipelineProgress';
import AttackResponsePanel from '../components/workspace/AttackResponsePanel';
import RealtimeDashboard from '../components/workspace/RealtimeDashboard';
import QualityReportPanel from '../components/workspace/QualityReportPanel';
import CodeEditor from '../components/CodeEditor';
import UserInteractionDock from '../components/workspace/UserInteractionDock';
import * as api from '../lib/api';
import type { DebatePhase, DebateMessage, QualityReport } from '../types/debate';

function inferPhase(status: string, statusText: string): DebatePhase {
  if (status === 'idle') return 'idle';
  if (status === 'done' || status === 'converged') return 'done';
  if (status === 'error') return 'error';
  const t = statusText.toLowerCase();
  if (t.includes('方案') || t.includes('plan')) return 'plan';
  if (t.includes('仲裁') || t.includes('arbitrat')) return 'arbitration';
  if (t.includes('修复') || t.includes('fix')) return 'fixing';
  if (t.includes('judge') || t.includes('总结') || t.includes('报告')) return 'judging';
  if (t.includes('coder') && !t.includes('attacker')) return 'coding';
  return 'debate';
}

function SideDrawer({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <>
      {open && (
        <div className="fixed inset-0 bg-black/40 z-40 backdrop-blur-sm" onClick={onClose} />
      )}
      <div
        className={`fixed top-0 right-0 h-full w-[420px] max-w-[90vw] bg-gray-900 border-l border-gray-800 z-50 transform transition-transform duration-300 ease-out ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h3 className="text-sm font-semibold text-gray-200">详细信息</h3>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg hover:bg-gray-800 flex items-center justify-center text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="overflow-y-auto h-[calc(100%-57px)] p-5 space-y-4">
          {children}
        </div>
      </div>
    </>
  );
}

function AgentDots({ activeAgents }: { activeAgents: Set<string> }) {
  const agents = [
    { key: 'coder', label: 'Coder', color: 'bg-blue-500' },
    { key: 'security', label: 'Security', color: 'bg-red-500' },
    { key: 'performance', label: 'Performance', color: 'bg-orange-500' },
    { key: 'correctness', label: 'Correctness', color: 'bg-green-500' },
    { key: 'arbitrator', label: 'Arbitrator', color: 'bg-amber-500' },
    { key: 'judge', label: 'Judge', color: 'bg-purple-500' },
  ];

  const active = agents.filter((a) => activeAgents.has(a.key));
  if (active.length === 0) return null;

  return (
    <div className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800/60 rounded-full border border-gray-700/30">
      {active.map((a) => (
        <div key={a.key} className="flex items-center gap-1">
          <div className={`w-2 h-2 rounded-full ${a.color} animate-pulse`} />
          <span className="text-xs text-gray-300">{a.label}</span>
        </div>
      ))}
      <span className="text-xs text-gray-500 ml-1">正在分析...</span>
    </div>
  );
}

export default function WorkspacePage() {
  const { sid } = useParams<{ sid: string }>();
  const debate = useDebate();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const isLive = sid === 'live';

  const [replayData, setReplayData] = useState<api.SessionDetail | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [replayError, setReplayError] = useState('');

  useEffect(() => {
    if (!isLive && sid) {
      setReplayLoading(true);
      api
        .getSessionDetail(sid)
        .then(setReplayData)
        .catch((e) => setReplayError(e.message))
        .finally(() => setReplayLoading(false));
    }
  }, [sid, isLive]);

  const isReplay = !isLive && replayData !== null;

  // Build unified view data (always computed, never behind early returns)
  const viewData = useMemo(() => {
    let messages: DebateMessage[];
    let code: string;
    let language: string;
    let currentRound: number;
    let statusText: string;
    let status: string;
    let phase: DebatePhase;
    let confidence: number;
    let qualityReport: QualityReport | null;
    let riskAssessment: { security: string; performance: string; correctness: string } | null;
    let metrics: { total_rounds: number; total_tokens: number; total_latency_ms: number; cost_usd: number } | null;
    let taskDescription: string;

    if (isReplay && replayData) {
      messages = replayData.messages.map((m) => ({
        agent: m.agent,
        content: m.content,
        round: m.round,
        code: m.code ?? undefined,
        structured: m.structured_json ?? undefined,
      }));
      code = replayData.result_code ?? '';
      language = replayData.language;
      currentRound = replayData.total_rounds;
      statusText = '历史回放';
      status = 'done';
      phase = 'done';
      confidence = replayData.confidence;
      taskDescription = replayData.task;

      const rj = replayData.risk_json as Record<string, string> | null;
      riskAssessment = rj ? {
        security: rj.security ?? 'unknown',
        performance: rj.performance ?? 'unknown',
        correctness: rj.correctness ?? 'unknown',
      } : null;

      const mj = replayData.metrics_json as Record<string, number> | null;
      metrics = mj ? {
        total_rounds: (mj.total_rounds as number) ?? replayData.total_rounds,
        total_tokens: (mj.total_tokens as number) ?? replayData.total_tokens,
        total_latency_ms: (mj.total_latency_ms as number) ?? replayData.total_latency_ms,
        cost_usd: (mj.cost_usd as number) ?? replayData.cost_usd,
      } : {
        total_rounds: replayData.total_rounds,
        total_tokens: replayData.total_tokens,
        total_latency_ms: replayData.total_latency_ms,
        cost_usd: replayData.cost_usd,
      };

      const qrJson = replayData.quality_report_json as Record<string, unknown> | null;
      qualityReport = qrJson ? {
        star_rating: (qrJson.star_rating as number) ?? 0,
        star_comment: (qrJson.star_comment as string) ?? '',
        resolved_issues: (qrJson.resolved_issues as string[]) ?? [],
        unresolved_issues: (qrJson.unresolved_issues as Array<{ issue: string; current_status: string; impact: string; suggestion: string }>) ?? [],
        score_security: (qrJson.score_security as number) ?? 0,
        score_performance: (qrJson.score_performance as number) ?? 0,
        score_correctness: (qrJson.score_correctness as number) ?? 0,
        usage_advice: (qrJson.usage_advice as string) ?? '',
      } : null;
    } else {
      messages = debate.messages;
      code = debate.result?.code ?? '';
      language = debate.result?.language ?? 'python';
      currentRound = debate.currentRound;
      statusText = debate.statusText;
      status = debate.status;
      phase = (debate.currentPhase || inferPhase(debate.status, debate.statusText)) as DebatePhase;
      confidence = debate.result?.confidence ?? 0;
      qualityReport = debate.result?.quality_report ?? null;
      riskAssessment = debate.result?.risk_assessment ?? null;
      metrics = debate.result?.metrics ?? null;
      taskDescription = '';
    }

    return { messages, code, language, currentRound, statusText, status, phase, confidence, qualityReport, riskAssessment, metrics, taskDescription };
  }, [isReplay, replayData, debate]);

  const activeAgents = useMemo(() => {
    const set = new Set<string>();
    if (viewData.status === 'running') {
      const t = viewData.statusText.toLowerCase();
      if (t.includes('coder')) set.add('coder');
      if (t.includes('security')) set.add('security');
      if (t.includes('performance')) set.add('performance');
      if (t.includes('correctness')) set.add('correctness');
      if (t.includes('attacker') || t.includes('审查') || t.includes('攻击')) {
        set.add('security');
        set.add('performance');
        set.add('correctness');
      }
      if (t.includes('仲裁') || t.includes('arbitrat')) set.add('arbitrator');
      if (t.includes('judge') || t.includes('总结')) set.add('judge');
    }
    return set;
  }, [viewData.status, viewData.statusText]);

  // Early returns AFTER all hooks
  if (isLive && debate.status === 'idle') {
    navigate('/dashboard');
    return null;
  }

  if (!isLive && replayLoading) {
    return (
      <div className="min-h-screen bg-gray-950 flex flex-col">
        <NavBar />
        <div className="flex-1 flex items-center justify-center">
          <div className="flex items-center gap-3">
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-gray-400 text-sm">加载历史记录...</span>
          </div>
        </div>
      </div>
    );
  }

  if (!isLive && (replayError || !replayData)) {
    return (
      <div className="min-h-screen bg-gray-950 flex flex-col">
        <NavBar />
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-red-500/10 flex items-center justify-center">
            <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
          </div>
          <p className="text-red-400 text-sm">{replayError || '记录不存在'}</p>
          <button
            onClick={() => navigate('/history')}
            className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
          >
            返回历史记录
          </button>
        </div>
      </div>
    );
  }

  const { messages, code, language, currentRound, statusText, status, phase, confidence, qualityReport, riskAssessment, metrics, taskDescription } = viewData;
  const isDone = status === 'done' || status === 'converged';
  const hasDetails = code || qualityReport || riskAssessment || metrics;

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      <NavBar />

      {/* Top bar: pipeline + controls */}
      <div className="border-b border-gray-800/50 bg-gray-950/80 backdrop-blur-md sticky top-0 z-30">
        <div className="max-w-5xl mx-auto px-4 py-2.5">
          <div className="flex items-center justify-between gap-4">
            <div className="flex-1 min-w-0 overflow-x-auto">
              <PipelineProgress
                phase={phase}
                currentRound={currentRound}
                maxRounds={5}
                statusText={isReplay ? '' : statusText}
              />
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {hasDetails && (
                <button
                  onClick={() => setDrawerOpen(true)}
                  className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-400 hover:text-white bg-gray-800/60 hover:bg-gray-800 border border-gray-700/30 rounded-lg transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
                  </svg>
                  代码 & 报告
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Replay badge */}
      {isReplay && (
        <div className="max-w-3xl mx-auto w-full px-4 pt-3">
          <div className="flex items-center gap-3 px-4 py-2.5 bg-gray-800/40 rounded-xl border border-gray-700/30">
            <svg className="w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-sm text-gray-400">历史回放</span>
            {taskDescription && (
              <span className="text-sm text-gray-300 truncate flex-1">{taskDescription}</span>
            )}
            <span className="text-xs text-gray-600">{language}</span>
          </div>
        </div>
      )}

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-h-0">
        <AttackResponsePanel messages={messages} currentRound={currentRound} />

        {!isReplay && status === 'running' && (
          <div className="max-w-3xl mx-auto w-full px-8 pb-2">
            <AgentDots activeAgents={activeAgents} />
          </div>
        )}
      </div>

      {/* Bottom: interaction dock or done actions */}
      {!isReplay && !isDone && status !== 'error' && (
        <UserInteractionDock
          phase={phase}
          onPlanSelect={(_plan) => { /* plan select handler */ }}
          onPlanChat={(_msg) => { /* plan chat handler */ }}
          onArbitrationAccept={() => { /* arbitration accept */ }}
          onStrategyAccept={() => { /* strategy accept */ }}
          onStrategyReject={() => { /* strategy reject */ }}
          onStop={debate.stop}
        />
      )}

      {isDone && (
        <div className="border-t border-gray-800/50 bg-gray-950/80 backdrop-blur-md">
          <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-center gap-3">
            <button
              onClick={() => {
                if (!isReplay) debate.reset();
                navigate('/dashboard');
              }}
              className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-medium text-white transition-colors shadow-lg shadow-blue-600/20"
            >
              {isReplay ? '返回任务中心' : '新建任务'}
            </button>
            <button
              onClick={() => navigate('/history')}
              className="px-6 py-2.5 bg-gray-800 hover:bg-gray-700 rounded-xl text-sm text-gray-300 transition-colors border border-gray-700/50"
            >
              历史记录
            </button>
            {hasDetails && (
              <button
                onClick={() => setDrawerOpen(true)}
                className="px-6 py-2.5 bg-gray-800 hover:bg-gray-700 rounded-xl text-sm text-gray-300 transition-colors border border-gray-700/50 flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
                </svg>
                查看代码 & 报告
              </button>
            )}
          </div>
        </div>
      )}

      {!isReplay && debate.error && (
        <div className="max-w-3xl mx-auto w-full px-4 pb-4">
          <div className="bg-red-900/20 border border-red-800/30 rounded-xl p-4 flex items-center justify-between">
            <p className="text-red-400 text-sm">{debate.error}</p>
            <button
              onClick={() => { debate.reset(); navigate('/dashboard'); }}
              className="shrink-0 ml-4 px-4 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300"
            >
              重试
            </button>
          </div>
        </div>
      )}

      {/* Side drawer for code + report + metrics */}
      <SideDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        <CodeEditor code={code} language={language} />
        {qualityReport && qualityReport.star_rating > 0 && (
          <QualityReportPanel report={qualityReport} confidence={confidence} />
        )}
        <RealtimeDashboard
          messages={messages}
          risk={riskAssessment ?? undefined}
          metrics={metrics ?? undefined}
        />
      </SideDrawer>
    </div>
  );
}
