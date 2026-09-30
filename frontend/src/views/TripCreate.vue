<template>
  <div class="create-page">
    <header class="page-head">
      <h1>新建行程</h1>
      <p class="lede">
        先记下时间和预算，行程内容之后可以随时补。想让 AI 直接出方案，去「智能规划」说一句更方便。
      </p>
    </header>

    <section class="plot">
      <div class="plot-label tick-cross">
        <span class="plot-label-name">行程基本信息</span>
        <span>带 * 的为必填</span>
      </div>

      <div class="plot-body">
        <a-form :model="form" layout="vertical" @submit-success="handleSubmit">
          <a-grid :cols="24" :col-gap="16">
            <a-grid-item :span="24">
              <a-form-item
                field="title"
                label="行程标题"
                :rules="[{ required: true, message: '请输入标题' }]"
              >
                <a-input v-model="form.title" placeholder="例如：东京赏樱 5 日" />
              </a-form-item>
            </a-grid-item>

            <a-grid-item :span="24">
              <a-form-item
                field="destination"
                label="目的地"
                :rules="[{ required: true, message: '请输入目的地' }]"
              >
                <a-input v-model="form.destination" placeholder="例如：日本东京" />
              </a-form-item>
            </a-grid-item>

            <a-grid-item :span="24">
              <a-form-item
                field="dates"
                label="出行日期"
                :rules="[{ required: true, message: '请选择日期' }]"
              >
                <a-range-picker v-model="dateRange" style="width: 100%" />
              </a-form-item>
            </a-grid-item>

            <a-grid-item :span="12">
              <a-form-item field="budget" label="预算（元）">
                <a-input-number
                  v-model="form.budget"
                  :min="0"
                  :step="1000"
                  style="width: 100%"
                />
              </a-form-item>
            </a-grid-item>

            <a-grid-item :span="12">
              <a-form-item field="travelers" label="出行人数">
                <a-input-number
                  v-model="form.travelers"
                  :min="1"
                  :max="30"
                  style="width: 100%"
                />
              </a-form-item>
            </a-grid-item>

            <a-grid-item :span="24">
              <a-form-item field="travel_style" label="旅行风格">
                <a-select v-model="form.travel_style" placeholder="请选择旅行风格">
                  <a-option v-for="s in styles" :key="s.value" :value="s.value">
                    {{ s.label }}
                  </a-option>
                </a-select>
              </a-form-item>
            </a-grid-item>

            <a-grid-item :span="24">
              <a-form-item field="notes" label="补充需求">
                <a-textarea
                  v-model="form.notes"
                  placeholder="例如：想看樱花、喜欢小店和市集、每天别排超过三个景点"
                  :auto-size="{ minRows: 3, maxRows: 6 }"
                />
              </a-form-item>
            </a-grid-item>
          </a-grid>

          <div class="form-actions">
            <a-button @click="fillAiPrompt" :loading="aiLoading">
              <template #icon><icon-robot /></template>
              AI 帮我填写
            </a-button>
            <a-button type="primary" html-type="submit" :loading="submitting">
              <template #icon><icon-save /></template>
              创建行程
            </a-button>
          </div>
        </a-form>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { useTripStore } from '../stores/trip'
import { agentApi } from '../api/agent'

const router = useRouter()
const tripStore = useTripStore()

const submitting = ref(false)
const aiLoading = ref(false)
const dateRange = ref<string[]>([])

const styles = [
  { label: '休闲度假', value: 'relaxed' },
  { label: '探险挑战', value: 'adventurous' },
  { label: '文化探索', value: 'cultural' },
  { label: '亲子游', value: 'family' },
  { label: '蜜月 / 情侣', value: 'romantic' },
  { label: '商务旅行', value: 'business' },
  { label: '美食之旅', value: 'foodie' },
  { label: '摄影采风', value: 'photography' },
]

const form = reactive({
  title: '',
  destination: '',
  budget: 5000,
  travelers: 2,
  travel_style: 'relaxed',
  notes: '',
})

async function handleSubmit() {
  if (!dateRange.value || dateRange.value.length !== 2) {
    Message.warning('请选择出行日期')
    return
  }
  submitting.value = true
  try {
    const trip = await tripStore.createTrip({
      title: form.title,
      destination: form.destination,
      start_date: dateRange.value[0],
      end_date: dateRange.value[1],
      budget: form.budget,
      travelers: form.travelers,
      requirements: {
        travel_style: form.travel_style,
        notes: form.notes,
      },
    })
    Message.success('行程创建成功')
    router.push(`/trip/${trip.id}`)
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '创建失败，请先登录')
  } finally {
    submitting.value = false
  }
}

async function fillAiPrompt() {
  const text = [form.destination, form.notes].filter(Boolean).join(' ')
  if (!text) {
    Message.warning('请先填写目的地或补充需求')
    return
  }
  aiLoading.value = true
  try {
    const res = await agentApi.chat({
      message: `我想去${text}，帮我规划行程`,
    })
    if (!form.title) {
      form.title = text.slice(0, 20) + ' 之旅'
    }
    Message.success('已根据 AI 建议填写表单')
    console.info('AI 建议：', res.message)
  } catch {
    Message.error('AI 服务暂时不可用，请手动填写')
  } finally {
    aiLoading.value = false
  }
}
</script>

<style scoped>
.create-page {
  max-width: 720px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
}
</style>
