<script setup lang="ts">
import { computed, ref } from "vue";
import Card from "primevue/card";
import Select from "primevue/select";
import SelectButton from "primevue/selectbutton";
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

const availableClusters = computed(() => {
  const win = store.evolution?.windows.find((w) => w.window_id === store.selectedWindowId);
  const ids = win ? Object.keys(win.counts).map(Number) : [store.selectedClusterId];
  return ids
    .sort((a, b) => a - b)
    .map((id) => ({
      label: id === -1 ? "Outlier (-1)" : `Clúster ${id}`,
      value: id,
    }));
});

async function onClusterChange(): Promise<void> {
  await store.loadClusterDetail();
}
</script>

<template>
  <div class="view-stack">
    <Card>
      <template #title>
        <div class="card-header-row">
          <span>Grafo de flujo directo (DFG) por clúster</span>
          <div class="inline-controls">
            <Select
              v-model="store.selectedClusterId"
              :options="availableClusters"
              option-label="label"
              option-value="value"
              placeholder="Clúster"
              @change="onClusterChange"
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
        Topología descubierta con PM4Py y consolidada aditivamente desde Neo4j
      </template>
      <template #content>
        <DfgGraphViewer :graph="store.clusterDfg" :metric-mode="edgeMode" :height-px="500" />
      </template>
    </Card>
  </div>
</template>
