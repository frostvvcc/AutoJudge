import { useCallback } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { useDebateState } from './hooks/useDebateState';
import InputForm from './components/InputForm';
import DebatePanel from './components/DebatePanel';
import CodeEditor from './components/CodeEditor';
import MetricsBar from './components/MetricsBar';
import RiskGauge from './components/RiskGauge';
import ConsensusIndicator from './components/ConsensusIndicator';

const WS_URL = `ws://${window.location.hostname}:9000/ws/generate`;

export default function App() {
  const ws = useWebSocket(WS_URL);
  const debate = useDebateState();

  const handleSubmit = useCallback(
    (task: string, language: string) => {
      debate.reset();
      debate.setStatus('connecting');

      ws.connect((event) => {
        debate.handleEvent(event);
      });

      setTimeout(() => {
        ws.send({
          type: 'start',
          task,
          language,
          config: {
            max_rounds: 5,
            attackers: ['security', 'performance', 'correctness'],
          },
        });
      }, 500);
    },
    [ws, debate],
  );

  const handleSkipAttacker = useCallback(
    (attacker: string) => {
      ws.send({ type: 'skip_attacker', attacker });
    },
    [ws],
  );

  const handleStop = useCallback(() => {
    ws.send({ type: 'force_stop' });
    ws.close();
  }, [ws]);

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg" />
            <h1 className="text-xl font-bold text-white">AutoJudge</h1>
            <span className="text-sm text-gray-500">
              多维对抗式代码进化引擎
            </span>
          </div>
          {debate.status === 'running' && (
            <span className="text-sm text-yellow-400 animate-pulse">
              {debate.statusText}
            </span>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Input Form */}
        <InputForm
          onSubmit={handleSubmit}
          disabled={debate.status === 'running' || debate.status === 'connecting'}
        />

        {/* Main Content */}
        {debate.status !== 'idle' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left: Debate Panel */}
            <div className="lg:col-span-2 space-y-4">
              <div className="flex items-center justify-between">
                <ConsensusIndicator messages={debate.messages} />
                {debate.status === 'running' && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleSkipAttacker('performance')}
                      className="px-3 py-1 text-xs bg-gray-800 hover:bg-gray-700 rounded border border-gray-700"
                    >
                      跳过性能
                    </button>
                    <button
                      onClick={handleStop}
                      className="px-3 py-1 text-xs bg-red-900/50 hover:bg-red-800/50 rounded border border-red-800"
                    >
                      终止
                    </button>
                  </div>
                )}
              </div>

              <DebatePanel
                messages={debate.messages}
                currentRound={debate.currentRound}
                status={debate.status}
                streamingAgents={debate.streamingAgents}
              />
            </div>

            {/* Right: Code + Metrics */}
            <div className="space-y-4">
              <CodeEditor
                code={debate.result?.code ?? ''}
                language={debate.result?.language ?? 'python'}
              />

              {debate.result && (
                <>
                  <RiskGauge risk={debate.result.risk_assessment} />
                  <MetricsBar metrics={debate.result.metrics} />
                </>
              )}
            </div>
          </div>
        )}

        {/* Error */}
        {debate.error && (
          <div className="bg-red-900/30 border border-red-800 rounded-lg p-4">
            <p className="text-red-400">{debate.error}</p>
          </div>
        )}
      </main>
    </div>
  );
}
