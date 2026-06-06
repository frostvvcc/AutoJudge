import { useState, useRef, useEffect } from 'react';

interface Props {
  phase: string;
  onPlanSelect: (plan: string) => void;
  onPlanChat: (message: string) => void;
  onArbitrationAccept: () => void;
  onStrategyAccept: () => void;
  onStrategyReject: (message: string) => void;
  onStop: () => void;
}

type PhaseKey = 'plan' | 'debate' | 'arbitration' | 'fixing' | 'done';

function isPhaseDock(phase: string): phase is PhaseKey {
  return ['plan', 'debate', 'arbitration', 'fixing', 'done'].includes(phase);
}

export default function UserInteractionDock({
  phase,
  onPlanSelect,
  onPlanChat,
  onArbitrationAccept,
  onStrategyAccept,
  onStrategyReject,
  onStop,
}: Props) {
  const [chatInput, setChatInput] = useState('');
  const [rejectInput, setRejectInput] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [prevPhase, setPrevPhase] = useState(phase);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const rejectInputRef = useRef<HTMLInputElement>(null);

  // Phase transition animation
  useEffect(() => {
    if (phase !== prevPhase) {
      setIsTransitioning(true);
      const timer = setTimeout(() => {
        setPrevPhase(phase);
        setIsTransitioning(false);
        setChatInput('');
        setRejectInput('');
        setShowRejectInput(false);
      }, 150);
      return () => clearTimeout(timer);
    }
  }, [phase, prevPhase]);

  // Auto-focus reject input when shown
  useEffect(() => {
    if (showRejectInput) {
      rejectInputRef.current?.focus();
    }
  }, [showRejectInput]);

  const handleChatSubmit = () => {
    const trimmed = chatInput.trim();
    if (!trimmed) return;
    onPlanChat(trimmed);
    setChatInput('');
  };

  const handleRejectSubmit = () => {
    const trimmed = rejectInput.trim();
    if (!trimmed) return;
    onStrategyReject(trimmed);
    setRejectInput('');
    setShowRejectInput(false);
  };

  const handleChatKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleChatSubmit();
    }
  };

  const handleRejectKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleRejectSubmit();
    }
    if (e.key === 'Escape') {
      setShowRejectInput(false);
      setRejectInput('');
    }
  };

  const activePhase = isTransitioning ? prevPhase : phase;
  const validPhase = isPhaseDock(activePhase) ? activePhase : null;

  if (!validPhase) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50">
      {/* Top edge gradient */}
      <div className="h-px bg-gradient-to-r from-transparent via-gray-200 to-transparent" />

      <div
        className={`bg-white/95 backdrop-blur-sm border-t border-gray-200 shadow-lg px-6 py-3 transition-opacity duration-150 ${
          isTransitioning ? 'opacity-0' : 'opacity-100'
        }`}
      >
        <div className="max-w-5xl mx-auto">
          {/* Phase indicator */}
          <div className="flex items-center gap-2 mb-2">
            <div className={`w-1.5 h-1.5 rounded-full ${
              validPhase === 'done' ? 'bg-green-500' : 'bg-blue-500 animate-pulse'
            }`} />
            <span className="text-xs text-gray-500">
              {validPhase === 'plan' && '方案选择阶段'}
              {validPhase === 'debate' && '辩论进行中'}
              {validPhase === 'arbitration' && '等待裁决确认'}
              {validPhase === 'fixing' && '修复策略确认'}
              {validPhase === 'done' && '任务已完成'}
            </span>
          </div>

          {/* Phase-specific content */}
          <div className="flex items-center gap-3">
            {validPhase === 'plan' && (
              <>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onPlanSelect('A')}
                    className="px-4 py-2 text-xs font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
                  >
                    选择方案A
                  </button>
                  <button
                    onClick={() => onPlanSelect('B')}
                    className="px-4 py-2 text-xs font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
                  >
                    选择方案B
                  </button>
                  <button
                    onClick={() => onPlanSelect('auto')}
                    className="px-4 py-2 text-xs font-medium text-gray-400 bg-gray-100 border border-gray-200 rounded-lg hover:text-gray-700 transition-colors"
                  >
                    交给Coder选择
                  </button>
                </div>
                <div className="h-5 w-px bg-gray-200" />
                <div className="flex-1 flex items-center gap-2">
                  <input
                    ref={inputRef}
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={handleChatKeyDown}
                    placeholder="和 Coder 聊聊你的想法..."
                    className="flex-1 bg-gray-100 border border-gray-200 rounded-lg px-3 py-2 text-xs text-gray-600 placeholder-gray-600 focus:outline-none focus:border-blue-600/50 transition-colors"
                  />
                  <button
                    onClick={handleChatSubmit}
                    disabled={!chatInput.trim()}
                    className={`px-3 py-2 rounded-lg text-xs transition-colors ${
                      chatInput.trim()
                        ? 'bg-blue-600/30 text-blue-600 border border-blue-600/40 hover:bg-blue-600/50'
                        : 'bg-gray-100 text-gray-600 border border-gray-200 cursor-not-allowed'
                    }`}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                    </svg>
                  </button>
                </div>
              </>
            )}

            {validPhase === 'debate' && (
              <button
                onClick={onStop}
                className="px-4 py-2 text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 transition-colors flex items-center gap-2"
              >
                <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                  <rect x="6" y="6" width="12" height="12" rx="1" />
                </svg>
                终止辩论
              </button>
            )}

            {validPhase === 'arbitration' && (
              <>
                <button
                  onClick={onArbitrationAccept}
                  className="px-4 py-2 text-xs font-medium text-green-600 bg-green-50 border border-green-200 rounded-lg hover:bg-green-100 transition-colors"
                >
                  接受裁决
                </button>
                <button
                  onClick={onStop}
                  className="px-4 py-2 text-xs font-medium text-yellow-700 bg-yellow-50 border border-yellow-200 rounded-lg hover:bg-yellow-100 transition-colors"
                >
                  我有异议
                </button>
              </>
            )}

            {validPhase === 'fixing' && (
              <>
                <div className="flex items-center gap-2">
                  <button
                    onClick={onStrategyAccept}
                    className="px-4 py-2 text-xs font-medium text-green-600 bg-green-50 border border-green-200 rounded-lg hover:bg-green-100 transition-colors"
                  >
                    同意替代方案
                  </button>
                  <button
                    onClick={() => setShowRejectInput(!showRejectInput)}
                    className={`px-4 py-2 text-xs font-medium rounded-lg transition-colors ${
                      showRejectInput
                        ? 'text-yellow-700 bg-yellow-100 border border-yellow-300'
                        : 'text-yellow-700 bg-yellow-50 border border-yellow-200 hover:bg-yellow-100'
                    }`}
                  >
                    不同意，我来说
                  </button>
                </div>
                {showRejectInput && (
                  <>
                    <div className="h-5 w-px bg-gray-200" />
                    <div className="flex-1 flex items-center gap-2">
                      <input
                        ref={rejectInputRef}
                        type="text"
                        value={rejectInput}
                        onChange={(e) => setRejectInput(e.target.value)}
                        onKeyDown={handleRejectKeyDown}
                        placeholder="说说你的想法..."
                        className="flex-1 bg-gray-100 border border-gray-200 rounded-lg px-3 py-2 text-xs text-gray-600 placeholder-gray-600 focus:outline-none focus:border-yellow-600/50 transition-colors"
                      />
                      <button
                        onClick={handleRejectSubmit}
                        disabled={!rejectInput.trim()}
                        className={`px-3 py-2 rounded-lg text-xs transition-colors ${
                          rejectInput.trim()
                            ? 'bg-yellow-600/30 text-yellow-700 border border-yellow-600/40 hover:bg-yellow-600/50'
                            : 'bg-gray-100 text-gray-600 border border-gray-200 cursor-not-allowed'
                        }`}
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                        </svg>
                      </button>
                    </div>
                  </>
                )}
              </>
            )}

            {validPhase === 'done' && (
              <button
                onClick={onStop}
                className="px-4 py-2 text-xs font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors flex items-center gap-2"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                新建任务
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
