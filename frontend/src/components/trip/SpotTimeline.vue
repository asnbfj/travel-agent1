<template>
  <a-timeline class="spot-timeline">
    <a-timeline-item
      v-for="(spot, index) in spots"
      :key="spot.id || index"
      :color="colorFor(index)"
    >
      <div class="spot-item">
        <div class="spot-time">
          {{ spot.start_time || '--:--' }} - {{ spot.end_time || '--:--' }}
        </div>
        <div class="spot-info">
          <div class="spot-name">{{ spot.name }}</div>
          <div class="spot-meta">
            <span v-if="spot.category">{{ spot.category }}</span>
            <span>游览约 {{ spot.duration_minutes || 120 }} 分钟</span>
            <span>¥{{ spot.estimated_cost || 0 }}</span>
          </div>
          <div v-if="spot.notes" class="spot-notes">{{ spot.notes }}</div>
        </div>
        <div v-if="spot.transport_to_next" class="transport-info">
          <icon-car /> {{ spot.transport_to_next }}
        </div>
      </div>
    </a-timeline-item>
  </a-timeline>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'
import type { ItinerarySpot } from '../../types'

defineProps({
  spots: {
    type: Array as PropType<ItinerarySpot[]>,
    default: () => [],
  },
})

const colors = ['blue', 'green', 'orange', 'purple', 'cyan']
function colorFor(index: number) {
  return colors[index % colors.length]
}
</script>

<style scoped>
.spot-item {
  padding: 8px 0;
}

.spot-time {
  font-weight: 600;
  color: #165dff;
  margin-bottom: 4px;
}

.spot-name {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}

.spot-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #86909c;
}

.spot-notes {
  margin-top: 4px;
  font-size: 13px;
  color: #4a5a6a;
}

.transport-info {
  margin-top: 8px;
  padding: 8px;
  background: #f2f3f5;
  border-radius: 8px;
  font-size: 12px;
  color: #86909c;
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
