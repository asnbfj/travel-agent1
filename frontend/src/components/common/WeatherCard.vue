<template>
  <div v-if="weather" class="weather-card">
    <div class="weather-header">
      <icon-environment />
      <span>{{ weather.city }} 天气预报</span>
    </div>
    <div class="weather-days">
      <div
        v-for="day in (weather.forecasts || []).slice(0, 5)"
        :key="day.date"
        class="weather-day"
      >
        <div class="day-name">{{ day.weekday }}</div>
        <div class="day-icon">{{ day.icon }}</div>
        <div class="day-weather">{{ day.weather }}</div>
        <div class="day-temp">{{ formatTemp(day.temp_low) }}° ~ {{ formatTemp(day.temp_high) }}°</div>
      </div>
    </div>
    <div v-if="weather.tips" class="weather-tips">💡 {{ weather.tips }}</div>
  </div>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'
import type { WeatherInfo } from '../../types'

defineProps({
  weather: {
    type: Object as PropType<WeatherInfo | undefined>,
    default: undefined,
  },
})

/** 上游可能不提供温度，避免渲染成 "null°" */
const formatTemp = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : value
</script>

<style scoped>
.weather-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 16px;
  border-radius: 12px;
  margin-bottom: 16px;
}

.weather-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-weight: 600;
}

.weather-days {
  display: flex;
  gap: 8px;
}

.weather-day {
  text-align: center;
  flex: 1;
}

.day-icon {
  font-size: 24px;
  margin: 4px 0;
}

.day-weather {
  font-size: 12px;
  opacity: 0.9;
}

.day-temp {
  font-size: 11px;
  opacity: 0.8;
}

.weather-tips {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.2);
  font-size: 13px;
}
</style>
