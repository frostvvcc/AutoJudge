import type { DegradationData } from '../../contexts/DebateContext';

interface Props {
  data: DegradationData;
}

const LEVEL_INFO: Record<string, { label: string; desc: string; color: string }> = {
  L1: {
    label: 'L1 精简审查',
    desc: '减少辩论轮数、跳过交叉评审，核心审查流程保持运行',
    color: 'border-yellow-300 bg-yellow-50',
  },
  L2: {
    label: 'L2 快速生成',
    desc: '跳过多轮辩论，仅执行单次代码生成',
    color: 'border-orange-300 bg-orange-50',
  },
  L3: {
    label: 'L3 不可用',
    desc: '所有降级手段已耗尽，请稍后重试',
    color: 'border-red-300 bg-red-50',
  },
};

const CB_LABELS: Record<string, { text: string; dot: string }> = {
  closed: { text: '正常', dot: '🟢' },
  'half-open': { text: '恢复试探中', dot: '🟡' },
  open: { text: '已熔断', dot: '🔴' },
};

export default function DegradationBanner({ data }: Props) {
  const info = LEVEL_INFO[data.level] ?? LEVEL_INFO.L1;
  const cb = CB_LABELS[data.circuit_breaker_state] ?? CB_LABELS.closed;

  return (
    <div className={`rounded-xl border-2 ${info.color} px-4 py-3`}>
      <div className="flex items-start gap-3">
        <span className="text-lg mt-0.5">⚠️</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-bold text-gray-800">服务弹性保护已触发</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-white border border-gray-200 font-mono">
              {info.label}
            </span>
          </div>
          <p className="text-xs text-gray-600 leading-relaxed">
            检测到 API 异常：{data.reason}
          </p>
          <p className="text-xs text-gray-500 mt-1">
            影响：{info.desc}
          </p>
          <div className="flex items-center gap-1.5 mt-2 text-xs text-gray-500">
            <span>熔断器状态：</span>
            <span>{cb.dot} {cb.text}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
