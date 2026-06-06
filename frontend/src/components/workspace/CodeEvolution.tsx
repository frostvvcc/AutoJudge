import { useState, useMemo } from 'react';

interface CodeVersion {
  version: number;
  code: string;
  round: number;
}

interface Props {
  versions: CodeVersion[];
  language: string;
}

interface DiffLine {
  type: 'same' | 'added' | 'removed';
  content: string;
  oldLineNum: number | null;
  newLineNum: number | null;
}

/** Compute the LCS table for two arrays of strings. */
function lcsTable(a: string[], b: string[]): number[][] {
  const m = a.length;
  const n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0) as number[]);
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  return dp;
}

/** Backtrack the LCS table to produce a line-by-line diff. */
function computeDiff(oldLines: string[], newLines: string[]): DiffLine[] {
  const dp = lcsTable(oldLines, newLines);
  const result: DiffLine[] = [];

  let i = oldLines.length;
  let j = newLines.length;

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
      result.push({ type: 'same', content: oldLines[i - 1], oldLineNum: i, newLineNum: j });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      result.push({ type: 'added', content: newLines[j - 1], oldLineNum: null, newLineNum: j });
      j--;
    } else {
      result.push({ type: 'removed', content: oldLines[i - 1], oldLineNum: i, newLineNum: null });
      i--;
    }
  }

  return result.reverse();
}

export default function CodeEvolution({ versions, language }: Props) {
  const sorted = useMemo(() => [...versions].sort((a, b) => a.version - b.version), [versions]);
  const [selected, setSelected] = useState<number[]>(sorted.length > 0 ? [sorted[0].version] : []);

  const handleTabClick = (version: number) => {
    setSelected((prev) => {
      if (prev.length === 1 && prev[0] === version) return prev;
      if (prev.length === 1) return [prev[0], version].sort((a, b) => a - b);
      if (prev.includes(version)) return [version];
      return [version];
    });
  };

  const isDiffMode = selected.length === 2;

  const diffLines = useMemo(() => {
    if (!isDiffMode) return [];
    const oldVer = sorted.find((v) => v.version === selected[0]);
    const newVer = sorted.find((v) => v.version === selected[1]);
    if (!oldVer || !newVer) return [];
    return computeDiff(oldVer.code.split('\n'), newVer.code.split('\n'));
  }, [isDiffMode, selected, sorted]);

  const singleCode = useMemo(() => {
    if (isDiffMode) return '';
    const ver = sorted.find((v) => v.version === selected[0]);
    return ver?.code ?? '';
  }, [isDiffMode, selected, sorted]);

  if (sorted.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-6 text-center text-gray-500 text-sm">
        暂无代码版本
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      {/* Header with version tabs */}
      <div className="flex items-center gap-1 px-4 py-3 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center gap-2 mr-3">
          <svg className="w-4 h-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
          </svg>
          <span className="text-xs font-medium text-gray-400">{language}</span>
        </div>

        <div className="flex items-center gap-1">
          {sorted.map((v) => {
            const isSelected = selected.includes(v.version);
            return (
              <button
                key={v.version}
                onClick={() => handleTabClick(v.version)}
                className={`px-3 py-1.5 rounded text-xs font-semibold transition-colors ${
                  isSelected
                    ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                    : 'bg-gray-100 text-gray-500 border border-gray-200 hover:text-gray-600 hover:border-gray-600'
                }`}
              >
                v{v.version}
                <span className="ml-1.5 text-gray-600 font-normal">R{v.round}</span>
              </button>
            );
          })}
        </div>

        {isDiffMode && (
          <div className="ml-auto flex items-center gap-2 text-xs">
            <span className="flex items-center gap-1 text-green-400">
              <span className="w-2 h-2 rounded-sm bg-green-500/40" />
              added
            </span>
            <span className="flex items-center gap-1 text-red-400">
              <span className="w-2 h-2 rounded-sm bg-red-500/40" />
              removed
            </span>
            <button
              onClick={() => setSelected([selected[1]])}
              className="ml-2 px-2 py-0.5 bg-gray-100 text-gray-400 rounded hover:text-gray-700 transition-colors"
            >
              exit diff
            </button>
          </div>
        )}

        {!isDiffMode && sorted.length > 1 && (
          <span className="ml-auto text-xs text-gray-600">
            click another version to compare
          </span>
        )}
      </div>

      {/* Code content */}
      <div className="max-h-[520px] overflow-auto font-mono text-xs leading-5">
        {isDiffMode ? (
          <table className="w-full border-collapse">
            <tbody>
              {diffLines.map((line, i) => (
                <tr
                  key={i}
                  className={
                    line.type === 'added'
                      ? 'bg-green-50'
                      : line.type === 'removed'
                        ? 'bg-red-50'
                        : ''
                  }
                >
                  <td className="w-10 text-right pr-2 text-gray-600 select-none border-r border-gray-200 px-2">
                    {line.oldLineNum ?? ''}
                  </td>
                  <td className="w-10 text-right pr-2 text-gray-600 select-none border-r border-gray-200 px-2">
                    {line.newLineNum ?? ''}
                  </td>
                  <td className="w-5 text-center select-none">
                    <span
                      className={
                        line.type === 'added'
                          ? 'text-green-400'
                          : line.type === 'removed'
                            ? 'text-red-400'
                            : 'text-gray-700'
                      }
                    >
                      {line.type === 'added' ? '+' : line.type === 'removed' ? '-' : ' '}
                    </span>
                  </td>
                  <td className="pl-2 pr-4">
                    <span
                      className={
                        line.type === 'added'
                          ? 'text-green-300'
                          : line.type === 'removed'
                            ? 'text-red-300'
                            : 'text-gray-300'
                      }
                    >
                      {line.content}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="w-full border-collapse">
            <tbody>
              {singleCode.split('\n').map((line, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="w-10 text-right text-gray-600 select-none border-r border-gray-200 px-2">
                    {i + 1}
                  </td>
                  <td className="pl-4 pr-4 text-gray-600 whitespace-pre">{line}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
