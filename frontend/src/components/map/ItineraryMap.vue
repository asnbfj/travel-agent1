<template>
  <div ref="chartRef" class="itinerary-map"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { MapPoint } from '../../types'

const props = defineProps<{
  points: MapPoint[]
}>()

const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

function render() {
  if (!chart) return
  const points = (props.points || []).filter(
    (p) => typeof p.lng === 'number' && typeof p.lat === 'number',
  )

  const lineData = points.map((p) => [p.lng, p.lat])

  chart.setOption(
    {
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          if (params.seriesType === 'scatter') {
            return `${params.data[2]}<br/>经度 ${params.data[0]} / 纬度 ${params.data[1]}`
          }
          return ''
        },
      },
      grid: { left: 40, right: 24, top: 24, bottom: 32 },
      xAxis: {
        type: 'value',
        name: '经度',
        scale: true,
        axisLabel: { fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        name: '纬度',
        scale: true,
        axisLabel: { fontSize: 10 },
      },
      series: [
        {
          type: 'line',
          data: lineData,
          smooth: true,
          lineStyle: { color: '#165dff', width: 2 },
          showSymbol: false,
          z: 1,
        },
        {
          type: 'scatter',
          data: points.map((p, i) => [p.lng, p.lat, `${i + 1}. ${p.name}`]),
          symbolSize: 14,
          itemStyle: { color: '#165dff' },
          label: {
            show: true,
            formatter: (params: any) => `${params.dataIndex + 1}`,
            color: '#fff',
            fontSize: 10,
          },
          z: 2,
        },
      ],
    },
    true,
  )
}

function resize() {
  chart?.resize()
}

onMounted(() => {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    render()
    window.addEventListener('resize', resize)
  }
})

watch(() => props.points, render, { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.itinerary-map {
  width: 100%;
  height: 400px;
}
</style>
