import { ref } from "vue";
import { defineStore } from "pinia";
import { apiClient, buildWebSocketUrl } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import type {
  ClusterEvolutionResponse,
  ClusterStudentItem,
  CourseSummary,
  DfgGraphResponse,
  ExperimentMetricRecord,
  Granularity,
  RunSummary,
  StudentListItem,
  StudentTimelineResponse,
  WindowSummary,
  WsWindowUpdateEvent,
} from "@/types/api";

export const useAnalyticsStore = defineStore("analytics", () => {
  const courses = ref<CourseSummary[]>([]);
  const runs = ref<RunSummary[]>([]);
  const windows = ref<WindowSummary[]>([]);
  const students = ref<StudentListItem[]>([]);

  const selectedCourseId = ref<string | null>(null);
  const selectedRunId = ref<string | null>(null);
  const selectedGranularity = ref<Granularity>("weekly");
  const selectedWindowId = ref<string | null>(null);
  const selectedClusterId = ref<number>(0);
  const selectedStudentId = ref<string | null>(null);

  const evolution = ref<ClusterEvolutionResponse | null>(null);
  const clusterStudents = ref<ClusterStudentItem[]>([]);
  const clusterDfg = ref<DfgGraphResponse | null>(null);
  const studentTimeline = ref<StudentTimelineResponse | null>(null);
  const studentDfg = ref<DfgGraphResponse | null>(null);
  const metrics = ref<ExperimentMetricRecord[]>([]);

  const loading = ref(false);
  const error = ref<string | null>(null);
  const wsConnected = ref(false);
  const lastLiveEvent = ref<WsWindowUpdateEvent | null>(null);

  let socket: WebSocket | null = null;
  let refreshTimer: number | null = null;

  function _token(): string {
    const auth = useAuthStore();
    if (!auth.token) throw new Error("Sesión no iniciada");
    return auth.token;
  }

  async function initialize(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const token = _token();
      const [courseList, runList] = await Promise.all([
        apiClient.listCourses(token),
        apiClient.listRuns(token),
      ]);
      courses.value = courseList;
      runs.value = runList;

      if (!selectedCourseId.value && courseList.length > 0) {
        selectedCourseId.value = courseList[0].course_id;
      }
      if (!selectedRunId.value && runList.length > 0) {
        selectedRunId.value = runList[0].run_id;
      }
      if (selectedRunId.value) {
        connectWebSocket(selectedRunId.value);
        await refreshRunData();
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : "Error cargando datos iniciales";
    } finally {
      loading.value = false;
    }
  }

  async function refreshRunData(): Promise<void> {
    if (!selectedRunId.value) return;
    loading.value = true;
    error.value = null;
    try {
      const token = _token();
      const runId = selectedRunId.value;
      const gran = selectedGranularity.value;
      const cid = selectedCourseId.value;

      const [winList, evoResp, studList, runMetrics] = await Promise.all([
        apiClient.listWindows(token, runId, gran, cid),
        apiClient.getClusterEvolution(token, runId, gran, cid),
        apiClient.listStudents(token, runId, gran, cid),
        apiClient.listRunMetrics(token, runId, gran),
      ]);

      windows.value = winList;
      evolution.value = evoResp;
      students.value = studList;
      metrics.value = runMetrics;

      if (winList.length > 0 && !winList.some((w) => w.window_id === selectedWindowId.value)) {
        selectedWindowId.value = winList[winList.length - 1].window_id;
      } else if (winList.length === 0) {
        selectedWindowId.value = null;
      }

      if (studList.length > 0 && !studList.some((s) => s.student_id === selectedStudentId.value)) {
        const transitioning = studList.find((s) => s.transition_count > 0);
        selectedStudentId.value = (transitioning ?? studList[0]).student_id;
      } else if (studList.length === 0) {
        selectedStudentId.value = null;
      }

      if (selectedWindowId.value && evoResp.windows.length > 0) {
        const winDist = evoResp.windows.find((w) => w.window_id === selectedWindowId.value);
        const availableClusters = winDist ? Object.keys(winDist.counts).map(Number) : [];
        if (
          availableClusters.length > 0 &&
          !availableClusters.includes(selectedClusterId.value)
        ) {
          const nonOutlier = availableClusters.find((c) => c >= 0);
          selectedClusterId.value = nonOutlier ?? availableClusters[0];
        }
        await Promise.all([loadClusterDetail(), loadStudentDetail()]);
      } else {
        clusterStudents.value = [];
        clusterDfg.value = null;
        studentTimeline.value = null;
        studentDfg.value = null;
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : "Error actualizando vista analítica";
    } finally {
      loading.value = false;
    }
  }

  async function loadClusterDetail(): Promise<void> {
    if (!selectedRunId.value || !selectedWindowId.value) return;
    const token = _token();
    const [members, dfg] = await Promise.all([
      apiClient.listClusterStudents(
        token,
        selectedRunId.value,
        selectedGranularity.value,
        selectedWindowId.value,
        selectedClusterId.value,
        selectedCourseId.value,
      ),
      apiClient.getDfg(
        token,
        selectedRunId.value,
        selectedGranularity.value,
        selectedWindowId.value,
        "cluster",
        String(selectedClusterId.value),
      ),
    ]);
    clusterStudents.value = members;
    clusterDfg.value = dfg;
  }

  async function loadStudentDetail(): Promise<void> {
    if (!selectedRunId.value || !selectedStudentId.value) return;
    const token = _token();
    const timeline = await apiClient.getStudentTimeline(
      token,
      selectedRunId.value,
      selectedStudentId.value,
      selectedGranularity.value,
    );
    studentTimeline.value = timeline;

    const targetWindow =
      selectedWindowId.value && timeline.history.some((h) => h.window_id === selectedWindowId.value)
        ? selectedWindowId.value
        : timeline.history[timeline.history.length - 1]?.window_id;

    if (targetWindow) {
      const entry = timeline.history.find((h) => h.window_id === targetWindow);
      const [sDfg, cDfg] = await Promise.all([
        apiClient.getDfg(
          token,
          selectedRunId.value,
          selectedGranularity.value,
          targetWindow,
          "student",
          selectedStudentId.value,
        ),
        entry
          ? apiClient.getDfg(
              token,
              selectedRunId.value,
              selectedGranularity.value,
              targetWindow,
              "cluster",
              String(entry.cluster_id),
            )
          : Promise.resolve(null),
      ]);
      studentDfg.value = sDfg;
      if (cDfg) {
        clusterDfg.value = cDfg;
      }
    }
  }

  function connectWebSocket(runId: string): void {
    disconnectWebSocket();
    try {
      socket = new WebSocket(buildWebSocketUrl(runId));
      socket.onopen = () => {
        wsConnected.value = true;
      };
      socket.onclose = () => {
        wsConnected.value = false;
      };
      socket.onmessage = (evt) => {
        try {
          const parsed = JSON.parse(evt.data as string) as WsWindowUpdateEvent;
          if (parsed.type === "window_updated") {
            lastLiveEvent.value = parsed;
            if (refreshTimer !== null) {
              window.clearTimeout(refreshTimer);
            }
            refreshTimer = window.setTimeout(() => {
              void refreshRunData();
            }, 600);
          }
        } catch {
          // ignore malformed ws message
        }
      };
    } catch {
      wsConnected.value = false;
    }
  }

  function disconnectWebSocket(): void {
    if (refreshTimer !== null) {
      window.clearTimeout(refreshTimer);
      refreshTimer = null;
    }
    if (socket !== null) {
      socket.close();
      socket = null;
    }
    wsConnected.value = false;
  }

  return {
    courses,
    runs,
    windows,
    students,
    selectedCourseId,
    selectedRunId,
    selectedGranularity,
    selectedWindowId,
    selectedClusterId,
    selectedStudentId,
    evolution,
    clusterStudents,
    clusterDfg,
    studentTimeline,
    studentDfg,
    metrics,
    loading,
    error,
    wsConnected,
    lastLiveEvent,
    initialize,
    refreshRunData,
    loadClusterDetail,
    loadStudentDetail,
    connectWebSocket,
    disconnectWebSocket,
  };
});
