<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import Button from "primevue/button";
import Card from "primevue/card";
import Column from "primevue/column";
import DataTable from "primevue/datatable";
import Tag from "primevue/tag";
import ClusterDistributionChart from "@/components/charts/ClusterDistributionChart.vue";
import ClusterSankeyChart from "@/components/charts/ClusterSankeyChart.vue";
import { useAnalyticsStore } from "@/stores/analytics";

const store = useAnalyticsStore();
const router = useRouter();

const totalTransitions = computed(() =>
  (store.evolution?.windows ?? []).reduce((acc, w) => acc + w.transition_count, 0),
);

async function handleSelectNode(payload: { windowId: string; clusterId: number }): Promise<void> {
  store.selectedWindowId = payload.windowId;
  store.selectedClusterId = payload.clusterId;
  await store.loadClusterDetail();
}

async function openStudent(studentId: string): Promise<void> {
  store.selectedStudentId = studentId;
  await store.loadStudentDetail();
  await router.push("/student");
}

async function openClusterGraph(): Promise<void> {
  await store.loadClusterDetail();
  await router.push("/process");
}
</script>

<template>
  <div class="view-stack">
    <div class="kpi-row">
      <Card>
        <template #title>{{ store.evolution?.windows.length ?? 0 }}</template>
        <template #subtitle>Ventanas ({{ store.selectedGranularity }})</template>
      </Card>
      <Card>
        <template #title>{{ store.students.length }}</template>
        <template #subtitle>Estudiantes perfilados</template>
      </Card>
      <Card>
        <template #title>{{ totalTransitions }}</template>
        <template #subtitle>Transiciones detectadas</template>
      </Card>
      <Card>
        <template #title>{{ store.clusterStudents.length }}</template>
        <template #subtitle>
          Integrantes en Clúster {{ store.selectedClusterId }} ({{ store.selectedWindowId ?? "-" }})
        </template>
      </Card>
    </div>

    <div class="two-col-grid">
      <Card>
        <template #title>Flujo evolutivo entre clústeres (Sankey)</template>
        <template #subtitle>Haz clic en un nodo para inspeccionar su composición</template>
        <template #content>
          <ClusterSankeyChart
            :nodes="store.evolution?.sankey_nodes ?? []"
            :links="store.evolution?.sankey_links ?? []"
            @select-node="handleSelectNode"
          />
        </template>
      </Card>

      <Card>
        <template #title>Distribución por ventana</template>
        <template #subtitle>Conteo de estudiantes por perfil en cada cierre</template>
        <template #content>
          <ClusterDistributionChart :windows="store.evolution?.windows ?? []" />
        </template>
      </Card>
    </div>

    <Card>
      <template #title>
        <div class="card-header-row">
          <span>
            Integrantes del Clúster {{ store.selectedClusterId }} en ventana
            {{ store.selectedWindowId ?? "-" }}
          </span>
          <Button
            label="Ver grafo DFG del clúster"
            icon="pi pi-sitemap"
            size="small"
            outlined
            @click="openClusterGraph"
          />
        </div>
      </template>
      <template #content>
        <DataTable :value="store.clusterStudents" striped-rows size="small" paginator :rows="10">
          <Column field="student_id" header="Estudiante (Seudónimo)" />
          <Column header="Estado">
            <template #body="{ data }">
              <Tag
                v-if="data.transition_detected"
                severity="warn"
                :value="`Cambió desde C${data.previous_cluster_id}`"
              />
              <Tag v-else severity="success" value="Estable" />
            </template>
          </Column>
          <Column header="Factores explicativos (z-score)">
            <template #body="{ data }">
              <span
                v-for="feat in data.top_contributing_features"
                :key="feat.feature"
                class="feat-chip"
              >
                {{ feat.feature }} ({{ feat.z_score >= 0 ? "+" : "" }}{{ feat.z_score.toFixed(2) }})
              </span>
            </template>
          </Column>
          <Column header="Acción">
            <template #body="{ data }">
              <Button
                label="Ficha explicable"
                icon="pi pi-user"
                size="small"
                text
                @click="openStudent(data.student_id)"
              />
            </template>
          </Column>
        </DataTable>
      </template>
    </Card>
  </div>
</template>
