import type {
  ClusterEvolutionResponse,
  ClusterStudentItem,
  CourseSummary,
  DfgGraphResponse,
  ExperimentMetricRecord,
  Granularity,
  GraphScope,
  RunSummary,
  StudentListItem,
  StudentTimelineResponse,
  TokenResponse,
  UserPublic,
  WindowSummary,
} from "@/types/api";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

async function apiFetch<T>(
  path: string,
  token: string | null,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const resp = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!resp.ok) {
    let detail = `Error HTTP ${resp.status}`;
    try {
      const errBody = (await resp.json()) as { detail?: string };
      if (errBody.detail) {
        detail = errBody.detail;
      }
    } catch {
      // ignore non-json error body
    }
    throw new Error(detail);
  }
  return (await resp.json()) as T;
}

export const apiClient = {
  login(username: string, password: string): Promise<TokenResponse> {
    return apiFetch<TokenResponse>("/api/v1/auth/login", null, {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },

  me(token: string): Promise<UserPublic> {
    return apiFetch<UserPublic>("/api/v1/auth/me", token);
  },

  listCourses(token: string): Promise<CourseSummary[]> {
    return apiFetch<CourseSummary[]>("/api/v1/courses", token);
  },

  listRuns(token: string, courseId?: string | null): Promise<RunSummary[]> {
    const q = courseId ? `?course_id=${encodeURIComponent(courseId)}` : "";
    return apiFetch<RunSummary[]>(`/api/v1/runs${q}`, token);
  },

  listWindows(
    token: string,
    runId: string,
    granularity?: Granularity,
    courseId?: string | null,
  ): Promise<WindowSummary[]> {
    const params = new URLSearchParams();
    if (granularity) params.set("granularity", granularity);
    if (courseId) params.set("course_id", courseId);
    const qs = params.toString();
    return apiFetch<WindowSummary[]>(
      `/api/v1/runs/${encodeURIComponent(runId)}/windows${qs ? `?${qs}` : ""}`,
      token,
    );
  },

  getClusterEvolution(
    token: string,
    runId: string,
    granularity: Granularity,
    courseId?: string | null,
  ): Promise<ClusterEvolutionResponse> {
    const params = new URLSearchParams({ granularity });
    if (courseId) params.set("course_id", courseId);
    return apiFetch<ClusterEvolutionResponse>(
      `/api/v1/runs/${encodeURIComponent(runId)}/clusters/evolution?${params.toString()}`,
      token,
    );
  },

  listClusterStudents(
    token: string,
    runId: string,
    granularity: Granularity,
    windowId: string,
    clusterId: number,
    courseId?: string | null,
  ): Promise<ClusterStudentItem[]> {
    const params = new URLSearchParams({ granularity, window_id: windowId });
    if (courseId) params.set("course_id", courseId);
    return apiFetch<ClusterStudentItem[]>(
      `/api/v1/runs/${encodeURIComponent(runId)}/clusters/${clusterId}/students?${params.toString()}`,
      token,
    );
  },

  listStudents(
    token: string,
    runId: string,
    granularity: Granularity,
    courseId?: string | null,
  ): Promise<StudentListItem[]> {
    const params = new URLSearchParams({ granularity });
    if (courseId) params.set("course_id", courseId);
    return apiFetch<StudentListItem[]>(
      `/api/v1/runs/${encodeURIComponent(runId)}/students?${params.toString()}`,
      token,
    );
  },

  getStudentTimeline(
    token: string,
    runId: string,
    studentId: string,
    granularity: Granularity,
  ): Promise<StudentTimelineResponse> {
    const params = new URLSearchParams({ granularity });
    return apiFetch<StudentTimelineResponse>(
      `/api/v1/runs/${encodeURIComponent(runId)}/students/${encodeURIComponent(studentId)}?${params.toString()}`,
      token,
    );
  },

  getDfg(
    token: string,
    runId: string,
    granularity: Granularity,
    windowId: string,
    scope: GraphScope,
    scopeId: string,
  ): Promise<DfgGraphResponse> {
    const params = new URLSearchParams({
      granularity,
      window_id: windowId,
      scope,
      scope_id: scopeId,
    });
    return apiFetch<DfgGraphResponse>(
      `/api/v1/runs/${encodeURIComponent(runId)}/dfg?${params.toString()}`,
      token,
    );
  },

  listRunMetrics(
    token: string,
    runId: string,
    granularity?: Granularity,
  ): Promise<ExperimentMetricRecord[]> {
    const qs = granularity ? `?granularity=${encodeURIComponent(granularity)}` : "";
    return apiFetch<ExperimentMetricRecord[]>(
      `/api/v1/runs/${encodeURIComponent(runId)}/metrics${qs}`,
      token,
    );
  },
};

export function buildWebSocketUrl(runId: string): string {
  if (API_BASE.startsWith("http")) {
    const url = new URL(API_BASE);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = `/ws/runs/${encodeURIComponent(runId)}`;
    return url.toString();
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/runs/${encodeURIComponent(runId)}`;
}
