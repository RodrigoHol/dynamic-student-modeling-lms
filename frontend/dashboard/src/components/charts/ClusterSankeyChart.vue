<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import type { SankeyLink, SankeyNode } from "@/types/api";

const props = defineProps<{
  nodes: SankeyNode[];
  links: SankeyLink[];
}>();

const emit = defineEmits<{
  selectNode: [payload: { windowId: string; clusterId: number }];
}>();

const option = computed(() => {
  const safeNodes = props.nodes.map((n) => ({
    name: n.id,
    displayName: n.name,
    windowId: n.window_id,
    clusterId: n.cluster_id,
  }));
  return {
    tooltip: {
      trigger: "item",
      triggerOn: "mousemove",
    },
    series: [
      {
        type: "sankey",
        layout: "none",
        emphasis: { focus: "adjacency" },
        nodeAlign: "left",
        data: safeNodes,
        links: props.links,
        label: {
          formatter: (params: { data?: { displayName?: string }; name: string }) =>
            params.data?.displayName ?? params.name,
          fontSize: 11,
        },
        lineStyle: {
          color: "gradient",
          curveness: 0.45,
          opacity: 0.45,
        },
      },
    ],
  };
});

function handleClick(params: unknown): void {
  const evt = params as {
    dataType?: string;
    data?: { windowId?: string; clusterId?: string } | null;
  };
  if (evt.dataType === "node" && evt.data?.windowId && evt.data.clusterId !== undefined) {
    emit("selectNode", {
      windowId: evt.data.windowId,
      clusterId: Number(evt.data.clusterId),
    });
  }
}
</script>

<template>
  <div class="chart-box">
    <div v-if="links.length === 0" class="empty-note">
      Se requieren al menos dos ventanas consecutivas para visualizar transiciones Sankey.
    </div>
    <VChart v-else :option="option" autoresize class="echart-canvas" @click="handleClick" />
  </div>
</template>
