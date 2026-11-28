<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import Button from "primevue/button";
import Card from "primevue/card";
import InputText from "primevue/inputtext";
import Message from "primevue/message";
import Password from "primevue/password";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();

const username = ref("docente");
const password = ref("docente123");

async function onSubmit(): Promise<void> {
  const ok = await auth.login(username.value.trim(), password.value);
  if (ok) {
    await router.push("/evolution");
  }
}
</script>

<template>
  <div class="login-shell">
    <Card class="login-card">
      <template #title>Acceso al Tablero Docente (C8)</template>
      <template #subtitle>
        Modelado dinámico e interpretable de patrones estudiantiles
      </template>
      <template #content>
        <form class="login-form" @submit.prevent="onSubmit">
          <Message v-if="auth.error" severity="error" :closable="false">
            {{ auth.error }}
          </Message>

          <div class="field">
            <label for="username">Usuario</label>
            <InputText id="username" v-model="username" class="w-full" required />
          </div>

          <div class="field">
            <label for="password">Contraseña</label>
            <Password
              id="password"
              v-model="password"
              :feedback="false"
              toggle-mask
              fluid
              required
            />
          </div>

          <Button
            type="submit"
            label="Ingresar"
            icon="pi pi-sign-in"
            :loading="auth.loading"
          />

          <p class="hint-text">
            Cuentas demo: <code>docente / docente123</code> (rol <em>teacher</em>) ·
            <code>admin / admin123</code> (rol <em>admin</em>).
          </p>
        </form>
      </template>
    </Card>
  </div>
</template>
