import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useDebate } from '../contexts/DebateContext';

export default function NavBar() {
  const { user, logout } = useAuth();
  const debate = useDebate();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isActive = (path: string) =>
    location.pathname === path ? 'text-blue-400 font-medium' : 'text-gray-400 hover:text-gray-900';

  const runningCount = debate.status === 'running' || debate.status === 'connecting' ? 1 : 0;

  const handleLogout = () => {
    logout();
    setMobileOpen(false);
    navigate('/login', { replace: true });
  };

  const NAV_ITEMS = [
    { to: '/dashboard', label: '任务中心' },
    { to: '/history', label: '历史记录' },
    { to: '/preferences', label: '偏好' },
    { to: '/settings', label: '设置' },
  ];

  return (
    <header className="border-b border-gray-200 px-4 sm:px-6 py-3 sm:py-4 relative">
      <div className="flex items-center justify-between max-w-7xl mx-auto">
        {/* Logo */}
        <Link to="/dashboard" className="flex items-center gap-2 sm:gap-3 shrink-0">
          <div className="w-7 h-7 sm:w-8 sm:h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
            <svg className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-gray-900" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
            </svg>
          </div>
          <h1 className="text-lg sm:text-xl font-bold text-gray-900">AutoJudge</h1>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-4">
          {NAV_ITEMS.map((item) => (
            <Link key={item.to} to={item.to} className={`text-sm transition-colors ${isActive(item.to)}`}>
              {item.label}
            </Link>
          ))}
          {runningCount > 0 && (
            <button
              onClick={() => navigate('/workspace/live')}
              className="flex items-center gap-1.5 text-sm text-yellow-400 animate-pulse"
            >
              <span className="w-2 h-2 bg-yellow-400 rounded-full" />
              进行中({runningCount})
            </button>
          )}
        </nav>

        {/* Desktop user */}
        <div className="hidden md:flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500/30 to-purple-500/30 border border-gray-300 flex items-center justify-center text-xs text-gray-900 font-medium">
              {user?.username?.[0]?.toUpperCase()}
            </div>
            <span className="text-sm text-gray-600">{user?.username}</span>
          </div>
          <button
            onClick={handleLogout}
            className="text-sm text-gray-500 hover:text-red-400 transition-colors"
          >
            退出
          </button>
        </div>

        {/* Mobile hamburger */}
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="md:hidden p-2 text-gray-400 hover:text-gray-900 transition-colors"
          aria-label="菜单"
        >
          {mobileOpen ? (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
            </svg>
          )}
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden absolute top-full left-0 right-0 bg-white border-b border-gray-200 z-50">
          <div className="px-4 py-3 border-b border-gray-200 flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-500/30 to-purple-500/30 border border-gray-300 flex items-center justify-center text-sm text-gray-900 font-medium">
              {user?.username?.[0]?.toUpperCase()}
            </div>
            <div>
              <div className="text-sm text-gray-900 font-medium">{user?.username}</div>
              <div className="text-xs text-gray-500">{user?.email}</div>
            </div>
          </div>
          <nav className="py-2">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setMobileOpen(false)}
                className={`block px-4 py-3 text-sm transition-colors ${isActive(item.to)}`}
              >
                {item.label}
              </Link>
            ))}
            {runningCount > 0 && (
              <button
                onClick={() => {
                  setMobileOpen(false);
                  navigate('/workspace/live');
                }}
                className="w-full text-left px-4 py-3 text-sm text-yellow-400"
              >
                <span className="w-2 h-2 bg-yellow-400 rounded-full inline-block mr-2" />
                任务进行中
              </button>
            )}
          </nav>
          <div className="border-t border-gray-200 py-2">
            <button
              onClick={handleLogout}
              className="w-full text-left px-4 py-3 text-sm text-red-400 hover:bg-gray-50 transition-colors"
            >
              退出登录
            </button>
          </div>
        </div>
      )}
    </header>
  );
}
