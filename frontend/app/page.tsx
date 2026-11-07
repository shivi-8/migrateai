'use client';

import { useMemo, useState } from 'react';
import DependencyGraph from '@/components/DependencyGraph';
import EngineeringView from '@/components/EngineeringView';
import FindingsTable from '@/components/FindingsTable';
import MigrationPlanView from '@/components/MigrationPlanView';
import NodeDetails from '@/components/NodeDetails';
import PipelineHeader from '@/components/PipelineHeader';
import RepositoryForm from '@/components/RepositoryForm';
import SummaryCards from '@/components/SummaryCards';
import {
  analyzeRepository,
  analyzeSample,
  runEngineering,
  runMigrationPlan,
} from '@/lib/api';
import type { AnalysisResponse, AnalyzeRequest, EngineeringResult, MigrationPlan } from '@/lib/types';

type Tab = 'graph' | 'findings' | 'plan' | 'engineering';

export default function Home() {
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [migrating, setMigrating] = useState(false);
  const [engineeringLoading, setEngineeringLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('graph');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  async function run(task: () => Promise<AnalysisResponse>) {
    setLoading(true);
    setError(null);
    try {
      const data = await task();
      setResult(data);
      setSelectedId(null);
      setTab(data.graph ? 'graph' : 'findings');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  }

  async function handleGeneratePlan() {
    if (!result) return;
    setMigrating(true);
    setError(null);
    try {
      const plan = await runMigrationPlan(result.id);
      setResult((prev) => (prev ? { ...prev, plan } : prev));
      setTab('plan');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate migration plan.');
    } finally {
      setMigrating(false);
    }
  }

  async function handleRunEngineering(dryRun: boolean = true) {
    if (!result) return;
    setEngineeringLoading(true);
    setError(null);
    try {
      const engResult = await runEngineering(result.id, { dry_run: dryRun });
      setResult((prev) => (prev ? { ...prev, engineering: engResult } : prev));
      setTab('engineering');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run migration engineering.');
    } finally {
      setEngineeringLoading(false);
    }
  }

  const selectedNode = useMemo(
    () => result?.graph?.nodes.find((n) => n.id === selectedId) ?? null,
    [result, selectedId],
  );

  function openFile(file: string) {
    if (result?.graph?.nodes.some((n) => n.id === file)) {
      setSelectedId(file);
      setTab('graph');
    }
  }

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Migrate<span className="text-neon">AI</span>
          </h1>
          <p className="text-sm text-zinc-400">AI-powered software migration workspace</p>
        </div>
        <span className="rounded-full border border-violet/50 bg-violet-faint px-3 py-1 font-mono text-[11px] text-violet-soft">
          Agent 1 (Graph) + Agent 2 (Plan) + Agent 3 (Engineering)
        </span>
      </header>

      <PipelineHeader
        loading={loading}
        hasResult={result !== null}
        migrating={migrating}
        hasPlan={Boolean(result?.plan)}
        engineeringLoading={engineeringLoading}
        hasEngineering={Boolean(result?.engineering)}
      />

      <RepositoryForm
        loading={loading}
        onAnalyze={(req: AnalyzeRequest) => run(() => analyzeRepository(req))}
        onSample={() => run(analyzeSample)}
      />

      {error && (
        <div role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading && (
        <div className="rounded-xl border border-violet/40 bg-violet-faint px-4 py-6 text-center text-sm text-violet-soft">
          Fetching the repository, scanning for MongoDB code and building the dependency graph…
        </div>
      )}

      {result && !loading && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-500">
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-neon" />
              Analysis complete for{' '}
              <span className="font-mono text-zinc-300">
                {result.source === 'sample' ? 'bundled sample app' : `${result.repositoryUrl}${result.branch ? ` @ ${result.branch}` : ''}`}
              </span>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleGeneratePlan}
                disabled={migrating}
                className="inline-flex items-center gap-1.5 rounded-md border border-violet/60 bg-violet-faint px-3 py-1 font-mono text-xs text-violet-soft hover:bg-violet/20 transition disabled:opacity-50"
              >
                <span className={migrating ? 'animate-spin' : ''}>✦</span>
                {migrating ? 'Planning…' : 'Agent 2 Plan'}
              </button>

              <button
                onClick={() => handleRunEngineering(true)}
                disabled={engineeringLoading}
                className="inline-flex items-center gap-1.5 rounded-md border border-neon/60 bg-neon-faint px-3 py-1 font-mono text-xs text-neon hover:bg-neon/20 transition disabled:opacity-50"
              >
                <span className={engineeringLoading ? 'animate-spin' : ''}>⚙</span>
                {engineeringLoading ? 'Engineering…' : 'Agent 3 Engineering'}
              </button>
            </div>
          </div>

          <SummaryCards summary={result.summary} warnings={result.warnings} />

          <div className="flex gap-1 border-b border-ink-700">
            <TabButton active={tab === 'graph'} onClick={() => setTab('graph')} disabled={!result.graph}>
              Dependency graph
            </TabButton>
            <TabButton active={tab === 'findings'} onClick={() => setTab('findings')}>
              Findings ({result.summary.totalFindings})
            </TabButton>
            <TabButton active={tab === 'plan'} onClick={() => setTab('plan')}>
              Migration Plan {result.plan ? `(${result.plan.summary.tasksCreated})` : ''}
            </TabButton>
            <TabButton active={tab === 'engineering'} onClick={() => setTab('engineering')}>
              Migration Engineering {result.engineering ? `(${result.engineering.status})` : ''}
            </TabButton>
          </div>

          {tab === 'graph' && result.graph && (
            <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
              <DependencyGraph graph={result.graph} selectedId={selectedId} onSelect={setSelectedId} />
              <NodeDetails node={selectedNode} graph={result.graph} findings={result.findings} onSelect={setSelectedId} />
            </div>
          )}

          {tab === 'findings' && <FindingsTable findings={result.findings} onOpenFile={openFile} />}

          {tab === 'plan' && (
            result.plan ? (
              <div className="space-y-4">
                <div className="flex justify-end">
                  <button
                    onClick={() => handleRunEngineering(true)}
                    disabled={engineeringLoading}
                    className="rounded-lg bg-neon px-4 py-2 text-xs font-semibold text-ink-950 hover:brightness-110 shadow-neon"
                  >
                    Proceed to Agent 3 (Migration Engineering) →
                  </button>
                </div>
                <MigrationPlanView plan={result.plan} onOpenFile={openFile} />
              </div>
            ) : (
              <div className="rounded-xl border border-ink-700 bg-ink-900/60 p-8 text-center space-y-3">
                <p className="text-zinc-400 text-sm">Agent 2 (Migration Planner) has not generated a plan for this analysis yet.</p>
                <button
                  onClick={handleGeneratePlan}
                  disabled={migrating}
                  className="rounded-lg border border-neon/50 bg-neon-faint px-4 py-2 font-mono text-xs font-semibold text-neon hover:bg-neon/20 transition"
                >
                  {migrating ? 'Generating plan…' : 'Generate Migration Plan Now'}
                </button>
              </div>
            )
          )}

          {tab === 'engineering' && (
            <EngineeringView
              result={result.engineering || null}
              loading={engineeringLoading}
              onRunEngineering={handleRunEngineering}
            />
          )}
        </>
      )}
    </main>
  );
}

function TabButton({
  active,
  disabled,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={[
        '-mb-px border-b-2 px-4 py-2 text-sm transition',
        active ? 'border-violet text-violet-soft font-semibold' : 'border-transparent text-zinc-400 hover:text-zinc-200',
        disabled ? 'cursor-not-allowed opacity-40' : '',
      ].join(' ')}
    >
      {children}
    </button>
  );
}
