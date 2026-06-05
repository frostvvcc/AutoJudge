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
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const rejectRef = useRef<HTMLTextAreaElement>(null);

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

  useEffect(() => {
    if (showRejectInput) {
      rejectRef.current?.focus();
    }
  }, [showRejectInput]);

  const handleChatSubmit = () => {
    const trimmed = chatInput.trim();
    if (!trimmed) return;
    onPlanChat(trimmed);
    setChatInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleRejectSubmit = () => {
    const trimmed = rejectInput.trim();
    if (!trimmed) return;
    onStrategyReject(trimmed);
    setRejectInput('');
    setShowRejectInput(false);
  };

  const handleTextareaKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>, onSubmit: () => void) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  const handleAutoResize = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  };

  const activePhase = isTransitioning ? prevPhase : phase;
  const validPhase = isPhaseDock(activePhase) ? activePhase : null;

  if (!validPhase) return null;

  return (
    <div className="border-t border-gray-800/50 bg-gray-950/80 backdrop-blur-md">
      <div
        className={`max-w-3xl mx-auto px-4 py-3 transition-opacity duration-150 ${
          isTransitioning ? 'opacity-0' : 'opacity-100'
        }`}
      >
        {/* Phase indicator */}
        <div className="flex items-center gap-2 mb-2.5">
          <div className={`w-2 h-2 rounded-full ${
            validPhase === 'done' ? 'bg-green-500' : 'bg-blue-500 animate-pulse'
          }`} />
          <span className="text-xs text-gray-500 font-medium">
            {validPhase === 'plan' && '方案选择阶段'}
            {validPhase === 'debate' && '辩论进行中'}
            {validPhase === 'arbitration' && '等待裁决确认'}
            {validPhase === 'fixing' && '修复策略确认'}
            {validPhase === 'done' && '任务已完成'}
          </span>
        </div>

        {/* Plan phase: buttons + chat input */}
        {validPhase === 'plan' && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <button
                onClick={() => onPlanSelect('A')}
                className="px-4 py-2 text-sm font-medium text-blue-300 bg-blue-500/10 border border-blue-500/20 rounded-xl hover:bg-blue-500/20 transition-colors"
              >
                方案 A
              </button>
              <button
                onClick={() => onPlanSelect('B')}
                className="px-4 py-2 text-sm font-medium text-blue-300 bg-blue-500/10 border border-blue-500/20 rounded-xl hover:bg-blue-500/20 transition-colors"
              >
                方案 B
              </button>
              <button
                onClick={() => onPlanSelect('auto')}
                className="px-4 py-2 text-sm text-gray-400 bg-gray-800/60 border border-gray-700/30 rounded-xl hover:bg-gray-800 hover:text-gray-200 transition-colors"
              >
                交给 Coder 选择
              </button>
            </div>
            <div className="relative">
              <textarea
                ref={textareaRef}
                value={chatInput}
                onChange={(e) => { setChatInput(e.target.value); handleAutoResize(e); }}
                onKeyDown={(e) => handleTextareaKeyDown(e, handleChatSubmit)}
                placeholder="和 Coder 聊聊你的想法..."
                rows={1}
                className="w-full bg-gray-800/60 border border-gray-700/40 rounded-2xl px-4 py-3 pr-12 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-all resize-none"
              />
              <button
                onClick={handleChatSubmit}
                disabled={!chatInput.trim()}
                className={`absolute right-2 bottom-2 w-8 h-8 rounded-lg flex items-center justify-center transition-all ${
                  chatInput.trim()
                    ? 'bg-blue-500 text-white hover:bg-blue-400 shadow-lg shadow-blue-500/20'
                    : 'bg-gray-700 text-gray-500 cursor-not-allowed'
                }`}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" />
                </svg>
              </button>
            </div>
          </div>
        )}

        {/* Debate phase: stop button */}
        {validPhase === 'debate' && (
          <div className="flex items-center justify-center">
            <button
              onClick={onStop}
              className="px-5 py-2.5 text-sm font-medium text-red-300 bg-red-500/10 border border-red-500/20 rounded-xl hover:bg-red-500/20 transition-colors flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
              终止辩论
            </button>
          </div>
        )}

        {/* Arbitration phase */}
        {validPhase === 'arbitration' && (
          <div className="flex items-center justify-center gap-3">
            <button
              onClick={onArbitrationAccept}
              className="px-5 py-2.5 text-sm font-medium text-green-300 bg-green-500/10 border border-green-500/20 rounded-xl hover:bg-green-500/20 transition-colors"
            >
              接受裁决
            </button>
            <button
              onClick={onStop}
              className="px-5 py-2.5 text-sm font-medium text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-xl hover:bg-amber-500/20 transition-colors"
            >
              我有异议
            </button>
          </div>
        )}

        {/* Fixing phase */}
        {validPhase === 'fixing' && (
          <div className="space-y-3">
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={onStrategyAccept}
                className="px-5 py-2.5 text-sm font-medium text-green-300 bg-green-500/10 border border-green-500/20 rounded-xl hover:bg-green-500/20 transition-colors"
              >
                同意替代方案
              </button>
              <button
                onClick={() => setShowRejectInput(!showRejectInput)}
                className={`px-5 py-2.5 text-sm font-medium rounded-xl transition-colors ${
                  showRejectInput
                    ? 'text-amber-300 bg-amber-500/20 border border-amber-500/30'
                    : 'text-amber-300 bg-amber-500/10 border border-amber-500/20 hover:bg-amber-500/20'
                }`}
              >
                不同意，我来说
              </button>
            </div>
            {showRejectInput && (
              <div className="relative">
                <textarea
                  ref={rejectRef}
                  value={rejectInput}
                  onChange={(e) => { setRejectInput(e.target.value); handleAutoResize(e); }}
                  onKeyDown={(e) => {
                    handleTextareaKeyDown(e, handleRejectSubmit);
                    if (e.key === 'Escape') {
                      setShowRejectInput(false);
                      setRejectInput('');
                    }
                  }}
                  placeholder="说说你的想法... (按 Esc 取消)"
                  rows={1}
                  className="w-full bg-gray-800/60 border border-amber-700/30 rounded-2xl px-4 py-3 pr-12 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-all resize-none"
                />
                <button
                  onClick={handleRejectSubmit}
                  disabled={!rejectInput.trim()}
                  className={`absolute right-2 bottom-2 w-8 h-8 rounded-lg flex items-center justify-center transition-all ${
                    rejectInput.trim()
                      ? 'bg-amber-500 text-white hover:bg-amber-400 shadow-lg shadow-amber-500/20'
                      : 'bg-gray-700 text-gray-500 cursor-not-allowed'
                  }`}
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        )}

        {/* Done phase */}
        {validPhase === 'done' && (
          <div className="flex items-center justify-center">
            <button
              onClick={onStop}
              className="px-5 py-2.5 text-sm font-medium text-blue-300 bg-blue-500/10 border border-blue-500/20 rounded-xl hover:bg-blue-500/20 transition-colors flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              新建任务
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
