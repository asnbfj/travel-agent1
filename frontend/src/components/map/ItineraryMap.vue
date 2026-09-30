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

/** 图上的颜色与线宽统一从设计变量取，避免图表里出现另一套配色 */
function tokens() {
  const css = getComputedStyle(document.documentElement)
  const read = (name: string, fallback: string) =>
    css.getPropertyValue(name).trim() || fallback
  return {
    ink: read('--ink', '#0e1b22'),
    ink3: read('--ink-3', '#6b7e86'),
    rule: read('--rule', '#b9c6c6'),
    ruleStrong: read('--rule-strong', '#8fa1a1'),
    plot: read('--plot', '#f2f5f4'),
    magenta: read('--magenta', '#c0266b'),
  }
}

function render() {
  if (!chart) return
  const t = tokens()
  const points = (props.points || []).filter(
    (p) => typeof p.lng === 'number' && typeof p.lat === 'number',
  )

  chart.setOption(
    {
      animationDuration: 600,
      textStyle: { fontFamily: 'PingFang SC, Microsoft YaHei, sans-serif' },
      tooltip: {
        trigger: 'item',
        backgroundColor: t.plot,
        borderColor: t.ruleStrong,
        borderWidth: 1,
        padding: [8, 10],
        textStyle: { color: t.ink, fontSize: 12 },
        extraCssText: 'border-radius:2px;box-shadow:none;',
        formatter: (params: any) =>
          params.seriesType === 'scatter'
            ? `${params.data[2]}<br/>经度 ${params.data[0]} · 纬度 ${params.data[1]}`
            : '',
      },
      grid: { left: 52, right: 28, top: 22, bottom: 34 },
      xAxis: {
        type: 'value',
        name: '经度',
        nameTextStyle: { color: t.ink3, fontSize: 11, padding: [0, 0, 6, 0] },
        scale: true,
        axisLine: { lineStyle: { color: t.ruleStrong } },
        axisTick: { lineStyle: { color: t.rule } },
        axisLabel: { color: t.ink3, fontSize: 10 },
        splitLine: { lineStyle: { color: t.rule, opacity: 0.7 } },
      },
      yAxis: {
        type: 'value',
        name: '纬度',
        nameTextStyle: { color: t.ink3, fontSize: 11, padding: [0, 0, 6, 0] },
        scale: true,
        axisLine: { lineStyle: { color: t.ruleStrong } },
        axisTick: { lineStyle: { color: t.rule } },
        axisLabel: { color: t.ink3, fontSize: 10 },
        splitLine: { lineStyle: { color: t.rule, opacity: 0.7 } },
      },
      series: [
        {
          type: 'line',
          data: points.map((p) => [p.lng, p.lat]),
          // 直线段：航线是折线，不做平滑处理
          smooth: false,
          lineStyle: { color: t.magenta, width: 2 },
          itemStyle: { color: t.magenta },
          showSymbol: false,
          silent: true,
          z: 1,
        },
        {
          type: 'scatter',
          data: points.map((p, i) => [p.lng, p.lat, `${i + 1}. ${p.name}`]),
          symbolSize: 16,
          itemStyle: {
            color: t.plot,
            borderColor: t.ink,
            borderWidth: 1.4,
          },
          label: {
            show: true,
            formatter: (params: any) => `${params.dataIndex + 1}`,
            color: t.ink,
            fontSize: 10,
          },
          emphasis: {
            itemStyle: { borderColor: t.magenta, borderWidth: 2 },
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
