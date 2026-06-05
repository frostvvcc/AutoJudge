import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import NavBar from '../components/NavBar';
import * as api from '../lib/api';

export default function SettingsPage() {
  const { user, refreshUser } = useAuth();

  const [username, setUsername] = useState(user?.username ?? '');
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  const [showPwSection, setShowPwSection] = useState(false);
  const [oldPw, setOldPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [pwLoading, setPwLoading] = useState(false);
  const [pwMsg, setPwMsg] = useState('');
  const [pwError, setPwError] = useState(false);

  const handleSaveProfile = async () => {
    if (!username.trim() || username === user?.username) return;
    setSaving(true);
    setSaveMsg('');
    try {
      await api.updateProfile(username.trim());
      await refreshUser();
      setSaveMsg('已保存');
    } catch (e: unknown) {
      setSaveMsg(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwMsg('');
    setPwError(false);
    if (newPw.length < 6) { setPwMsg('新密码至少需要6个字符'); setPwError(true); return; }
    if (newPw !== confirmPw) { setPwMsg('两次密码输入不一致'); setPwError(true); return; }
    setPwLoading(true);
    try {
      await api.changePassword(oldPw, newPw);
      setPwMsg('密码已修改');
      setPwError(false);
      setOldPw(''); setNewPw(''); setConfirmPw('');
    } catch (e: unknown) {
      setPwMsg(e instanceof Error ? e.message : '修改失败');
      setPwError(true);
    } finally {
      setPwLoading(false);
    }
  };

  const togglePw = () => {
    setShowPwSection((v) => !v);
    if (showPwSection) { setOldPw(''); setNewPw(''); setConfirmPw(''); setPwMsg(''); setPwError(false); }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />
      <main className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        <h2 className="text-lg font-semibold text-gray-900">个人设置</h2>

        <div className="bg-white border border-gray-200 shadow-sm rounded-xl p-6 space-y-5">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-xl font-bold text-white">
              {user?.username?.[0]?.toUpperCase()}
            </div>
            <div>
              <div className="text-gray-900 font-medium">{user?.username}</div>
              <div className="text-sm text-gray-500">{user?.email}</div>
              <div className="text-xs text-gray-400 mt-0.5">
                注册于 {user?.created_at ? new Date(user.created_at).toLocaleDateString('zh-CN') : ''}
              </div>
            </div>
          </div>

          <div className="border-t border-gray-200 pt-4">
            <label className="block text-sm text-gray-600 mb-1.5">用户名</label>
            <div className="flex gap-2">
              <input
                type="text" value={username} onChange={(e) => setUsername(e.target.value)}
                className="flex-1 bg-gray-50 border border-gray-300 rounded-lg px-4 py-2.5 text-sm text-gray-900 focus:outline-none focus:border-blue-500 transition-colors"
              />
              <button
                onClick={handleSaveProfile}
                disabled={saving || !username.trim() || username === user?.username}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-200 disabled:text-gray-400 rounded-lg text-sm font-medium text-white transition-colors"
              >
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
            {saveMsg && <p className="mt-1.5 text-xs text-green-600">{saveMsg}</p>}
          </div>

          <div>
            <label className="block text-sm text-gray-600 mb-1.5">邮箱</label>
            <input type="text" value={user?.email ?? ''} disabled
              className="w-full bg-gray-100 border border-gray-200 rounded-lg px-4 py-2.5 text-sm text-gray-400 cursor-not-allowed"
            />
          </div>
        </div>

        <div className="bg-white border border-gray-200 shadow-sm rounded-xl">
          <button type="button" onClick={togglePw}
            className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-gray-50 transition-colors rounded-xl"
          >
            <span className="text-sm font-medium text-gray-900">修改密码</span>
            <svg className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${showPwSection ? 'rotate-180' : ''}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          <div className={`overflow-hidden transition-all duration-300 ease-in-out ${showPwSection ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0'}`}>
            <form onSubmit={handleChangePassword} className="px-6 pb-6 space-y-4 border-t border-gray-200 pt-4">
              <div>
                <label className="block text-sm text-gray-600 mb-1.5">当前密码</label>
                <input type="password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} required
                  className="w-full bg-gray-50 border border-gray-300 rounded-lg px-4 py-2.5 text-sm text-gray-900 focus:outline-none focus:border-blue-500 transition-colors" />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1.5">新密码</label>
                <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} placeholder="至少6个字符" required minLength={6}
                  className="w-full bg-gray-50 border border-gray-300 rounded-lg px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:border-blue-500 transition-colors" />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1.5">确认新密码</label>
                <input type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} required
                  className="w-full bg-gray-50 border border-gray-300 rounded-lg px-4 py-2.5 text-sm text-gray-900 focus:outline-none focus:border-blue-500 transition-colors" />
              </div>
              {pwMsg && <p className={`text-xs ${pwError ? 'text-red-500' : 'text-green-600'}`}>{pwMsg}</p>}
              <button type="submit" disabled={pwLoading || !oldPw || !newPw || !confirmPw}
                className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-200 disabled:text-gray-400 rounded-lg text-sm font-medium text-white transition-colors">
                {pwLoading ? '修改中...' : '修改密码'}
              </button>
            </form>
          </div>
        </div>
      </main>
    </div>
  );
}
