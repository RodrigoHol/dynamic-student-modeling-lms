<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { RouterLink, RouterView, useRouter } from "vue-router";
import Button from "primevue/button";
import Message from "primevue/message";
import Select from "primevue/select";
import Tag from "primevue/tag";
import { useAnalyticsStore } from "@/stores/analytics";
import { useAuthStore } from "@/stores/auth";
import type { Granularity } from "@/types/api";

const auth = useAuthStore();
const store = useAnalyticsStore();
const router = useRouter();

const granularities: { label: string; value: Granularity }[] = [
  { label: "Diaria", value: "daily" },
  { label: "Semanal", value: "weekly" },
  { label: "Mensual", value: "monthly" },
  { label: "Curso completo", value: "course" },
];

const courseOptions = computed(() =>
  store.courses.map((c) => ({ label: `${c.title} (${c.course_id})`, value: c.course_id })),
);
const runOptions = computed(() =>
  store.runs.map((r) => ({
    label: `${r.run_id} [${r.clustering_algorithm ?? r.mode}]`,
    value: r.run_id,
  })),
);
const windowOptions = computed(() =>
  store.windows.map((w) => ({
    label: `${w.window_id} (${w.student_count} est.)`,
    value: w.window_id,
  })),
);

onMounted(async () => {
  if (auth.isAuthenticated) {
    await store.initialize();
  }
});

watch(
  () => auth.isAuthenticated,
  async (loggedIn) => {
    if (loggedIn) {
      await store.initialize();
    } else {
      store.disconnectWebSocket();
    }
  },
);

async function onRunChange(): Promise<void> {
  if (store.selectedRunId) {
    store.connectWebSocket(store.selectedRunId);
    await store.refreshRunData();
  }
}

async function onFilterChange(): Promise<void> {
  await store.refreshRunData();
}

async function onWindowChange(): Promise<void> {
  await Promise.all([store.loadClusterDetail(), store.loadStudentDetail()]);
}

function logout(): void {
  store.disconnectWebSocket();
  auth.logout();
  void router.push("/login");
}
</script>

<template>
  <div class="app-shell">
    <header v-if="auth.isAuthenticated" class="topbar">
      <div class="brand-group">
        <strong>DSM LMS · Analítica Interpretable</strong>
        <Tag
          :severity="store.wsConnected ? 'success' : 'secondary'"
          :value="store.wsConnected ? 'WS En Vivo' : 'WS Offline'"
        />
        <span v-if="store.lastLiveEvent" class="live-badge">
          Última ventana: {{ store.lastLiveEvent.window_id }} ({{ store.lastLiveEvent.granularity }})
        </span>
      </div>

      <nav class="nav-links">
        <RouterLink to="/evolution">Evolución</RouterLink>
        <RouterLink to="/process">Grafos DFG</RouterLink>
        <RouterLink to="/student">Ficha Estudiante</RouterLink>
        <RouterLink to="/metrics">Validación</RouterLink>
      </nav>

      <div class="user-group">
        <span>{{ auth.user?.username }} ({{ auth.user?.role }})</span>
        <Button label="Salir" icon="pi pi-sign-out" size="small" text @click="logout" />
      </div>
    </header>

    <section v-if="auth.isAuthenticated" class="filter-bar">
      <Select
        v-model="store.selectedCourseId"
        :options="courseOptions"
        option-label="label"
        option-value="value"
        placeholder="Curso"
        @change="onFilterChange"
      />
      <Select
        v-model="store.selectedRunId"
        :options="runOptions"
        option-label="label"
        option-value="value"
        placeholder="Corrida (run_id)"
        @change="onRunChange"
      />
      <Select
        v-model="store.selectedGranularity"
        :options="granularities"
        option-label="label"
        option-value="value"
        @change="onFilterChange"
      />
      <Select
        v-model="store.selectedWindowId"
        :options="windowOptions"
        option-label="label"
        option-value="value"
        placeholder="Ventana"
        @change="onWindowChange"
      />
      <Button
        icon="pi pi-refresh"
        label="Actualizar"
        size="small"
        outlined
        :loading="store.loading"
        @click="onFilterChange"
      />
    </section>

    <main class="main-content">
      <Message v-if="store.error" severity="error" :closable="false">
        {{ store.error }}
      </Message>
      <RouterView />
    </main>
  </div>
</template>
