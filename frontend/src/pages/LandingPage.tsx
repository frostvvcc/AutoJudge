import { Link } from 'react-router-dom';

const FEATURES = [
  {
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
      </svg>
    ),
    title: 'Security Agent',
    desc: 'SQL 注入、XSS、权限越权等安全漏洞扫描',
    color: 'from-red-500/20 to-red-600/5 border-red-500/30',
    iconColor: 'text-red-400',
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
      </svg>
    ),
    title: 'Performance Agent',
    desc: '时间复杂度、内存泄漏、并发瓶颈分析',
    color: 'from-orange-500/20 to-orange-600/5 border-orange-500/30',
    iconColor: 'text-orange-400',
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    title: 'Correctness Agent',
    desc: '边界条件、逻辑错误、类型安全验证',
    color: 'from-green-500/20 to-green-600/5 border-green-500/30',
    iconColor: 'text-green-400',
  },
];

const STEPS = [
  { num: '01', title: '描述需求', desc: '用自然语言描述你的编码需求，选择目标语言' },
  { num: '02', title: 'Coder 生成', desc: 'AI Coder 生成初版代码和多套备选方案' },
  { num: '03', title: '三维攻击', desc: '安全、性能、正确性三个 Agent 并行审查攻击' },
  { num: '04', title: '辩论修复', desc: 'Coder 逐条回应：接受修复或用证据反驳' },
  { num: '05', title: '仲裁收敛', desc: 'Arbitrator 裁决争议，循环直到所有 Agent 满意' },
  { num: '06', title: '质量报告', desc: 'Judge 输出星级评分、风险评级和使用建议' },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Nav */}
      <header className="border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-6xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
              <svg className="w-4 h-4 text-gray-900" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
              </svg>
            </div>
            <span className="text-lg font-bold text-gray-900">AutoJudge</span>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/login" className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors">
              登录
            </Link>
            <Link
              to="/register"
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium text-white transition-colors"
            >
              免费注册
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="px-6 pt-20 pb-16">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-blue-500/10 border border-blue-500/20 rounded-full text-xs text-blue-400 mb-6">
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
            Multi-Agent Adversarial Code Review
          </div>
          <h1 className="text-4xl sm:text-5xl font-bold text-gray-900 leading-tight mb-6">
            AI 驱动的
            <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
              {' '}多维代码审查{' '}
            </span>
            引擎
          </h1>
          <p className="text-lg text-gray-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            提交编码需求，多个 AI Agent 从安全、性能、正确性三个维度对抗式辩论，
            自动迭代优化，交付经过验证的高质量代码
          </p>
          <div className="flex items-center justify-center gap-4">
            <Link
              to="/register"
              className="px-8 py-3 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-semibold text-white transition-colors shadow-lg shadow-blue-600/20"
            >
              免费体验
            </Link>
            <a
              href="#how-it-works"
              className="px-8 py-3 bg-gray-100 hover:bg-gray-100 border border-gray-300 rounded-lg text-sm font-medium text-gray-600 transition-colors"
            >
              了解工作流程
            </a>
          </div>
        </div>
      </section>

      {/* Feature cards */}
      <section className="px-6 py-16">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-center text-2xl font-bold text-gray-900 mb-3">三维对抗式审查</h2>
          <p className="text-center text-sm text-gray-500 mb-10">每个 Agent 独立审查，互不妥协，直到代码无懈可击</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className={`bg-gradient-to-b ${f.color} border rounded-xl p-6 hover:scale-[1.02] transition-transform`}
              >
                <div className={`${f.iconColor} mb-4`}>{f.icon}</div>
                <h3 className="text-base font-semibold text-gray-900 mb-2">{f.title}</h3>
                <p className="text-sm text-gray-400 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="px-6 py-16 bg-gray-100">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-center text-2xl font-bold text-gray-900 mb-3">工作流程</h2>
          <p className="text-center text-sm text-gray-500 mb-12">从需求到交付，全自动化的代码审查管线</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {STEPS.map((s) => (
              <div key={s.num} className="flex gap-4">
                <div className="shrink-0 w-10 h-10 rounded-lg bg-blue-600/20 flex items-center justify-center text-sm font-bold text-blue-400">
                  {s.num}
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 mb-1">{s.title}</h3>
                  <p className="text-xs text-gray-500 leading-relaxed">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 py-20">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">开始使用 AutoJudge</h2>
          <p className="text-sm text-gray-400 mb-8">注册即可免费体验多 Agent 代码审查</p>
          <Link
            to="/register"
            className="inline-block px-10 py-3 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-semibold text-white transition-colors shadow-lg shadow-blue-600/20"
          >
            免费注册
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-200 px-6 py-8">
        <div className="max-w-6xl mx-auto flex items-center justify-between text-xs text-gray-600">
          <span>&copy; 2026 AutoJudge</span>
          <div className="flex items-center gap-4">
            <a href="https://github.com" className="hover:text-gray-400 transition-colors">GitHub</a>
            <span>v0.3.0</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
