import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useDebate } from '../contexts/DebateContext';

export default function NavBar() {
  const { user, logout } = useAuth();
  const debate = useDebate();
  const location = useLocation();
  const navigate = useNavigate();

  const isActive = (path: string) =>
    location.pathname === path ? 'text-blue-400 font-medium' : 'text-gray-400 hover:text-white';

  const runningCount = debate.status === 'running' || debate.status === 'connecting' ? 1 : 0;

  return (
    <header className="border-b border-gray-800 px-6 py-4">
      <div className="flex items-center justify-between max-w-7xl mx-auto">
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg" />
            <h1 className="text-xl font-bold text-white">AutoJudge</h1>
          </Link>
          <nav className="flex items-center gap-4">
            <Link to="/" className={`text-sm transition-colors ${isActive('/')}`}>
              任务中心
            </Link>
            <Link to="/history" className={`text-sm transition-colors ${isActive('/history')}`}>
              历史记录
            </Link>
            {runningCount > 0 && (
              <button
                onClick={() => navigate('/')}
                className="flex items-center gap-1.5 text-sm text-yellow-400 animate-pulse"
              >
                <span className="w-2 h-2 bg-yellow-400 rounded-full" />
                进行中({runningCount})
              </button>
            )}
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center text-xs text-white font-medium">
              {user?.username?.[0]?.toUpperCase()}
            </div>
            <span className="text-sm text-gray-300">{user?.username}</span>
          </div>
          <button
            onClick={() => {
              logout();
              navigate('/login');
            }}
            className="text-sm text-gray-500 hover:text-red-400 transition-colors"
          >
            退出
          </button>
        </div>
      </div>
    </header>
  );
}
