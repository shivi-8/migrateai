// Mirrors backend/schemas.py and analyzer/src/types.ts (camelCase JSON).

export type Category =
  | 'Dependencies'
  | 'Connection'
  | 'Schema'
  | 'Model'
  | 'Queries'
  | 'Relationships'
  | 'Database operations';

export type Confidence = 'high' | 'medium' | 'low';
export type NodeKind = 'entry' | 'route' | 'controller' | 'service' | 'model' | 'database' | 'file';
export type EdgeType = 'imports' | 'registers_route' | 'calls_service' | 'uses_model' | 'connects_db';
export type Impact = 'direct' | 'indirect' | 'none';

export interface Finding {
  file: string;
  line: number;
  column: number;
  category: Category;
  pattern: string;
  evidence: string;
  confidence: Confidence;
  detail?: string | null;
}

export interface GraphNode {
  id: string;
  label: string;
  path: string;
  kind: NodeKind;
  mongo: boolean;
  impact: Impact;
  categories: Category[];
  findingCount: number;
  models: string[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: EdgeType;
  label?: string | null;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  impact: Record<string, string[]>;
}

export interface AffectedFile {
  file: string;
  kind: NodeKind;
  findingCount: number;
  categories: Category[];
}

export interface Summary {
  filesScanned: number;
  filesWithFindings: number;
  totalFindings: number;
  byCategory: Record<string, number>;
  byConfidence: Record<string, number>;
  modelCount: number;
  models: string[];
  driver: 'mongoose' | 'mongodb' | 'both' | 'none';
  parseFailures: number;
  truncated: boolean;
  nodeCount: number;
  edgeCount: number;
  durationMs: number;
}

export interface MigrationTask {
  id: number;
  file: string;
  line?: number | null;
  model?: string | null;
  sourceOperation?: string | null;
  targetOperation?: string | null;
  action: string;
  reason: string;
  priority: 'high' | 'medium' | 'low';
  status: string;
  manualReview: boolean;
}

export interface MigrationBlocker {
  file: string;
  line?: number | null;
  pattern: string;
  keyword: string;
  severity: 'high' | 'medium' | 'low';
  reason: string;
}

export interface MigrationWarning {
  file?: string;
  line?: number | null;
  operation?: string;
  findingIndex?: number;
  message: string;
}

export interface MigrationPlanSummary {
  findingsReceived: number;
  findingsProcessed: number;
  tasksCreated: number;
  blockersFound: number;
  warningsCount: number;
}

export interface MigrationPlan {
  source: string;
  target: string;
  summary: MigrationPlanSummary;
  blockers: MigrationBlocker[];
  warnings: MigrationWarning[];
  tasks: MigrationTask[];
}

export interface FileChange {
  file: string;
  status: 'modified' | 'created' | 'skipped';
  changes: string[];
  reviewRequired: boolean;
  diff?: string | null;
  reason?: string | null;
}

export interface EngineeringResult {
  migrationId: string;
  status: 'completed' | 'partial' | 'dry_run';
  filesModified: number;
  filesCreated: number;
  filesSkipped: number;
  files: FileChange[];
  unresolvedTasks: number[];
  diffAvailable: boolean;
  prismaSchema?: string | null;
  workspaceDir?: string | null;
}

export interface EngineeringRequest {
  task_ids?: number[] | null;
  dry_run?: boolean;
  require_approval?: boolean;
}

export interface AnalysisResponse {
  id: string;
  source: 'github' | 'sample';
  repositoryUrl: string | null;
  branch: string | null;
  createdAt: string;
  summary: Summary;
  findings: Finding[];
  affectedFiles: AffectedFile[];
  graph: Graph | null;
  warnings: string[];
  plan?: MigrationPlan | null;
  engineering?: EngineeringResult | null;
}

export interface AnalyzeRequest {
  repository_url: string;
  branch?: string | null;
  generate_graph: boolean;
  graph_scope: 'relevant' | 'all';
}
