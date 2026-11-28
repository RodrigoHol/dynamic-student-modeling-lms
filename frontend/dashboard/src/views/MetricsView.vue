<script setup lang="ts">
import Card from "primevue/card";
import Column from "primevue/column";
import DataTable from "primevue/datatable";
import { useAnalyticsStore } from "@/stores/analytics";

const store = useAnalyticsStore();

function fmt(value?: number | null, digits = 3): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits);
}
</script>

<template>
  <div class="view-stack">
    <Card>
      <template #title>Métricas experimentales registradas (PostgreSQL)</template>
      <template #subtitle>
        Calidad de clustering (Silueta, ARI), fidelidad de procesos (Fitness, Precision) y latencias
      </template>
      <template #content>
        <DataTable :value="store.metrics" striped-rows size="small" paginator :rows="12">
          <Column field="granularity" header="Granularidad" />
          <Column field="window_id" header="Ventana" />
          <Column header="Silueta">
            <template #body="{ data }">{{ fmt(data.silhouette_score) }}</template>
          </Column>
          <Column header="ARI">
            <template #body="{ data }">{{ fmt(data.ari_score) }}</template>
          </Column>
          <Column header="PM Fitness">
            <template #body="{ data }">{{ fmt(data.pm_fitness) }}</template>
          </Column>
          <Column header="PM Precision">
            <template #body="{ data }">{{ fmt(data.pm_precision) }}</template>
          </Column>
          <Column header="p50 (ms)">
            <template #body="{ data }">{{ fmt(data.p50_latency_ms, 1) }}</template>
          </Column>
          <Column header="p95 (ms)">
            <template #body="{ data }">{{ fmt(data.p95_latency_ms, 1) }}</template>
          </Column>
          <Column header="Throughput (ev/s)">
            <template #body="{ data }">{{ fmt(data.throughput_eps, 1) }}</template>
          </Column>
        </DataTable>
      </template>
    </Card>
  </div>
</template>
