import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="text-center">
        <div className="text-6xl font-bold text-gray-800 mb-2">404</div>
        <h1 className="text-xl font-semibold text-gray-900 mb-2">页面未找到</h1>
        <p className="text-sm text-gray-500 mb-8">你访问的页面不存在或已被移除</p>
        <div className="flex items-center justify-center gap-3">
          <Link
            to="/"
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium text-white transition-colors"
          >
            返回首页
          </Link>
          <Link
            to="/history"
            className="px-6 py-2.5 bg-gray-100 hover:bg-gray-100 border border-gray-300 rounded-lg text-sm text-gray-600 transition-colors"
          >
            查看历史
          </Link>
        </div>
      </div>
    </div>
  );
}
