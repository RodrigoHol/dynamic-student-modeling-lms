<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import cytoscape, { type Core } from "cytoscape";
import dagre from "cytoscape-dagre";
import type { DfgEdge, DfgGraphResponse, EdgeMetricMode } from "@/types/api";

cytoscape.use(dagre);

const props = withDefaults(
  defineProps<{
    graph: DfgGraphResponse | null;
    metricMode?: EdgeMetricMode;
    heightPx?: number;
  }>(),
  {
    metricMode: "freq",
    heightPx: 460,
  },
);

const containerRef = ref<HTMLElement | null>(null);
const selectedEdge = ref<DfgEdge | null>(null);
let cy: Core | null = null;

function formatEdgeLabel(edge: DfgEdge, mode: EdgeMetricMode): string {
  if (mode === "mean_time_sec") {
    return `${edge.mean_time_sec.toFixed(1)}s`;
  }
  if (mode === "support") {
    return `${(edge.support * 100).toFixed(0)}%`;
  }
  return `${edge.freq}×`;
}

function edgeValue(edge: DfgEdge, mode: EdgeMetricMode): number {
  if (mode === "mean_time_sec") return edge.mean_time_sec;
  if (mode === "support") return edge.support;
  return edge.freq;
}

function renderGraph(): void {
  if (!containerRef.value) return;
  if (cy) {
    cy.destroy();
    cy = null;
  }
  selectedEdge.value = null;

  const g = props.graph;
  if (!g || g.nodes.length === 0) return;

  const maxVal = Math.max(
    1e-6,
    ...g.edges.map((e) => edgeValue(e, props.metricMode)),
  );

  const elements = [
    ...g.nodes.map((node) => ({
      data: {
        id: node.code,
        label: node.label,
        kind: node.kind,
      },
    })),
    ...g.edges.map((edge, idx) => {
      const ratio = edgeValue(edge, props.metricMode) / maxVal;
      return {
        data: {
          id: `e_${idx}_${edge.source}_${edge.target}`,
          source: edge.source,
          target: edge.target,
          label: formatEdgeLabel(edge, props.metricMode),
          width: 1.8 + ratio * 6.5,
          rawEdge: edge,
        },
      };
    }),
  ];

  cy = cytoscape({
    container: containerRef.value,
    elements,
    style: [
      {
        selector: "node",
        style: {
          label: "data(label)",
          "text-valign": "center",
          "text-halign": "center",
          "background-color": "#0f766e",
          color: "#ffffff",
          "font-size": 11,
          "font-weight": 600,
          width: "label",
          height: 36,
          padding: "12px",
          shape: "round-rectangle",
          "text-wrap": "wrap",
          "text-max-width": "130px",
        },
      },
      {
        selector: 'node[kind = "boundary"]',
        style: {
          "background-color": "#334155",
          shape: "ellipse",
          width: 56,
          height: 36,
        },
      },
      {
        selector: "edge",
        style: {
          width: "data(width)",
          "line-color": "#0284c7",
          "target-arrow-color": "#0284c7",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          label: "data(label)",
          "font-size": 10,
          "text-background-color": "#ffffff",
          "text-background-opacity": 0.9,
          "text-background-padding": "2px",
          color: "#0f172a",
        },
      },
      {
        selector: "edge:selected",
        style: {
          "line-color": "#dc2626",
          "target-arrow-color": "#dc2626",
        },
      },
    ],
    layout: {
      name: "dagre",
      rankDir: "LR",
      nodeSep: 42,
      rankSep: 64,
    } as cytoscape.LayoutOptions,
  });

  cy.on("tap", "edge", (evt) => {
    const raw = evt.target.data("rawEdge") as DfgEdge | undefined;
    selectedEdge.value = raw ?? null;
  });
}

function fitGraph(): void {
  cy?.fit(undefined, 24);
}

watch(() => [props.graph, props.metricMode], renderGraph, { deep: true });
onMounted(renderGraph);
onBeforeUnmount(() => {
  cy?.destroy();
  cy = null;
});
</script>

<template>
  <div class="dfg-wrapper">
    <div class="dfg-toolbar">
      <span v-if="graph && graph.nodes.length > 0" class="meta-pill">
        Trazas: {{ graph.trace_count }} · Nodos: {{ graph.nodes.length }} · Aristas:
        {{ graph.edges.length }}
      </span>
      <button type="button" class="mini-btn" @click="fitGraph">Ajustar vista</button>
    </div>

    <div
      v-if="!graph || graph.nodes.length === 0"
      class="empty-note"
      :style="{ height: `${heightPx}px` }"
    >
      Sin grafo DFG disponible para la selección actual.
    </div>
    <div
      v-else
      ref="containerRef"
      class="cytoscape-canvas"
      :style="{ height: `${heightPx}px` }"
    />

    <div v-if="selectedEdge" class="edge-inspector">
      <strong>{{ selectedEdge.source }} → {{ selectedEdge.target }}</strong> · Frecuencia:
      {{ selectedEdge.freq }} · Tiempo medio: {{ selectedEdge.mean_time_sec.toFixed(2) }} s ·
      Soporte: {{ (selectedEdge.support * 100).toFixed(1) }}%
    </div>
  </div>
</template>
