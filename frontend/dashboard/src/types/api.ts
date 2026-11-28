export type Granularity = "daily" | "weekly" | "monthly" | "course";
export type GraphScope = "cluster" | "student";
export type EdgeMetricMode = "freq" | "mean_time_sec" | "support";

export interface UserPublic {
  user_id: string;
  username: string;
  role: "teacher" | "admin";
  assigned_courses: string[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  user: UserPublic;
}

export interface CourseSummary {
  course_id: string;
  external_code?: string | null;
  title: string;
  start_date?: string | null;
  end_date?: string | null;
}

export interface RunSummary {
  run_id: string;
  mode: string;
  status: string;
  source_dataset: string;
  speed_factor?: string | null;
  events_processed: number;
  started_at?: string | null;
  finished_at?: string | null;
  clustering_algorithm?: string | null;
  active_granularities: string[];
  course_ids: string[];
}

export interface WindowSummary {
  granularity: string;
  window_id: string;
  window_start: string;
  window_end: string;
  student_count: number;
  transition_count: number;
  cluster_count: number;
}

export interface ExplainabilityFeature {
  feature: string;
  z_score: number;
}

export interface SankeyNode {
  id: string;
  name: string;
  window_id: string;
  cluster_id: string;
}

export interface SankeyLink {
  source: string;
  target: string;
  value: number;
}

export interface WindowClusterDistribution {
  window_id: string;
  window_start: string;
  window_end: string;
  counts: Record<string, number>;
  total_students: number;
  transition_count: number;
  centroids: Record<string, Record<string, number>>;
}

export interface ClusterEvolutionResponse {
  run_id: string;
  granularity: string;
  course_id?: string | null;
  windows: WindowClusterDistribution[];
  sankey_nodes: SankeyNode[];
  sankey_links: SankeyLink[];
}

export interface ClusterStudentItem {
  student_id: string;
  cluster_id: number;
  previous_cluster_id?: number | null;
  transition_detected: boolean;
  distance_to_centroid?: number | null;
  is_outlier: boolean;
  features: Record<string, number>;
  top_contributing_features: ExplainabilityFeature[];
}

export interface StudentListItem {
  student_id: string;
  latest_window_id: string;
  latest_cluster_id: number;
  transition_count: number;
  total_windows: number;
}

export interface StudentWindowEntry {
  window_id: string;
  window_start: string;
  window_end: string;
  algorithm: string;
  cluster_id: number;
  previous_cluster_id?: number | null;
  transition_detected: boolean;
  distance_to_centroid?: number | null;
  is_outlier: boolean;
  features: Record<string, number>;
  top_contributing_features: ExplainabilityFeature[];
  ingested_to_profile_ms: number;
}

export interface StudentTimelineResponse {
  run_id: string;
  course_id?: string | null;
  granularity: string;
  student_id: string;
  history: StudentWindowEntry[];
}

export interface DfgNode {
  code: string;
  label: string;
  kind: "activity" | "boundary";
  category: string;
}

export interface DfgEdge {
  source: string;
  target: string;
  source_kind: "activity" | "boundary";
  target_kind: "activity" | "boundary";
  freq: number;
  total_time_sec: number;
  mean_time_sec: number;
  trace_support_count: number;
  support: number;
}

export interface DfgGraphResponse {
  run_id: string;
  course_id?: string | null;
  granularity: string;
  window_id: string;
  scope: GraphScope;
  scope_id: string;
  trace_count: number;
  nodes: DfgNode[];
  edges: DfgEdge[];
}

export interface ExperimentMetricRecord {
  metric_id?: number | null;
  run_id: string;
  granularity: string;
  window_id: string;
  silhouette_score?: number | null;
  ari_score?: number | null;
  pm_fitness?: number | null;
  pm_precision?: number | null;
  p50_latency_ms?: number | null;
  p95_latency_ms?: number | null;
  p99_latency_ms?: number | null;
  throughput_eps?: number | null;
  computed_at?: string | null;
}

export interface WsWindowUpdateEvent {
  type: "window_updated";
  run_id: string;
  course_id: string;
  granularity: string;
  window_id: string;
  student_id: string;
  cluster_id: number;
  transition_detected: boolean;
  emitted_at: string;
}
