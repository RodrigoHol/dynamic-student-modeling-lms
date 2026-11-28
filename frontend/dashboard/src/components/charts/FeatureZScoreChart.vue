<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import type { ExplainabilityFeature } from "@/types/api";

const props = defineProps<{
  features: ExplainabilityFeature[];
}>();

const option = computed(() => {
  const reversed = [...props.features].reverse();
  return {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 170, right: 28, top: 16, bottom: 28 },
    xAxis: { type: "value", name: "z-score" },
    yAxis: {
      type: "category",
      data: reversed.map((f) => f.feature),
    },
    series: [
      {
        name: "z-score",
        type: "bar",
        data: reversed.map((f) => ({
          value: Number(f.z_score.toFixed(3)),
          itemStyle: { color: f.z_score >= 0 ? "#0d9488" : "#e11d48" },
        })),
      },
    ],
  };
});
</script>

<template>
  <div class="chart-box-sm">
    <div v-if="features.length === 0" class="empty-note">
      Sin factores de explicabilidad registrados.
    </div>
    <VChart v-else :option="option" autoresize class="echart-canvas" />
  </div>
</template>
