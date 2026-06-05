import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('两次密码输入不一致');
      return;
    }
    if (password.length < 6) {
      setError('密码至少需要6个字符');
      return;
    }

    setLoading(true);
    try {
      await register(username, email, password);
      navigate('/dashboard');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Left: Brand panel */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-gray-100 to-gray-100 items-center justify-center p-12">
        <div className="max-w-md">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
              <svg className="w-5 h-5 text-gray-900" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
              </svg>
            </div>
            <span className="text-2xl font-bold text-gray-900">AutoJudge</span>
          </div>
          <h2 className="text-3xl font-bold text-gray-900 leading-tight mb-4">
            加入 AutoJudge
            <br />
            <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
              体验 AI 代码审查
            </span>
          </h2>
          <div className="space-y-4 mt-8">
            {[
              '注册即可免费体验',
              '多 Agent 并行审查，覆盖三大维度',
              '实时辩论可视化，透明可追溯',
            ].map((text) => (
              <div key={text} className="flex items-center gap-3">
                <svg className="w-4 h-4 text-blue-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
                <span className="text-sm text-gray-400">{text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right: Form */}
      <div className="flex-1 flex items-center justify-center px-4 sm:px-6">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="lg:hidden text-center mb-8">
            <div className="inline-flex items-center gap-3 mb-3">
              <div className="w-9 h-9 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                <svg className="w-4 h-4 text-gray-900" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
                </svg>
              </div>
              <h1 className="text-xl font-bold text-gray-900">AutoJudge</h1>
            </div>
            <p className="text-sm text-gray-500">AI 驱动的多维代码审查引擎</p>
          </div>

          <form
            onSubmit={handleSubmit}
            className="bg-white border border-gray-200 rounded-xl p-6 space-y-4"
          >
            <h2 className="text-xl font-semibold text-gray-900 text-center">注册</h2>

            {error && (
              <div className="bg-red-900/30 border border-red-800 rounded-lg px-4 py-3 flex items-start gap-2">
                <svg className="w-4 h-4 text-red-400 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                </svg>
                <span className="text-sm text-red-400">{error}</span>
              </div>
            )}

            <div>
              <label htmlFor="reg-username" className="block text-sm text-gray-400 mb-1.5">用户名</label>
              <input
                id="reg-username" type="text" autoComplete="username"
                value={username} onChange={(e) => setUsername(e.target.value)}
                className="w-full bg-gray-100 border border-gray-300 rounded-lg px-4 py-2.5 text-sm text-gray-800 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-all"
                placeholder="2-50个字符" required minLength={2} maxLength={50}
              />
            </div>

            <div>
              <label htmlFor="reg-email" className="block text-sm text-gray-400 mb-1.5">邮箱</label>
              <input
                id="reg-email" type="email" autoComplete="email"
                value={email} onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-gray-100 border border-gray-300 rounded-lg px-4 py-2.5 text-sm text-gray-800 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-all"
                placeholder="your@email.com" required
              />
            </div>

            <div>
              <label htmlFor="reg-password" className="block text-sm text-gray-400 mb-1.5">密码</label>
              <div className="relative">
                <input
                  id="reg-password" type={showPw ? 'text' : 'password'} autoComplete="new-password"
                  value={password} onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-gray-100 border border-gray-300 rounded-lg px-4 py-2.5 pr-10 text-sm text-gray-800 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-all"
                  placeholder="至少6个字符" required minLength={6}
                />
                <button
                  type="button" onClick={() => setShowPw(!showPw)} tabIndex={-1}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-600 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    {showPw ? (
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                    ) : (
                      <>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      </>
                    )}
                  </svg>
                </button>
              </div>
            </div>

            <div>
              <label htmlFor="reg-confirm" className="block text-sm text-gray-400 mb-1.5">确认密码</label>
              <input
                id="reg-confirm" type="password" autoComplete="new-password"
                value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full bg-gray-100 border border-gray-300 rounded-lg px-4 py-2.5 text-sm text-gray-800 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-all"
                placeholder="再次输入密码" required
              />
              {confirmPassword && password !== confirmPassword && (
                <p className="mt-1 text-xs text-red-400">两次密码输入不一致</p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading || !username || !email || !password || !confirmPassword}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-200 disabled:text-gray-500 rounded-lg text-sm font-medium transition-colors text-white flex items-center justify-center gap-2"
            >
              {loading && (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              )}
              {loading ? '注册中...' : '注册'}
            </button>

            <p className="text-center text-sm text-gray-500">
              已有账号？{' '}
              <Link to="/login" className="text-blue-400 hover:text-blue-300 transition-colors">
                去登录
              </Link>
            </p>
          </form>

          <div className="mt-4 text-center">
            <Link to="/" className="text-xs text-gray-600 hover:text-gray-400 transition-colors">
              &larr; 返回首页
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
