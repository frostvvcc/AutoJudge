import { useCallback, useRef, useState } from 'react';
import type {
  DebateMessage,
  DebateResult,
  DebateStatus,
  StreamingAgent,
  WSEvent,
} from '../types/debate';

export function useDebateState() {
  const [status, setStatus] = useState<DebateStatus>('idle');
  const [messages, setMessages] = useState<DebateMessage[]>([]);
  const [currentRound, setCurrentRound] = useState(0);
  const [statusText, setStatusText] = useState('');
  const [result, setResult] = useState<DebateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [streamingAgents, setStreamingAgents] = useState<
    Record<string, StreamingAgent>
  >({});

  // Use ref to batch high-frequency token updates and reduce renders
  const tokenBufferRef = useRef<Record<string, { content: string; round: number }>>({});
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flushTokenBuffer = useCallback(() => {
    const buffer = tokenBufferRef.current;
    if (Object.keys(buffer).length === 0) return;

    setStreamingAgents((prev) => {
      const next = { ...prev };
      for (const [agent, data] of Object.entries(buffer)) {
        const existing = next[agent];
        next[agent] = {
          content: (existing?.content ?? '') + data.content,
          round: data.round,
        };
      }
      return next;
    });
    tokenBufferRef.current = {};
  }, []);

  const handleEvent = useCallback(
    (event: WSEvent) => {
      switch (event.type) {
        case 'status':
          setStatusText(event.content ?? '');
          break;

        case 'round_start':
          setCurrentRound(event.round ?? 0);
          setStatus('running');
          break;

        case 'agent_start':
          setStatusText(`${event.agent} 正在生成...`);
          setStreamingAgents((prev) => ({
            ...prev,
            [event.agent!]: { content: '', round: event.round ?? 0 },
          }));
          break;

        case 'agent_token': {
          const agent = event.agent!;
          const token = event.token ?? '';
          const round = event.round ?? 0;

          // Buffer tokens, flush every 50ms to avoid per-token re-renders
          const buf = tokenBufferRef.current;
          if (buf[agent]) {
            buf[agent].content += token;
          } else {
            buf[agent] = { content: token, round };
          }

          if (!flushTimerRef.current) {
            flushTimerRef.current = setTimeout(() => {
              flushTimerRef.current = null;
              flushTokenBuffer();
            }, 50);
          }
          break;
        }

        case 'message':
          // Flush any remaining tokens before adding the final message
          if (flushTimerRef.current) {
            clearTimeout(flushTimerRef.current);
            flushTimerRef.current = null;
          }
          flushTokenBuffer();

          if (event.agent) {
            setStreamingAgents((prev) => {
              const next = { ...prev };
              delete next[event.agent!];
              return next;
            });
          }
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
          setStreamingAgents({});
          break;

        case 'done':
          setStatus('done');
          setStreamingAgents({});
          break;

        case 'error':
          setError(event.message ?? 'Unknown error');
          setStatus('error');
          setStreamingAgents({});
          break;
      }
    },
    [flushTokenBuffer],
  );

  const reset = useCallback(() => {
    setStatus('idle');
    setMessages([]);
    setCurrentRound(0);
    setStatusText('');
    setResult(null);
    setError(null);
    setStreamingAgents({});
    tokenBufferRef.current = {};
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
  }, []);

  return {
    status,
    messages,
    currentRound,
    statusText,
    result,
    error,
    streamingAgents,
    handleEvent,
    reset,
    setStatus,
  };
}
