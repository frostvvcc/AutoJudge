import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
} from 'react';
import type { ReactNode } from 'react';
import type {
  DebateMessage,
  DebateResult,
  DebateStatus,
  WSEvent,
} from '../types/debate';

interface DebateState {
  status: DebateStatus;
  messages: DebateMessage[];
  currentRound: number;
  statusText: string;
  currentPhase: string;
  result: DebateResult | null;
  error: string | null;
  submit: (task: string, language: string) => void;
  skipAttacker: (attacker: string) => void;
  stop: () => void;
  reset: () => void;
}

const DebateContext = createContext<DebateState | null>(null);

function getWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/api/v1/ws/generate`;
}

export function DebateProvider({ children }: { children: ReactNode }) {
  const wsRef = useRef<WebSocket | null>(null);

  const [status, setStatus] = useState<DebateStatus>('idle');
  const [messages, setMessages] = useState<DebateMessage[]>([]);
  const [currentRound, setCurrentRound] = useState(0);
  const [statusText, setStatusText] = useState('');
  const [currentPhase, setCurrentPhase] = useState('idle');
  const [result, setResult] = useState<DebateResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleEvent = useCallback((event: WSEvent) => {
    switch (event.type) {
      case 'status':
        setStatusText(event.content ?? '');
        break;

      case 'round_start':
        setCurrentRound(event.round ?? 0);
        setCurrentPhase('debate');
        setStatus('running');
        break;

      case 'agent_start':
        setStatusText(`${event.agent} 正在分析...`);
        break;

      case 'message':
        if (event.agent) {
          setMessages((prev) => [
            ...prev,
            {
              agent: event.agent!,
              content: event.content ?? '',
              round: event.round,
              code: event.code,
              structured: event.structured,
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
        setCurrentPhase('done');
        setStatus('done');
        setStatusText('完成');
        break;

      case 'phase_change':
        setCurrentPhase(event.phase ?? 'idle');
        setStatusText(event.phase ? `进入${event.phase}阶段` : '');
        break;

      case 'plan_proposal':
        setCurrentPhase('plan');
        setStatusText('方案已生成，正在自动选择最佳方案...');
        break;

      case 'arbitration_complete':
        setCurrentPhase('arbitration');
        setStatusText(
          `仲裁完成: ${event.overall_verdict ?? ''} (${event.disputes_count ?? 0}条争议)`,
        );
        break;

      case 'done':
        setStatus('done');
        break;

      case 'error':
        setError(event.message ?? '未知错误');
        setStatus('error');
        break;
    }
  }, []);

  const wsSend = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const submit = useCallback(
    (task: string, language: string) => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      setStatus('connecting');
      setMessages([]);
      setCurrentRound(0);
      setStatusText('连接中...');
      setResult(null);
      setError(null);

      const ws = new WebSocket(getWsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('running');
        setStatusText('已连接，发送任务...');
        const token = localStorage.getItem('access_token');
        ws.send(
          JSON.stringify({
            task,
            language,
            token,
            config: {
              max_rounds: 5,
              attackers: ['security', 'performance', 'correctness'],
            },
          }),
        );
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WSEvent;
          handleEvent(data);
        } catch {
          // ignore malformed messages
        }
      };

      ws.onerror = () => {
        setError('WebSocket 连接失败');
        setStatus('error');
      };

      ws.onclose = (event) => {
        wsRef.current = null;
        setStatus((prev) => {
          if (prev === 'running' || prev === 'connecting') {
            setError(
              event.code === 1000
                ? '连接已关闭'
                : `连接意外断开 (${event.code || 'unknown'})`,
            );
            return 'error';
          }
          return prev;
        });
      };
    },
    [handleEvent],
  );

  const skipAttacker = useCallback(
    (attacker: string) => {
      wsSend({ type: 'skip_attacker', attacker });
    },
    [wsSend],
  );

  const stop = useCallback(() => {
    wsSend({ type: 'force_stop' });
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, [wsSend]);

  const reset = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus('idle');
    setMessages([]);
    setCurrentRound(0);
    setStatusText('');
    setCurrentPhase('idle');
    setResult(null);
    setError(null);
  }, []);

  return (
    <DebateContext.Provider
      value={{
        status,
        messages,
        currentRound,
        statusText,
        currentPhase,
        result,
        error,
        submit,
        skipAttacker,
        stop,
        reset,
      }}
    >
      {children}
    </DebateContext.Provider>
  );
}

export function useDebate(): DebateState {
  const ctx = useContext(DebateContext);
  if (!ctx) throw new Error('useDebate must be inside DebateProvider');
  return ctx;
}
