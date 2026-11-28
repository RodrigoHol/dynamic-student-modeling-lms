<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import type { WindowClusterDistribution } from "@/types/api";

const props = defineProps<{
  windows: WindowClusterDistribution[];
}>();

const option = computed(() => {
  const xLabels = props.windows.map((w) => w.window_id);
  const clusterIds = Array.from(
    new Set(props.windows.flatMap((w) => Object.keys(w.counts))),
  ).sort((a, b) => Number(a) - Number(b));

  const series = clusterIds.map((cid) => ({
    name: cid === "-1" ? "Outlier (-1)" : `Clúster ${cid}`,
    type: "bar",
    stack: "total",
    emphasis: { focus: "series" },
    data: props.windows.map((w) => w.counts[cid] ?? 0),
  }));

  return {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    legend: { top: 0 },
    grid: { left: 40, right: 20, top: 40, bottom: 32 },
    xAxis: { type: "category", data: xLabels },
    yAxis: { type: "value", name: "Estudiantes" },
    series,
  };
});
</script>

<template>
  <div class="chart-box">
    <div v-if="windows.length === 0" class="empty-note">
      Sin ventanas materializadas para esta selección.
    </div>
    <VChart v-else :option="option" autoresize class="echart-canvas" />
  </div>
</template>
