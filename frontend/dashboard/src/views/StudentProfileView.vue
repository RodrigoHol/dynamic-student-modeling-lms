<script setup lang="ts">
import { computed, ref } from "vue";
import Card from "primevue/card";
import Column from "primevue/column";
import DataTable from "primevue/datatable";
import Select from "primevue/select";
import SelectButton from "primevue/selectbutton";
import Tag from "primevue/tag";
import FeatureZScoreChart from "@/components/charts/FeatureZScoreChart.vue";
import DfgGraphViewer from "@/components/graphs/DfgGraphViewer.vue";
import { useAnalyticsStore } from "@/stores/analytics";
import type { EdgeMetricMode } from "@/types/api";

const store = useAnalyticsStore();
const edgeMode = ref<EdgeMetricMode>("freq");

const edgeModeOptions = [
  { label: "Frecuencia", value: "freq" },
  { label: "Tiempo medio (s)", value: "mean_time_sec" },
  { label: "Soporte (%)", value: "support" },
];

const studentOptions = computed(() =>
  store.students.map((s) => ({
    label: `${s.student_id} (C${s.latest_cluster_id} · ${s.transition_count} cambios)`,
    value: s.student_id,
  })),
);

const currentEntry = computed(() => {
  const hist = store.studentTimeline?.history ?? [];
  if (hist.length === 0) return null;
  return hist.find((h) => h.window_id === store.selectedWindowId) ?? hist[hist.length - 1];
});

async function onStudentChange(): Promise<void> {
  await store.loadStudentDetail();
}
</script>

<template>
  <div class="view-stack">
    <Card>
      <template #title>
        <div class="card-header-row">
          <span>Ficha explicable del estudiante</span>
          <div class="inline-controls">
            <Select
              v-model="store.selectedStudentId"
              :options="studentOptions"
              option-label="label"
              option-value="value"
              filter
              placeholder="Seleccionar estudiante"
              @change="onStudentChange"
            />
            <SelectButton
              v-model="edgeMode"
              :options="edgeModeOptions"
              option-label="label"
              option-value="value"
            />
          </div>
        </div>
      </template>
      <template #subtitle>
        Justificación estadística (z-score) y contraste estructural de secuencias (DFG individual vs.
        clúster)
      </template>
      <template #content>
        <div v-if="currentEntry" class="two-col-grid">
          <div>
            <h4>Perfil en ventana {{ currentEntry.window_id }}</h4>
            <p class="meta-line">
              Algoritmo: <strong>{{ currentEntry.algorithm }}</strong> · Clúster actual:
              <Tag :value="`C${currentEntry.cluster_id}`" severity="info" />
              <Tag
                v-if="currentEntry.transition_detected"
                :value="`Transición desde C${currentEntry.previous_cluster_id}`"
                severity="warn"
              />
            </p>
            <FeatureZScoreChart :features="currentEntry.top_contributing_features" />
          </div>

          <div>
            <h4>Historial de transiciones ({{ store.selectedGranularity }})</h4>
            <DataTable :value="store.studentTimeline?.history ?? []" size="small" striped-rows>
              <Column field="window_id" header="Ventana" />
              <Column field="cluster_id" header="Clúster" />
              <Column header="Transición">
                <template #body="{ data }">
                  <Tag
                    v-if="data.transition_detected"
                    severity="warn"
                    :value="`C${data.previous_cluster_id} → C${data.cluster_id}`"
                  />
                  <span v-else>—</span>
                </template>
              </Column>
              <Column field="ingested_to_profile_ms" header="Latencia (ms)" />
            </DataTable>
          </div>
        </div>
        <div v-else class="empty-note">Selecciona un estudiante para visualizar su ficha.</div>
      </template>
    </Card>

    <div class="two-col-grid">
      <Card>
        <template #title>Ruta individual del estudiante</template>
        <template #subtitle>{{ store.selectedStudentId ?? "-" }}</template>
        <template #content>
          <DfgGraphViewer :graph="store.studentDfg" :metric-mode="edgeMode" :height-px="380" />
        </template>
      </Card>

      <Card>
        <template #title>Ruta consolidada de su clúster</template>
        <template #subtitle>Clúster {{ currentEntry?.cluster_id ?? "-" }}</template>
        <template #content>
          <DfgGraphViewer :graph="store.clusterDfg" :metric-mode="edgeMode" :height-px="380" />
        </template>
      </Card>
    </div>
  </div>
</template>
