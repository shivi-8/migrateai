type StageState = 'done' | 'active' | 'ready' | 'future';

interface Stage {
  name: string;
  caption: string;
  state: StageState;
}

interface Props {
  loading: boolean;
  hasResult: boolean;
  migrating?: boolean;
  hasPlan?: boolean;
  engineeringLoading?: boolean;
  hasEngineering?: boolean;
}

export default function PipelineHeader({
  loading,
  hasResult,
  migrating,
  hasPlan,
  engineeringLoading,
  hasEngineering,
}: Props) {
  const stages: Stage[] = [
    { name: 'Repository', caption: 'Connect GitHub', state: hasResult ? 'done' : loading ? 'active' : 'ready' },
    { name: 'Scanner', caption: 'Find MongoDB code', state: hasResult ? 'done' : loading ? 'active' : 'ready' },
    { name: 'Agent 1', caption: 'Dependency graph', state: hasResult ? 'done' : loading ? 'active' : 'ready' },
    {
      name: 'Agent 2',
      caption: 'Migration planner',
      state: hasPlan ? 'done' : migrating ? 'active' : hasResult ? 'ready' : 'future',
    },
    {
      name: 'Agent 3',
      caption: 'Code engineering',
      state: hasEngineering ? 'done' : engineeringLoading ? 'active' : hasPlan ? 'ready' : 'future',
    },
    { name: 'Validation', caption: 'Test output', state: 'future' },
  ];

  return (
    <ol className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      {stages.map((s, i) => (
        <li
          key={s.name}
          className={[
            'rounded-lg border px-3 py-2.5 transition-colors',
            s.state === 'done' && 'border-neon/40 bg-neon-faint',
            s.state === 'active' && 'animate-pulse border-violet/60 bg-violet-faint',
            s.state === 'ready' && 'border-ink-600 bg-ink-900',
            s.state === 'future' && 'border-ink-700 bg-ink-900/50 opacity-60',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <div className="flex items-center gap-2 text-xs font-medium">
            <span
              className={[
                'inline-block h-1.5 w-1.5 rounded-full',
                s.state === 'done' ? 'bg-neon' : s.state === 'active' ? 'bg-violet' : 'bg-ink-500',
              ].join(' ')}
            />
            <span className={s.state === 'done' ? 'text-neon' : s.state === 'active' ? 'text-violet-soft' : 'text-zinc-300'}>
              {i + 1}. {s.name}
            </span>
          </div>
          <div className="mt-1 text-[11px] text-zinc-500">{s.state === 'future' ? `${s.caption} · later` : s.caption}</div>
        </li>
      ))}
    </ol>
  );
}
