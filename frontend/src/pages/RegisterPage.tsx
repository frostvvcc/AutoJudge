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
      navigate('/');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg" />
            <h1 className="text-2xl font-bold text-white">AutoJudge</h1>
          </div>
          <p className="text-gray-400">多维对抗式代码进化引擎</p>
        </div>

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-5"
        >
          <h2 className="text-xl font-semibold text-white text-center">注册</h2>

          {error && (
            <div className="bg-red-900/30 border border-red-800 rounded-lg px-4 py-2 text-sm text-red-400">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="reg-username" className="block text-sm text-gray-400 mb-1.5">用户名</label>
            <input
              id="reg-username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
              placeholder="2-50个字符，支持中英文、数字、下划线"
              required
              minLength={2}
              maxLength={50}
            />
          </div>

          <div>
            <label htmlFor="reg-email" className="block text-sm text-gray-400 mb-1.5">邮箱</label>
            <input
              id="reg-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
              placeholder="your@email.com"
              required
            />
          </div>

          <div>
            <label htmlFor="reg-password" className="block text-sm text-gray-400 mb-1.5">密码</label>
            <input
              id="reg-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
              placeholder="至少6个字符"
              required
              minLength={6}
            />
          </div>

          <div>
            <label htmlFor="reg-confirm" className="block text-sm text-gray-400 mb-1.5">确认密码</label>
            <input
              id="reg-confirm"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
              placeholder="再次输入密码"
              required
            />
            {confirmPassword && password !== confirmPassword && (
              <p className="mt-1 text-xs text-red-400">两次密码输入不一致</p>
            )}
          </div>

          <button
            type="submit"
            disabled={loading || !username || !email || !password || !confirmPassword}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg text-sm font-medium transition-colors text-white"
          >
            {loading ? '注册中...' : '注册'}
          </button>

          <p className="text-center text-sm text-gray-500">
            已有账号？{' '}
            <Link to="/login" className="text-blue-400 hover:text-blue-300">
              去登录
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
