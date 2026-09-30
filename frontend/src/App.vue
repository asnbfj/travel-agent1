<template>
  <a-layout class="app-layout">
    <AppHeader />
    <a-layout-content class="app-content">
      <router-view />
    </a-layout-content>
    <footer class="app-footer">
      TravelAI · 基于 LLM · Agent · RAG · LangGraph · LangChain
    </footer>
  </a-layout>
</template>

<script setup lang="ts">
import AppHeader from './components/common/AppHeader.vue'
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
  background: #f7f8fa;
}

.app-content {
  padding: 24px;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
}

.app-footer {
  text-align: center;
  padding: 24px;
  color: #86909c;
  font-size: 12px;
}
</style>
