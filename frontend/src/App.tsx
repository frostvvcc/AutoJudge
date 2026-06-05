import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import { useDebate } from './contexts/DebateContext';
import InputForm from './components/InputForm';
import DebatePanel from './components/DebatePanel';
import CodeEditor from './components/CodeEditor';
import MetricsBar from './components/MetricsBar';
import RiskGauge from './components/RiskGauge';
import ConsensusIndicator from './components/ConsensusIndicator';

export default function App() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const debate = useDebate();

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg" />
            <h1 className="text-xl font-bold text-gray-900">AutoJudge</h1>
            <span className="text-sm text-gray-500">
              多维对抗式代码进化引擎
            </span>
          </div>
          <div className="flex items-center gap-4">
            {(debate.status === 'running' || debate.status === 'connecting') && (
              <span className="text-sm text-yellow-400 animate-pulse">
                {debate.statusText}
              </span>
            )}
            <button
              onClick={debate.reset}
              className="text-sm text-blue-400 font-medium hover:text-blue-300 transition-colors"
            >
              新任务
            </button>
            <Link
              to="/history"
              className="text-sm text-gray-400 hover:text-gray-900 transition-colors"
            >
              历史记录
            </Link>
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center text-xs text-gray-900 font-medium">
                {user?.username?.[0]?.toUpperCase()}
              </div>
              <span className="text-sm text-gray-600">{user?.username}</span>
            </div>
            <button
              onClick={() => {
                logout();
                navigate('/login');
              }}
              className="text-sm text-gray-500 hover:text-red-400 transition-colors"
            >
              退出
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Input Form */}
        <InputForm
          onSubmit={debate.submit}
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
                      onClick={() => debate.skipAttacker('performance')}
                      className="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-100 rounded border border-gray-300"
                    >
                      跳过性能
                    </button>
                    <button
                      onClick={debate.stop}
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
                statusText={debate.statusText}
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

        {/* Done / Error actions */}
        {(debate.status === 'done' || debate.status === 'converged') && (
          <div className="text-center">
            <button
              onClick={debate.reset}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium text-white transition-colors"
            >
              新建任务
            </button>
          </div>
        )}

        {debate.error && (
          <div className="bg-red-900/30 border border-red-800 rounded-lg p-4 flex items-center justify-between">
            <p className="text-red-400">{debate.error}</p>
            <button
              onClick={debate.reset}
              className="shrink-0 ml-4 px-4 py-1.5 bg-gray-100 hover:bg-gray-100 rounded text-sm text-gray-600 transition-colors"
            >
              重试
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
