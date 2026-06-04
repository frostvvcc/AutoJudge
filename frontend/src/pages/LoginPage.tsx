import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [loginStr, setLoginStr] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(loginStr, password);
      navigate('/');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '登录失败');
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
          <h2 className="text-xl font-semibold text-white text-center">登录</h2>

          {error && (
            <div className="bg-red-900/30 border border-red-800 rounded-lg px-4 py-2 text-sm text-red-400">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm text-gray-400 mb-1.5">用户名或邮箱</label>
            <input
              type="text"
              value={loginStr}
              onChange={(e) => setLoginStr(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
              placeholder="请输入用户名或邮箱"
              required
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1.5">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
              placeholder="请输入密码"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading || !loginStr || !password}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg text-sm font-medium transition-colors text-white"
          >
            {loading ? '登录中...' : '登录'}
          </button>

          <p className="text-center text-sm text-gray-500">
            还没有账号？{' '}
            <Link to="/register" className="text-blue-400 hover:text-blue-300">
              立即注册
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
