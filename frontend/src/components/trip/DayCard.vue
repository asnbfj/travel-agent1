<template>
  <a-card class="day-card">
    <template #title>
      <div class="day-header">
        <div class="day-number">Day {{ day.day_number }}</div>
        <div class="day-date">{{ formatDate(day.date) }} · {{ day.theme }}</div>
      </div>
    </template>

    <div v-if="day.weather_info" class="day-weather">
      <span>{{ day.weather_info.icon }} {{ day.weather_info.weather }}</span>
      <span>{{ formatTemp(day.weather_info.temp_low) }}°C ~ {{ formatTemp(day.weather_info.temp_high) }}°C</span>
    </div>

    <SpotTimeline :spots="day.spots" />

    <div v-if="day.summary" class="day-summary">
      <strong>今日总结：</strong> {{ day.summary }}
    </div>
  </a-card>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'
import SpotTimeline from './SpotTimeline.vue'
import type { ItineraryDay } from '../../types'

defineProps({
  day: {
    type: Object as PropType<ItineraryDay>,
    required: true,
  },
})

function formatTemp(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value
}

function formatDate(dateStr: string) {
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return dateStr
  return date.toLocaleDateString('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  })
}
</script>

<style scoped>
.day-card {
  margin-bottom: 16px;
}

.day-header {
  display: flex;
  align-items: center;
  gap: 16px;
}

.day-number {
  background: #165dff;
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-weight: 600;
}

.day-weather {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  color: #4a5a6a;
}

.day-summary {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed #e5e6eb;
  font-size: 14px;
  color: #4a5a6a;
}
</style>
