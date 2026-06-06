import { useEffect, useState } from 'react';
import NavBar from '../components/NavBar';
import * as api from '../lib/api';

interface PrefsData {
  preferences: Record<string, string>;
  stats: { attack_experiences: number; fix_patterns: number };
}

export default function PreferencesPage() {
  const [data, setData] = useState<PrefsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [language, setLanguage] = useState('');
  const [framework, setFramework] = useState('');

  useEffect(() => {
    api.fetchJson<PrefsData>('/api/v1/preferences')
      .then((d) => {
        setData(d);
        setLanguage(d.preferences.preferred_language ?? '');
        setFramework(d.preferences.preferred_framework ?? '');
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.postJson('/api/v1/preferences', {
        preferred_language: language || null,
        preferred_framework: framework || null,
      });
      setData((prev) => prev ? {
        ...prev,
        preferences: { ...prev.preferences, preferred_language: language, preferred_framework: framework },
      } : prev);
    } catch { /* ignore */ }
    setSaving(false);
  };

  const clear = async () => {
    await api.deleteJson('/api/v1/preferences');
    setLanguage('');
    setFramework('');
    setData((prev) => prev ? { ...prev, preferences: {} } : prev);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <NavBar />
        <div className="flex items-center justify-center py-20">
          <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />
      <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">
        <h1 className="text-lg font-bold text-gray-800">编码偏好设置</h1>
        <p className="text-xs text-gray-500">
          系统会自动学习你的编码偏好，也可以手动设置。这些偏好会影响 Coder Agent 的代码风格。
        </p>

        {/* Preference inputs */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">偏好配置</h2>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">编程语言</label>
              <input
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                placeholder="Python"
                className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200"
              />
              <span className="text-[10px] text-gray-400 mt-0.5 block">
                {data?.preferences.preferred_language ? '(自动学习)' : '(未设置)'}
              </span>
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">框架偏好</label>
              <input
                value={framework}
                onChange={(e) => setFramework(e.target.value)}
                placeholder="Flask, FastAPI, React..."
                className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200"
              />
              <span className="text-[10px] text-gray-400 mt-0.5 block">
                {data?.preferences.preferred_framework ? '(自动学习)' : '(未设置)'}
              </span>
            </div>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              onClick={save}
              disabled={saving}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-50"
            >
              {saving ? '保存中...' : '保存'}
            </button>
            <button
              onClick={clear}
              className="px-4 py-2 bg-white hover:bg-gray-50 border border-gray-200 text-gray-600 text-xs rounded-lg transition-colors"
            >
              清空偏好
            </button>
          </div>
        </div>

        {/* Memory stats */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
          <h2 className="text-sm font-semibold text-gray-700">记忆系统统计</h2>
          <p className="text-xs text-gray-500">系统在每次审查中积累经验，提升后续审查质量。</p>
          <div className="grid grid-cols-2 gap-4">
            <StatCard
              label="攻击经验库"
              value={data?.stats.attack_experiences ?? 0}
              unit="条"
              icon="🗡️"
              desc="历史审查发现的安全/性能/正确性问题"
            />
            <StatCard
              label="修复模式库"
              value={data?.stats.fix_patterns ?? 0}
              unit="条"
              icon="🔧"
              desc="成功修复方案的向量化存储"
            />
          </div>
        </div>
      </main>
    </div>
  );
}

function StatCard({ label, value, unit, icon, desc }: { label: string; value: number; unit: string; icon: string; desc: string }) {
  return (
    <div className="px-4 py-3 rounded-lg bg-gray-50 border border-gray-100">
      <div className="flex items-center gap-2 mb-1">
        <span>{icon}</span>
        <span className="text-xs font-semibold text-gray-700">{label}</span>
      </div>
      <div className="text-xl font-bold text-indigo-600">
        {value} <span className="text-xs font-normal text-gray-400">{unit}</span>
      </div>
      <p className="text-[10px] text-gray-400 mt-1">{desc}</p>
    </div>
  );
}
