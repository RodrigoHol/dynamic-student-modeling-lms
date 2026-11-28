import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import ClusterEvolutionView from "@/views/ClusterEvolutionView.vue";
import LoginView from "@/views/LoginView.vue";
import MetricsView from "@/views/MetricsView.vue";
import ProcessGraphView from "@/views/ProcessGraphView.vue";
import StudentProfileView from "@/views/StudentProfileView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: LoginView },
    { path: "/", redirect: "/evolution" },
    { path: "/evolution", name: "evolution", component: ClusterEvolutionView },
    { path: "/process", name: "process", component: ProcessGraphView },
    { path: "/student", name: "student", component: StudentProfileView },
    { path: "/metrics", name: "metrics", component: MetricsView },
  ],
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.path !== "/login" && !auth.isAuthenticated) {
    return "/login";
  }
  if (to.path === "/login" && auth.isAuthenticated) {
    return "/evolution";
  }
  return true;
});

export default router;
