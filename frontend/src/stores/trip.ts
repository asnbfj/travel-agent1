import { defineStore } from 'pinia'
import { ref } from 'vue'
import { tripApi, type Trip, type TripCreatePayload, type TripFromPlanPayload } from '../api/trips'

export const useTripStore = defineStore('trip', () => {
  const trips = ref<Trip[]>([])
  const currentTrip = ref<Trip | null>(null)
  const loading = ref(false)

  async function fetchTrips() {
    loading.value = true
    try {
      trips.value = await tripApi.list()
    } finally {
      loading.value = false
    }
    return trips.value
  }

  async function createTrip(payload: TripCreatePayload) {
    const trip = await tripApi.create(payload)
    trips.value.unshift(trip)
    currentTrip.value = trip
    return trip
  }

  async function createFromPlan(payload: TripFromPlanPayload) {
    const trip = await tripApi.createFromPlan(payload)
    trips.value.unshift(trip)
    currentTrip.value = trip
    return trip
  }

  async function fetchTrip(tripId: string) {
    loading.value = true
    try {
      currentTrip.value = await tripApi.detail(tripId)
    } finally {
      loading.value = false
    }
    return currentTrip.value
  }

  async function updateTrip(tripId: string, payload: Partial<TripCreatePayload> & { status?: string }) {
    const trip = await tripApi.update(tripId, payload)
    currentTrip.value = trip
    const idx = trips.value.findIndex((t) => t.id === trip.id)
    if (idx !== -1) trips.value[idx] = trip
    return trip
  }

  async function removeTrip(tripId: string) {
    await tripApi.remove(tripId)
    trips.value = trips.value.filter((t) => t.id !== tripId)
    if (currentTrip.value?.id === tripId) currentTrip.value = null
  }

  function setCurrentTrip(trip: Trip | null) {
    currentTrip.value = trip
  }

  return {
    trips,
    currentTrip,
    loading,
    fetchTrips,
    createTrip,
    createFromPlan,
    fetchTrip,
    updateTrip,
    removeTrip,
    setCurrentTrip,
  }
})
