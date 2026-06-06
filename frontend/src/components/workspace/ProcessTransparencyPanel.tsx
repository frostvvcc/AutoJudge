import type { DebateResult } from '../../types/debate';
import type { TestResultData } from '../../contexts/DebateContext';

interface Props {
  result: DebateResult;
  testResult?: TestResultData | null;
}

export default function ProcessTransparencyPanel({ result, testResult }: Props) {
  const pt = result.metadata?.process_transparency as Record<string, unknown> | undefined;
  const complexity = (pt?.complexity as string) ?? 'unknown';
  const memoryReads = (pt?.memory_reads as number) ?? 0;
  const memoryWrites = (pt?.memory_writes_findings as number) ?? 0;
  const consensusStatus = (pt?.consensus_status as Record<string, unknown>) ?? {};
  const testVerify = testResult ?? (pt?.test_verification as TestResultData | null);
  const degradation = result.metadata?.degradation_level as string | undefined;

  const cplxLabel: Record<string, { text: string; dot: string }> = {
    simple: { text: '简单', dot: '🟢' },
    medium: { text: '中等', dot: '🟡' },
    hard: { text: '困难', dot: '🔴' },
  };
  const cplx = cplxLabel[complexity] ?? cplxLabel.medium;

  const converged = result.converged;
  const consensusEntries = Object.entries(
    (consensusStatus?.status as Record<string, boolean>) ?? {},
  );

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center gap-2">
        <span className="text-sm">🔍</span>
        <h4 className="text-sm font-semibold text-gray-700">审查过程透视</h4>
      </div>

      <div className="p-4 grid grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
        {/* Complexity */}
        <InfoBlock label="任务复杂度">
          <span className="font-semibold">{cplx.dot} {cplx.text}</span>
        </InfoBlock>

        {/* Rounds */}
        <InfoBlock label="辩论轮数">
          <span className="font-semibold">
            {result.debate?.total_rounds ?? result.metrics?.total_rounds ?? 0} 轮
          </span>
          {converged && (
            <span className="text-green-600 ml-1">(共识收敛)</span>
          )}
        </InfoBlock>

        {/* Consensus */}
        {consensusEntries.length > 0 && (
          <InfoBlock label="共识状态">
            <div className="flex gap-2">
              {consensusEntries.map(([agent, ok]) => (
                <span key={agent} className={ok ? 'text-green-600' : 'text-red-500'}>
                  {ok ? '✅' : '❌'} {agent.charAt(0).toUpperCase() + agent.slice(1)}
                </span>
              ))}
            </div>
          </InfoBlock>
        )}

        {/* Token usage */}
        <InfoBlock label="Token 消耗">
          <span className="font-mono font-semibold">
            {((result.metrics?.total_tokens ?? 0) / 1000).toFixed(1)}k
          </span>
          <span className="text-gray-400 ml-1">
            (${(result.metrics?.cost_usd ?? 0).toFixed(3)})
          </span>
        </InfoBlock>

        {/* Memory */}
        <InfoBlock label="记忆系统">
          <div className="flex gap-3">
            <span>📥 调用 {memoryReads} 条经验</span>
            <span>📤 新增 {memoryWrites} 条</span>
          </div>
        </InfoBlock>

        {/* Test verification */}
        {testVerify && (
          <InfoBlock label="代码验证">
            <span className={testVerify.passed ? 'text-green-600 font-semibold' : 'text-red-500 font-semibold'}>
              {testVerify.passed ? '✅ 通过' : '❌ 未通过'}
            </span>
            {(testVerify.tests_passed > 0 || testVerify.tests_failed > 0) && (
              <span className="text-gray-500 ml-1">
                ({testVerify.tests_passed} 通过 / {testVerify.tests_failed} 失败)
              </span>
            )}
          </InfoBlock>
        )}

        {/* Degradation */}
        {degradation && (
          <InfoBlock label="弹性保护">
            <span className="text-amber-600 font-semibold">
              ⚠️ {degradation}
            </span>
          </InfoBlock>
        )}

        {!degradation && (
          <InfoBlock label="弹性保护">
            <span className="text-green-600">未触发（API 全程正常）</span>
          </InfoBlock>
        )}
      </div>
    </div>
  );
}

function InfoBlock({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-gray-400 mb-1">{label}</div>
      <div className="text-gray-700">{children}</div>
    </div>
  );
}
