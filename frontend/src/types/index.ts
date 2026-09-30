/**
 * 全局 TypeScript 类型
 */

export interface WeatherForecast {
  date: string
  weekday: string
  weather: string
  icon: string
  /** 上游可能不提供温度，故允许为空 */
  temp_high: number | null
  temp_low: number | null
  wind?: string
  pm25?: number | null
}

export interface WeatherInfo {
  city: string
  forecasts: WeatherForecast[]
  tips: string
  /** 数据来源与发布时间，由高德地图返回，可能缺省 */
  source?: string
  report_time?: string
}

export interface ItinerarySpot {
  id: string
  name: string
  category?: string
  start_time?: string
  end_time?: string
  duration_minutes?: number
  estimated_cost?: number
  transport_to_next?: string
  notes?: string
}

export interface ItineraryDay {
  id: string
  day_number: number
  date: string
  theme?: string
  summary?: string
  weather_info?: Partial<WeatherForecast>
  spots: ItinerarySpot[]
}

export interface DraftItinerary {
  content: string
  spots_used: string[]
}

/** 一次线上工具调用记录 */
export interface ToolCallInfo {
  name: string
  args: Record<string, any>
}

export interface ChatMessageItem {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  weather_info?: WeatherInfo
  suggested_actions?: string[]
  tool_calls?: ToolCallInfo[]
  metadata?: Record<string, any>
}

export interface MapPoint {
  name: string
  lng: number
  lat: number
  order?: number
}

/** 高德地图 POI（酒店 / 景点），仅用于查询展示，不支持在线下单 */
export interface PoiInfo {
  id: string
  name: string
  category?: string
  address?: string
  city?: string
  district?: string
  tel?: string
  lng?: string | null
  lat?: string | null
  location?: string
  rating?: number | null
  cost?: number | null
  open_time?: string
  photos?: string[]
}
