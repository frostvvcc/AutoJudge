import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import type { ReactNode } from 'react';
import type {
  BudgetData,
  DebateMessage,
  DebateResult,
  DebateStatus,
  WSEvent,
} from '../types/debate';

export interface InterruptData {
  type: string;
  content?: string;
  round?: number;
  max_rounds?: number;
  unresolved_issues?: Array<Record<string, unknown>>;
  retry_count?: number;
  options?: Array<Record<string, string>>;
  [key: string]: unknown;
}

export interface AnalysisData {
  parsed_requirement: {
    functional: string[];
    constraints: string[];
    implicit: string[];
    edge_cases: string[];
  };
  complexity: string;
  experiences: Array<{
    content: string;
    category: string;
    severity: string;
    session_id?: string;
    similarity?: number;
  }>;
}

export interface TestResultData {
  passed: boolean;
  reason: string;
  tests_passed: number;
  tests_failed: number;
  test_sources: Record<string, number>;
}

export interface DegradationData {
  level: string;
  reason: string;
  circuit_breaker_state: string;
}

interface DebateState {
  status: DebateStatus;
  messages: DebateMessage[];
  currentRound: number;
  statusText: string;
  currentPhase: string;
  result: DebateResult | null;
  error: string | null;
  interruptData: InterruptData | null;
  analysisData: AnalysisData | null;
  testResult: TestResultData | null;
  degradation: DegradationData | null;
  activeAgents: Set<string>;
  elapsedMs: number;
  streamingAgent: string | null;
  streamingText: string;
  visitedPhases: Set<string>;
  budget: BudgetData | null;
  agentStreams: Record<string, string>;
  submit: (task: string, language: string, mode?: string) => void;
  skipAttacker: (attacker: string) => void;
  stop: () => void;
  reset: () => void;
  respondToInterrupt: (response: Record<string, unknown>) => void;
}

const DebateContext = createContext<DebateState | null>(null);

function getWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/api/v1/ws/generate`;
}

export function DebateProvider({ children }: { children: ReactNode }) {
  const wsRef = useRef<WebSocket | null>(null);
  const startTimeRef = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [status, setStatus] = useState<DebateStatus>('idle');
  const [messages, setMessages] = useState<DebateMessage[]>([]);
  const [currentRound, setCurrentRound] = useState(0);
  const [statusText, setStatusText] = useState('');
  const [currentPhase, setCurrentPhase] = useState('idle');
  const [result, setResult] = useState<DebateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [interruptData, setInterruptData] = useState<InterruptData | null>(null);
  const [analysisData, setAnalysisData] = useState<AnalysisData | null>(null);
  const [testResult, setTestResult] = useState<TestResultData | null>(null);
  const [degradation, setDegradation] = useState<DegradationData | null>(null);
  const [activeAgents, setActiveAgents] = useState<Set<string>>(new Set());
  const [elapsedMs, setElapsedMs] = useState(0);
  const [streamingAgent, setStreamingAgent] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState('');
  const [visitedPhases, setVisitedPhases] = useState<Set<string>>(new Set());
  const [budget, setBudget] = useState<BudgetData | null>(null);
  const [agentStreams, setAgentStreams] = useState<Record<string, string>>({});

  const wsSendRef = useRef<(data: Record<string, unknown>) => void>(() => {});
  const reconnectRef = useRef<{ task: string; language: string; mode: string; retries: number } | null>(null);
  const planConfirmedRef = useRef(false);

  useEffect(() => {
    wsSendRef.current = (data: Record<string, unknown>) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify(data));
      }
    };
  });

  const startTimer = useCallback(() => {
    startTimeRef.current = Date.now();
    setElapsedMs(0);
    timerRef.current = setInterval(() => {
      setElapsedMs(Date.now() - startTimeRef.current);
    }, 500);
  }, []);

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const handleEvent = useCallback((event: WSEvent) => {
    switch (event.type) {
      case 'status':
        if (planConfirmedRef.current && (event.content ?? '').includes('方案')) {
          break;
        }
        setStatusText(event.content ?? '');
        break;

      case 'round_start':
        setCurrentRound(event.round ?? 0);
        setStatus('running');
        setActiveAgents(new Set());
        setStreamingAgent(null);
        setStreamingText('');
        setAgentStreams({});
        break;

      case 'agent_start':
        if (planConfirmedRef.current && event.agent === 'coder') {
          break;
        }
        // Don't overwrite phase-specific status text from 'status' events
        setStreamingAgent(event.agent ?? null);
        setStreamingText('');
        if (['security', 'performance', 'correctness'].includes(event.agent ?? '')) {
          setCurrentPhase('debate');
          setVisitedPhases((prev) => { const next = new Set(prev); next.add('debate'); return next; });
        }
        setActiveAgents((prev) => {
          const next = new Set(prev);
          next.add(event.agent!);
          return next;
        });
        setAgentStreams((prev) => ({ ...prev, [event.agent!]: '' }));
        break;

      case 'stream': {
        const raw = event as unknown as Record<string, unknown>;
        const delta = raw.delta as string | undefined;
        const streamAgent = raw.agent as string | undefined;
        if (delta) {
          setStreamingText((prev) => prev + delta);
          if (streamAgent) {
            setAgentStreams((prev) => ({
              ...prev,
              [streamAgent]: (prev[streamAgent] ?? '') + delta,
            }));
          }
        }
        break;
      }

      case 'stream_end':
        if (event.agent) {
          setAgentStreams((prev) => {
            const next = { ...prev };
            delete next[event.agent!];
            return next;
          });
        }
        setStreamingAgent(null);
        setStreamingText('');
        break;

      case 'agent_error': {
        const agentName = event.agent ?? 'unknown';
        const errMsg = (event as unknown as Record<string, unknown>).error as string ?? '';
        const isProxy = (event as unknown as Record<string, unknown>).is_proxy_error as boolean;

        // Remove from active agents
        if (event.agent) {
          setActiveAgents((prev) => {
            const next = new Set(prev);
            next.delete(event.agent!);
            return next;
          });
          setAgentStreams((prev) => {
            const next = { ...prev };
            delete next[event.agent!];
            return next;
          });
        }

        if (isProxy) {
          setError(`API 代理服务异常：${agentName} 调用失败 (${errMsg.substring(0, 80)})。请检查代理服务状态后重试。`);
          setStatus('error');
          setStatusText(`${agentName} API 调用失败`);
        } else {
          setStatusText(`⚠️ ${agentName} 调用失败，系统将尝试继续...`);
        }
        break;
      }

      case 'budget_update': {
        const raw = event as unknown as Record<string, unknown>;
        setBudget({
          spent: (raw.spent as number) ?? 0,
          total: (raw.total as number) ?? 100000,
          phase: (raw.phase as string) ?? '',
          agent: (raw.agent as string) ?? '',
          by_agent: (raw.by_agent as Record<string, number>) ?? {},
          cache_read: (raw.cache_read as number) ?? 0,
          cache_creation: (raw.cache_creation as number) ?? 0,
        });
        break;
      }

      case 'message':
        if (event.agent) {
          setStreamingAgent(null);
          setStreamingText('');
          setAgentStreams((prev) => {
            const next = { ...prev };
            delete next[event.agent!];
            return next;
          });
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
          setActiveAgents((prev) => {
            const next = new Set(prev);
            next.delete(event.agent!);
            return next;
          });
        }
        break;

      case 'converged':
        setStatus('converged');
        setStatusText(
          `共识达成 (${event.round} 轮) — ${event.reason}`,
        );
        break;

      case 'result': {
        const resultData = event.data ?? null;
        setResult(resultData);
        setActiveAgents(new Set());
        reconnectRef.current = null;
        const rounds = resultData?.metrics?.total_rounds ?? resultData?.debate?.total_rounds ?? 0;
        const hasCode = Boolean(resultData?.code);
        const degraded = resultData?.metadata?.degradation_level;
        if (!hasCode && rounds === 0) {
          const reason = degraded
            ? `服务降级 (${degraded})，未生成代码`
            : resultData?.convergence_reason || '任务未能正常完成';
          setError(reason);
          setCurrentPhase('error');
          setStatus('error');
          setStatusText(reason);
        } else {
          setCurrentPhase('done');
          setStatus('done');
          setStatusText('完成');
        }
        break;
      }

      case 'analysis_complete': {
        const raw = event as unknown as Record<string, unknown>;
        setAnalysisData({
          parsed_requirement: (raw.parsed_requirement as AnalysisData['parsed_requirement']) ?? { functional: [], constraints: [], implicit: [], edge_cases: [] },
          complexity: (raw.complexity as string) ?? 'medium',
          experiences: (raw.experiences as AnalysisData['experiences']) ?? [],
        });
        setCurrentPhase('analysis');
        break;
      }

      case 'test_result': {
        const raw = event as unknown as Record<string, unknown>;
        setTestResult({
          passed: (raw.passed as boolean) ?? false,
          reason: (raw.reason as string) ?? '',
          tests_passed: (raw.tests_passed as number) ?? 0,
          tests_failed: (raw.tests_failed as number) ?? 0,
          test_sources: (raw.test_sources as Record<string, number>) ?? {},
        });
        break;
      }

      case 'degradation': {
        const raw = event as unknown as Record<string, unknown>;
        setDegradation({
          level: (raw.level as string) ?? '',
          reason: (raw.reason as string) ?? '',
          circuit_breaker_state: (raw.circuit_breaker_state as string) ?? 'closed',
        });
        break;
      }

      case 'phase_change': {
        const newPhase = event.phase ?? 'idle';
        if (newPhase === 'coding') {
          planConfirmedRef.current = false;
        }
        if (newPhase !== 'idle') {
          setVisitedPhases((prev) => {
            const next = new Set(prev);
            next.add(newPhase);
            return next;
          });
        }
        const PHASE_ORDER = ['idle', 'analysis', 'plan', 'coding', 'debate', 'arbitration', 'fixing', 'judging', 'user_decision', 'done'];
        setCurrentPhase((prev) => {
          const prevIdx = PHASE_ORDER.indexOf(prev);
          const newIdx = PHASE_ORDER.indexOf(newPhase);
          if (prevIdx >= 0 && newIdx >= 0 && newIdx < prevIdx) {
            return prev;
          }
          return newPhase;
        });
        setActiveAgents(new Set());
        break;
      }

      case 'plan_proposal':
        if (!planConfirmedRef.current) {
          setCurrentPhase('plan');
        }
        break;

      case 'arbitration_complete':
        setCurrentPhase('arbitration');
        setStatusText(
          `仲裁完成: ${event.overall_verdict ?? ''} (${event.disputes_count ?? 0}条争议)`,
        );
        break;

      case 'interrupt': {
        const payload = (event as unknown as Record<string, unknown>).payload as InterruptData | undefined;
        if (!payload) break;
        const iType = payload.type;
        if (iType === 'plan_review' || iType === 'resolution_decision') {
          setInterruptData(payload);
          if (iType === 'plan_review') {
            setCurrentPhase('plan');
            setStatusText('等待用户选择方案...');
          } else {
            setCurrentPhase('user_decision');
            setStatusText('等待用户决策...');
          }
        } else {
          wsSendRef.current({ type: 'interrupt_response', data: { action: 'auto_select' } });
        }
        break;
      }

      case 'done':
        setStatus('done');
        break;

      case 'error':
        setError(event.message ?? '未知错误');
        setStatus('error');
        break;
    }
  }, []);

  const submit = useCallback(
    (task: string, language: string, mode: string = 'pro') => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      reconnectRef.current = { task, language, mode, retries: 0 };

      setStatus('connecting');
      setMessages([]);
      setCurrentRound(0);
      setStatusText('连接中...');
      setCurrentPhase('idle');
      setResult(null);
      setError(null);
      setInterruptData(null);
      setAnalysisData(null);
      setTestResult(null);
      setDegradation(null);
      setActiveAgents(new Set());
      setStreamingAgent(null);
      setStreamingText('');
      setBudget(null);
      setAgentStreams({});
      startTimer();

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
              mode,
              max_rounds: mode === 'flash' ? 1 : 5,
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
        stopTimer();
      };

      ws.onclose = (event) => {
        wsRef.current = null;
        setStatus((prev) => {
          if (prev === 'running' || prev === 'connecting') {
            const rc = reconnectRef.current;
            if (event.code !== 1000 && rc && rc.retries < 3) {
              rc.retries++;
              setError(null);
              setStatusText(`连接断开，正在重连 (${rc.retries}/3)...`);
              setTimeout(() => {
                submit(rc.task, rc.language, rc.mode);
              }, 2000 * rc.retries);
              return 'connecting';
            }
            stopTimer();
            reconnectRef.current = null;
            setError(
              event.code === 1000
                ? '连接已关闭'
                : `连接意外断开 (${event.code || 'unknown'})`,
            );
            return 'error';
          }
          stopTimer();
          reconnectRef.current = null;
          return prev;
        });
      };
    },
    [handleEvent, startTimer, stopTimer],
  );

  const skipAttacker = useCallback(
    (attacker: string) => {
      wsSendRef.current({ type: 'skip_attacker', attacker });
    },
    [],
  );

  const stop = useCallback(() => {
    wsSendRef.current({ type: 'force_stop' });
    stopTimer();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, [stopTimer]);

  const reset = useCallback(() => {
    stopTimer();
    planConfirmedRef.current = false;
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
    setInterruptData(null);
    setAnalysisData(null);
    setTestResult(null);
    setDegradation(null);
    setActiveAgents(new Set());
    setElapsedMs(0);
    setStreamingAgent(null);
    setStreamingText('');
    setVisitedPhases(new Set());
    setBudget(null);
    setAgentStreams({});
  }, [stopTimer]);

  const respondToInterrupt = useCallback((response: Record<string, unknown>) => {
    wsSendRef.current({ type: 'interrupt_response', data: response });
    const itype = interruptData?.type;
    setInterruptData(null);
    if (itype === 'plan_review' && (response.action === 'select' || response.action === 'auto_select')) {
      planConfirmedRef.current = true;
      setCurrentPhase('coding');
      setStatusText('方案已确认，正在准备编码...');
    }
  }, [interruptData]);

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
        interruptData,
        analysisData,
        testResult,
        degradation,
        activeAgents,
        elapsedMs,
        streamingAgent,
        streamingText,
        visitedPhases,
        budget,
        agentStreams,
        submit,
        skipAttacker,
        stop,
        reset,
        respondToInterrupt,
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
