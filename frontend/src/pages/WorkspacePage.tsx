import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import NavBar from '../components/NavBar';
import { useDebate } from '../contexts/DebateContext';
import PipelineProgress from '../components/workspace/PipelineProgress';
import AttackResponsePanel from '../components/workspace/AttackResponsePanel';
import QualityReportPanel from '../components/workspace/QualityReportPanel';
import CodeEditor from '../components/CodeEditor';
import * as api from '../lib/api';
import type { DebatePhase, DebateMessage, QualityReport } from '../types/debate';
import { AGENT_LABELS, AGENT_DOTS } from '../types/debate';
import { useRef, useEffect as useLayoutEffect } from 'react';

function StreamingCard({ agent, text }: { agent: string; text: string }) {
  const endRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [text]);

  const dotClass = AGENT_DOTS[agent] ?? 'bg-gray-500';
  const label = AGENT_LABELS[agent] ?? agent;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <div className={`w-2.5 h-2.5 rounded-full ${dotClass} animate-pulse`} />
        <span className="text-sm font-semibold text-gray-700">{label}</span>
        <span className="text-xs text-gray-400">正在输出...</span>
      </div>
      <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap max-h-[300px] overflow-y-auto font-mono">
        {text}
        <span className="inline-block w-2 h-4 bg-blue-500 animate-pulse ml-0.5 align-middle" />
        <div ref={endRef} />
      </div>
    </div>
  );
}

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
  const [selectedPhase, setSelectedPhase] = useState<string | null>(null);

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
      status = replayData.status;
      phase = inferPhase(replayData.status, '');
      confidence = replayData.confidence;
      taskDescription = replayData.task;

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
      metrics = debate.result?.metrics ?? null;
      taskDescription = '';
    }
    return { messages, code, language, currentRound, statusText, status, phase, confidence, qualityReport, metrics, taskDescription };
  }, [isReplay, replayData, debate]);

  // Auto-select current phase when it changes
  useEffect(() => {
    if (!isReplay && viewData.phase !== 'idle' && viewData.phase !== 'error') {
      setSelectedPhase(null);
    }
  }, [viewData.phase, isReplay]);

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

  const { messages, code, language, currentRound, statusText, status, phase, confidence, qualityReport, metrics, taskDescription } = viewData;
  const isDone = status === 'done' || status === 'converged' || status === 'completed';
  const isFlash = isReplay
    ? (replayData?.config_json as Record<string, unknown>)?.mode === 'flash'
    : debate.mode === 'flash';

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-4 space-y-4">
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

        {/* Pipeline progress — doubles as phase selector */}
        <PipelineProgress
          phase={phase}
          currentRound={currentRound}
          maxRounds={5}
          statusText={isReplay ? '' : statusText}
          activeAgents={isReplay ? new Set() : debate.activeAgents}
          elapsedMs={isReplay ? 0 : debate.elapsedMs}
          selectedPhase={selectedPhase}
          onSelectPhase={setSelectedPhase}
          isFlash={
            isReplay
              ? (replayData?.config_json as Record<string, unknown>)?.mode === 'flash'
              : debate.mode === 'flash'
          }
        />

        {/* Stop button */}
        {!isReplay && status === 'running' && (
          <div className="flex items-center justify-end">
            <button onClick={debate.stop} className="px-4 py-1.5 text-xs bg-red-50 hover:bg-red-100 rounded-lg border border-red-200 text-red-600 transition-colors">
              终止任务
            </button>
          </div>
        )}

        {/* Streaming output card */}
        {!isReplay && debate.streamingAgent && debate.streamingText && (
          <StreamingCard agent={debate.streamingAgent} text={debate.streamingText} />
        )}

        {/* Full-width phase content — skip for Flash (no debate phases to show) */}
        {!isFlash && (
          <AttackResponsePanel
            messages={messages}
            currentRound={currentRound}
            selectedPhase={selectedPhase ?? (phase === 'idle' || phase === 'error' ? null : phase === 'done' ? 'done' : phase)}
            interruptData={isReplay ? null : debate.interruptData}
            onRespondInterrupt={debate.respondToInterrupt}
          />
        )}

        {/* Results section: show in done view */}
        {isDone && code && (!selectedPhase || selectedPhase === 'done') && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <span className="text-lg">{isFlash ? '⚡' : '📦'}</span>
              <h2 className="text-base font-bold text-gray-800">{isFlash ? 'Flash 交付' : '最终交付'}</h2>
              {isFlash && (
                <span className="px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-700 rounded-full">
                  快速生成
                </span>
              )}
              {metrics && (
                <div className="flex items-center gap-3 ml-auto text-xs text-gray-400">
                  {!isFlash && <span>{metrics.total_rounds} 轮</span>}
                  <span>{((metrics.total_tokens ?? 0) / 1000).toFixed(1)}k tokens</span>
                  <span>{((metrics.total_latency_ms ?? 0) / 1000).toFixed(1)}s</span>
                  <span>${(metrics.cost_usd ?? 0).toFixed(2)}</span>
                </div>
              )}
            </div>

            <CodeEditor code={code} language={language} />

            {isFlash ? (
              <div className="bg-white rounded-lg border border-amber-200 p-5 space-y-3">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
                  <span className="text-sm font-medium text-green-700">自测验证通过</span>
                </div>
                <p className="text-xs text-gray-600 leading-relaxed">
                  代码已通过 Coder Agent 自测，基本功能验证正常。如需安全、性能、正确性深度审查，请使用 Pro 模式。
                </p>
              </div>
            ) : (
              qualityReport && qualityReport.star_rating > 0 && (
                <QualityReportPanel report={qualityReport} confidence={confidence} />
              )
            )}
          </div>
        )}

        {/* Done actions */}
        {isDone && (
          <div className="flex items-center justify-center gap-3 pt-4 pb-8">
            <button
              onClick={() => { if (!isReplay) debate.reset(); navigate('/dashboard'); }}
              className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium text-white transition-colors"
            >
              {isReplay ? '返回任务中心' : '新建任务'}
            </button>
          </div>
        )}

        {!isReplay && debate.error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center justify-between">
            <p className="text-red-600 text-sm">{debate.error}</p>
            <button onClick={() => { debate.reset(); navigate('/dashboard'); }} className="shrink-0 ml-4 px-4 py-1.5 bg-white hover:bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-700">
              重试
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
