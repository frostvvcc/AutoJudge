import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import NavBar from '../components/NavBar';
import { useDebate } from '../contexts/DebateContext';
import PipelineProgress from '../components/workspace/PipelineProgress';
import AgentStatusBar from '../components/workspace/AgentStatusBar';
import AttackResponsePanel from '../components/workspace/AttackResponsePanel';
import RealtimeDashboard from '../components/workspace/RealtimeDashboard';
import QualityReportPanel from '../components/workspace/QualityReportPanel';
import CodeEditor from '../components/CodeEditor';
import type { DebatePhase } from '../types/debate';

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

export default function WorkspacePage() {
  const debate = useDebate();
  const navigate = useNavigate();

  const phase = inferPhase(debate.status, debate.statusText);

  const activeAgents = useMemo(() => {
    const set = new Set<string>();
    if (debate.status === 'running') {
      const t = debate.statusText.toLowerCase();
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
  }, [debate.status, debate.statusText]);

  const latestCode = debate.result?.code ?? '';
  const hasResult = debate.result !== null;

  if (debate.status === 'idle') {
    navigate('/');
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-950">
      <NavBar />

      <main className="max-w-7xl mx-auto px-6 py-4 space-y-4">
        {/* Pipeline progress */}
        <PipelineProgress
          phase={phase}
          currentRound={debate.currentRound}
          maxRounds={5}
          statusText={debate.statusText}
        />

        {/* Agent status */}
        <AgentStatusBar activeAgents={activeAgents} />

        {/* Main layout: left 60% + right 40% */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          {/* Left: Debate workspace */}
          <div className="lg:col-span-3 space-y-4">
            {/* Controls */}
            {debate.status === 'running' && (
              <div className="flex items-center justify-end gap-2">
                <button
                  onClick={debate.stop}
                  className="px-3 py-1 text-xs bg-red-900/50 hover:bg-red-800/50 rounded border border-red-800"
                >
                  终止
                </button>
              </div>
            )}

            {/* Attack-Response Panel */}
            <AttackResponsePanel
              messages={debate.messages}
              currentRound={debate.currentRound}
            />

            {/* Loading indicator */}
            {debate.status === 'running' && (
              <div className="flex items-center gap-2 text-gray-500 text-sm p-3">
                <div className="flex gap-1">
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                {debate.statusText || '处理中...'}
              </div>
            )}
          </div>

          {/* Right: Code + Dashboard / Report */}
          <div className="lg:col-span-2 space-y-4">
            {/* Code editor */}
            <CodeEditor
              code={latestCode}
              language={debate.result?.language ?? 'python'}
            />

            {/* Quality Report (when done) */}
            {hasResult && debate.result!.quality_report && (
              <QualityReportPanel
                report={debate.result!.quality_report}
                confidence={debate.result!.confidence}
              />
            )}

            {/* Realtime dashboard (while running) */}
            {!hasResult && (
              <RealtimeDashboard
                messages={debate.messages}
                risk={debate.result?.risk_assessment}
                metrics={debate.result?.metrics}
              />
            )}
          </div>
        </div>

        {/* Done / Error actions */}
        {(debate.status === 'done' || debate.status === 'converged') && (
          <div className="flex items-center justify-center gap-4 pt-4">
            <button
              onClick={() => {
                debate.reset();
                navigate('/');
              }}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium text-white transition-colors"
            >
              新建任务
            </button>
            <button
              onClick={() => navigate('/history')}
              className="px-6 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300 transition-colors"
            >
              查看历史
            </button>
          </div>
        )}

        {debate.error && (
          <div className="bg-red-900/30 border border-red-800 rounded-lg p-4 flex items-center justify-between">
            <p className="text-red-400 text-sm">{debate.error}</p>
            <button
              onClick={() => {
                debate.reset();
                navigate('/');
              }}
              className="shrink-0 ml-4 px-4 py-1.5 bg-gray-800 hover:bg-gray-700 rounded text-sm text-gray-300"
            >
              重试
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
