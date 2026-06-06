import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import NavBar from '../components/NavBar';
import { useDebate } from '../contexts/DebateContext';
import PipelineProgress from '../components/workspace/PipelineProgress';
import AgentStatusBar from '../components/workspace/AgentStatusBar';
import AttackResponsePanel from '../components/workspace/AttackResponsePanel';
import RealtimeDashboard from '../components/workspace/RealtimeDashboard';
import QualityReportPanel from '../components/workspace/QualityReportPanel';
import CodeEditor from '../components/CodeEditor';
import * as api from '../lib/api';
import type { DebatePhase, DebateMessage, QualityReport } from '../types/debate';

function inferPhase(status: string, statusText: string): DebatePhase {
  if (status === 'idle') return 'idle';
  if (status === 'done' || status === 'converged' || status === 'completed') return 'done';
  if (status === 'error' || status === 'failed') return 'error';
  const t = statusText.toLowerCase();
  if (t.includes('方案') || t.includes('plan') || status === 'planning') return 'plan';
  if (t.includes('仲裁') || t.includes('arbitrat') || status === 'arbitrating') return 'arbitration';
  if (t.includes('修复') || t.includes('fix') || status === 'fixing') return 'fixing';
  if (t.includes('judge') || t.includes('总结') || t.includes('报告')) return 'judging';
  if (t.includes('coder') && !t.includes('attacker')) return 'coding';
  if (status === 'debating') return 'debate';
  return 'debate';
}

export default function WorkspacePage() {
  const { sid } = useParams<{ sid: string }>();
  const debate = useDebate();
  const navigate = useNavigate();

  const isLive = sid === 'live';

  const [replayData, setReplayData] = useState<api.SessionDetail | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [replayError, setReplayError] = useState('');

  useEffect(() => {
    if (!isLive && sid) {
      setReplayLoading(true);
      api.getSessionDetail(sid)
        .then(setReplayData)
        .catch((e) => setReplayError(e.message))
        .finally(() => setReplayLoading(false));
    }
  }, [sid, isLive]);

  const isReplay = !isLive && replayData !== null;

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
        agent: m.agent, content: m.content, round: m.round,
        code: m.code ?? undefined, structured: m.structured_json ?? undefined,
      }));
      code = replayData.result_code ?? '';
      language = replayData.language;
      currentRound = replayData.total_rounds;
      statusText = '历史回放';

      const replayStatus = replayData.status;
      status = replayStatus;
      phase = inferPhase(replayStatus, '');

      confidence = replayData.confidence;
      taskDescription = replayData.task;

      const rj = replayData.risk_json as Record<string, string> | null;
      riskAssessment = rj ? { security: rj.security ?? 'unknown', performance: rj.performance ?? 'unknown', correctness: rj.correctness ?? 'unknown' } : null;

      const mj = replayData.metrics_json as Record<string, number> | null;
      metrics = mj ? {
        total_rounds: (mj.total_rounds as number) ?? replayData.total_rounds,
        total_tokens: (mj.total_tokens as number) ?? replayData.total_tokens,
        total_latency_ms: (mj.total_latency_ms as number) ?? replayData.total_latency_ms,
        cost_usd: (mj.cost_usd as number) ?? replayData.cost_usd,
      } : { total_rounds: replayData.total_rounds, total_tokens: replayData.total_tokens, total_latency_ms: replayData.total_latency_ms, cost_usd: replayData.cost_usd };

      const qrJson = replayData.quality_report_json as Record<string, unknown> | null;
      qualityReport = qrJson ? {
        star_rating: (qrJson.star_rating as number) ?? 0, star_comment: (qrJson.star_comment as string) ?? '',
        resolved_issues: (qrJson.resolved_issues as string[]) ?? [],
        unresolved_issues: (qrJson.unresolved_issues as Array<{ issue: string; current_status: string; impact: string; suggestion: string }>) ?? [],
        score_security: (qrJson.score_security as number) ?? 0, score_performance: (qrJson.score_performance as number) ?? 0,
        score_correctness: (qrJson.score_correctness as number) ?? 0, usage_advice: (qrJson.usage_advice as string) ?? '',
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
      if (t.includes('attacker') || t.includes('审查') || t.includes('攻击')) { set.add('security'); set.add('performance'); set.add('correctness'); }
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
      <div className="min-h-screen bg-gray-50">
        <NavBar />
        <div className="flex items-center justify-center py-20">
          <div className="flex items-center gap-3">
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-gray-500 text-sm">加载历史记录...</span>
          </div>
        </div>
      </div>
    );
  }

  if (!isLive && (replayError || !replayData)) {
    return (
      <div className="min-h-screen bg-gray-50">
        <NavBar />
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <p className="text-red-500 text-sm">{replayError || '记录不存在'}</p>
          <button onClick={() => navigate('/history')} className="text-sm text-blue-600 hover:text-blue-500">
            返回历史记录
          </button>
        </div>
      </div>
    );
  }

  const { messages, code, language, currentRound, statusText, status, phase, confidence, qualityReport, riskAssessment, metrics, taskDescription } = viewData;
  const isDone = status === 'done' || status === 'converged';

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-4 space-y-4">
        {/* Replay badge */}
        {isReplay && (
          <div className="flex items-start gap-3 px-4 py-3 bg-blue-50 rounded-xl border border-blue-100">
            <svg className="w-4 h-4 text-blue-500 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1 min-w-0">
              <span className="text-xs font-medium text-blue-600">历史回放</span>
              {taskDescription && (
                <p className="text-sm text-gray-700 mt-1 leading-relaxed">{taskDescription}</p>
              )}
            </div>
            <span className="text-xs text-blue-400 shrink-0">{language}</span>
          </div>
        )}

        {/* Pipeline progress */}
        <PipelineProgress phase={phase} currentRound={currentRound} maxRounds={5} statusText={isReplay ? '' : statusText} />

        {/* Agent status (live only) */}
        {!isReplay && <AgentStatusBar activeAgents={activeAgents} />}

        {/* Main layout */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          <div className="lg:col-span-3 space-y-4">
            {!isReplay && status === 'running' && (
              <div className="flex items-center justify-end gap-2">
                <button onClick={debate.stop} className="px-3 py-1 text-xs bg-red-50 hover:bg-red-100 rounded border border-red-200 text-red-600">
                  终止
                </button>
              </div>
            )}

            <AttackResponsePanel messages={messages} currentRound={currentRound} />

            {!isReplay && status === 'running' && (
              <div className="flex items-center gap-2 text-gray-500 text-sm p-3">
                <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                {statusText || '处理中...'}
              </div>
            )}
          </div>

          <div className="lg:col-span-2 space-y-4">
            <CodeEditor code={code} language={language} />
            {qualityReport && qualityReport.star_rating > 0 && (
              <QualityReportPanel report={qualityReport} confidence={confidence} />
            )}
            <RealtimeDashboard messages={messages} risk={riskAssessment ?? undefined} metrics={metrics ?? undefined} />
          </div>
        </div>

        {/* Done actions */}
        {isDone && (
          <div className="flex items-center justify-center gap-3 pt-4">
            <button
              onClick={() => { if (!isReplay) debate.reset(); navigate('/dashboard'); }}
              className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium text-white transition-colors"
            >
              {isReplay ? '返回任务中心' : '新建任务'}
            </button>
          </div>
        )}

        {!isReplay && debate.error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center justify-between">
            <p className="text-red-600 text-sm">{debate.error}</p>
            <button onClick={() => { debate.reset(); navigate('/dashboard'); }} className="shrink-0 ml-4 px-4 py-1.5 bg-white hover:bg-gray-50 border border-gray-200 rounded text-sm text-gray-700">
              重试
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
