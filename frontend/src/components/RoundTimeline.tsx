interface Props {
  totalRounds: number;
  currentRound: number;
  converged: boolean;
}

export default function RoundTimeline({
  totalRounds,
  currentRound,
  converged,
}: Props) {
  const rounds = Array.from({ length: totalRounds }, (_, i) => i + 1);

  return (
    <div className="flex flex-col items-center">
      {rounds.map((round, idx) => {
        const isCompleted = round < currentRound;
        const isCurrent = round === currentRound;
        const isLast = idx === rounds.length - 1;

        return (
          <div key={round} className="flex flex-col items-center">
            {/* Node */}
            <div className="relative flex items-center gap-3">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center border-2 transition-colors ${
                  isCompleted
                    ? 'bg-green-500/20 border-green-500'
                    : isCurrent
                      ? 'bg-blue-500/20 border-blue-500 ring-4 ring-blue-500/20'
                      : 'bg-gray-100 border-gray-300'
                }`}
              >
                {isCompleted ? (
                  <svg
                    className="w-3.5 h-3.5 text-green-400"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={3}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                ) : (
                  <span
                    className={`text-xs font-semibold ${
                      isCurrent ? 'text-blue-400' : 'text-gray-500'
                    }`}
                  >
                    {round}
                  </span>
                )}
              </div>

              <span
                className={`text-xs whitespace-nowrap ${
                  isCompleted
                    ? 'text-green-400'
                    : isCurrent
                      ? 'text-blue-400 font-semibold'
                      : 'text-gray-600'
                }`}
              >
                Round {round}
                {isCurrent && !converged && (
                  <span className="ml-1.5 inline-block w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
                )}
              </span>
            </div>

            {/* Connector line */}
            {!isLast && (
              <div
                className={`w-0.5 h-6 ${
                  isCompleted ? 'bg-green-300' : 'bg-gray-200'
                }`}
              />
            )}
          </div>
        );
      })}

      {converged && (
        <div className="mt-3 text-center">
          <span className="text-xs text-green-400 font-medium">
            共识达成
          </span>
        </div>
      )}
    </div>
  );
}
