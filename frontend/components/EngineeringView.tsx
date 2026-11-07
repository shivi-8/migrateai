'use client';

import { useState } from 'react';
import type { EngineeringResult, FileChange } from '@/lib/types';

interface Props {
  result: EngineeringResult | null;
  loading: boolean;
  onRunEngineering: (dryRun: boolean) => void;
}

export default function EngineeringView({ result, loading, onRunEngineering }: Props) {
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [activeSubTab, setActiveSubTab] = useState<'diff' | 'schema'>('diff');

  if (!result && !loading) {
    return (
      <div className="rounded-xl border border-ink-600 bg-ink-900/80 p-8 text-center space-y-4">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-violet-faint border border-violet/40 text-violet-soft text-xl">
          ⚙️
        </div>
        <div>
          <h3 className="text-base font-semibold text-zinc-100">Agent 3 — Migration Engineering</h3>
          <p className="mt-1 text-xs text-zinc-400 max-w-lg mx-auto">
            Context-aware code transformation: extracts Mongoose schemas to Prisma, transforms query operations,
            generates the Prisma database client, and produces reviewable unified diffs.
          </p>
        </div>
        <div className="flex justify-center gap-3 pt-2">
          <button
            onClick={() => onRunEngineering(true)}
            className="rounded-lg bg-neon px-5 py-2.5 text-xs font-semibold text-ink-950 transition hover:brightness-110 shadow-neon"
          >
            Generate Migration Preview (Dry Run)
          </button>
          <button
            onClick={() => onRunEngineering(false)}
            className="rounded-lg border border-violet/60 px-5 py-2.5 text-xs font-medium text-violet-soft transition hover:bg-violet-faint"
          >
            Apply to Migration Workspace
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="rounded-xl border border-violet/40 bg-violet-faint p-8 text-center space-y-3 animate-pulse">
        <div className="font-medium text-sm text-violet-soft">
          Agent 3 is inspecting source files, generating Prisma schema, and converting database queries…
        </div>
        <p className="text-xs text-zinc-400">Contextual AST transformation in progress</p>
      </div>
    );
  }

  if (!result) return null;

  const currentFileChange = result.files.find((f) => f.file === selectedFile) || result.files[0];

  return (
    <div className="space-y-4">
      {/* Header and summary cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-ink-600 bg-ink-900/80 p-3">
          <div className="text-xs text-zinc-400">Status</div>
          <div className="mt-1 font-mono text-sm font-semibold capitalize text-neon">
            {result.status.replace('_', ' ')}
          </div>
        </div>
        <div className="rounded-xl border border-ink-600 bg-ink-900/80 p-3">
          <div className="text-xs text-zinc-400">Files Created</div>
          <div className="mt-1 font-mono text-xl font-semibold text-neon">{result.filesCreated}</div>
        </div>
        <div className="rounded-xl border border-ink-600 bg-ink-900/80 p-3">
          <div className="text-xs text-zinc-400">Files Modified</div>
          <div className="mt-1 font-mono text-xl font-semibold text-violet-soft">{result.filesModified}</div>
        </div>
        <div className="rounded-xl border border-ink-600 bg-ink-900/80 p-3">
          <div className="text-xs text-zinc-400">Manual Review Tasks</div>
          <div className="mt-1 font-mono text-xl font-semibold text-zinc-300">
            {result.unresolvedTasks.length}
          </div>
        </div>
      </div>

      {/* Action Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-ink-600 bg-ink-900/80 p-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveSubTab('diff')}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              activeSubTab === 'diff' ? 'bg-violet text-ink-950 font-semibold' : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            File Diffs ({result.files.length})
          </button>
          <button
            onClick={() => setActiveSubTab('schema')}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              activeSubTab === 'schema' ? 'bg-violet text-ink-950 font-semibold' : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            Generated schema.prisma
          </button>
        </div>

        <div className="flex items-center gap-2">
          {result.status === 'dry_run' ? (
            <button
              onClick={() => onRunEngineering(false)}
              className="rounded-lg bg-neon px-3.5 py-1.5 text-xs font-semibold text-ink-950 hover:brightness-110 shadow-neon"
            >
              Apply Changes to Workspace
            </button>
          ) : (
            <span className="text-xs text-neon font-mono">Workspace: {result.workspaceDir}</span>
          )}
        </div>
      </div>

      {/* Main Content Area */}
      {activeSubTab === 'diff' ? (
        <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
          {/* File change list */}
          <div className="space-y-1.5 rounded-xl border border-ink-600 bg-ink-900/80 p-3 max-h-[580px] overflow-y-auto">
            <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">
              Modified & Created Files
            </div>
            {result.files.map((fc) => (
              <button
                key={fc.file}
                onClick={() => setSelectedFile(fc.file)}
                className={`w-full text-left rounded-lg p-2.5 transition text-xs border ${
                  (selectedFile || result.files[0]?.file) === fc.file
                    ? 'border-violet bg-violet-faint text-zinc-100'
                    : 'border-transparent bg-ink-950 text-zinc-400 hover:text-zinc-200'
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="font-mono font-medium truncate">{fc.file}</span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded font-mono uppercase ${
                      fc.status === 'created'
                        ? 'bg-neon-faint text-neon'
                        : fc.status === 'modified'
                        ? 'bg-violet-faint text-violet-soft'
                        : 'bg-zinc-800 text-zinc-400'
                    }`}
                  >
                    {fc.status}
                  </span>
                </div>
                {fc.reviewRequired && (
                  <div className="mt-1 text-[10px] text-amber-400 font-medium">⚠️ Review needed</div>
                )}
                {fc.changes.length > 0 && (
                  <div className="mt-1 text-[10px] text-zinc-500 truncate">{fc.changes[0]}</div>
                )}
              </button>
            ))}
          </div>

          {/* Diff viewer */}
          <div className="rounded-xl border border-ink-600 bg-ink-950 p-4 overflow-x-auto max-h-[580px]">
            {currentFileChange ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between border-b border-ink-700 pb-2">
                  <span className="font-mono text-sm text-zinc-200 font-semibold">
                    {currentFileChange.file}
                  </span>
                  <span className="text-xs text-zinc-400">{currentFileChange.reason}</span>
                </div>

                {currentFileChange.changes.length > 0 && (
                  <ul className="text-xs text-zinc-400 space-y-1 list-disc pl-4">
                    {currentFileChange.changes.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                )}

                {currentFileChange.diff ? (
                  <pre className="text-xs font-mono p-3 rounded-lg bg-ink-900 border border-ink-700 overflow-x-auto leading-relaxed">
                    {currentFileChange.diff.split('\n').map((line, idx) => {
                      let color = 'text-zinc-400';
                      if (line.startsWith('+') && !line.startsWith('+++')) color = 'text-neon bg-neon-faint';
                      else if (line.startsWith('-') && !line.startsWith('---')) color = 'text-red-400 bg-red-950/30';
                      else if (line.startsWith('@@')) color = 'text-violet-soft font-semibold';
                      return (
                        <div key={idx} className={`${color} px-1 rounded-sm`}>
                          {line}
                        </div>
                      );
                    })}
                  </pre>
                ) : (
                  <div className="text-xs text-zinc-500 italic p-4 text-center">
                    New file created without previous version diff.
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-zinc-500 text-center py-12">Select a file to inspect diff</div>
            )}
          </div>
        </div>
      ) : (
        /* Prisma Schema View */
        <div className="rounded-xl border border-ink-600 bg-ink-950 p-4">
          <div className="flex items-center justify-between border-b border-ink-700 pb-2 mb-3">
            <span className="font-mono text-xs text-zinc-300">prisma/schema.prisma</span>
            <span className="text-[11px] text-neon font-mono">PostgreSQL target ORM</span>
          </div>
          <pre className="text-xs font-mono p-4 rounded-lg bg-ink-900 border border-ink-700 overflow-x-auto text-zinc-200 leading-relaxed max-h-[500px]">
            {result.prismaSchema || '// No schema generated'}
          </pre>
        </div>
      )}
    </div>
  );
}
