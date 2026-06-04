import { useCallback, useState } from 'react';
import type {
  DebateMessage,
  DebateResult,
  DebateStatus,
  WSEvent,
} from '../types/debate';

export function useDebateState() {
  const [status, setStatus] = useState<DebateStatus>('idle');
  const [messages, setMessages] = useState<DebateMessage[]>([]);
  const [currentRound, setCurrentRound] = useState(0);
  const [statusText, setStatusText] = useState('');
  const [result, setResult] = useState<DebateResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleEvent = useCallback((event: WSEvent) => {
    switch (event.type) {
      case 'status':
        setStatusText(event.content ?? '');
        break;

      case 'round_start':
        setCurrentRound(event.round ?? 0);
        setStatus('running');
        break;

      case 'agent_start':
        setStatusText(`${event.agent} 正在分析...`);
        break;

      case 'message':
        if (event.agent && event.content) {
          setMessages((prev) => [
            ...prev,
            {
              agent: event.agent!,
              content: event.content!,
              round: event.round,
              code: event.code,
            },
          ]);
        }
        break;

      case 'converged':
        setStatus('converged');
        setStatusText(
          `共识达成 (${event.round} 轮) — ${event.reason}`,
        );
        break;

      case 'result':
        setResult(event.data ?? null);
        setStatus('done');
        setStatusText('辩论完成');
        break;

      case 'done':
        setStatus('done');
        break;

      case 'error':
        setError(event.message ?? 'Unknown error');
        setStatus('error');
        break;
    }
  }, []);

  const reset = useCallback(() => {
    setStatus('idle');
    setMessages([]);
    setCurrentRound(0);
    setStatusText('');
    setResult(null);
    setError(null);
  }, []);

  return {
    status,
    messages,
    currentRound,
    statusText,
    result,
    error,
    handleEvent,
    reset,
    setStatus,
  };
}
