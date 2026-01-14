export interface Coordinates {
  latitude: number
  longitude: number
}

export interface Job {
  id: string
  company_name: string
  title: string
  location: string
  salary: string
  experience: string
  employment_type: string
  deadline: string
  url: string
  // V6: 지하철 기반 통근시간 정보
  commute_minutes?: number
  commute_text?: string
}

export interface PaginationInfo {
  total_count: number
  displayed: number
  has_more: boolean
  remaining: number
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  jobs: Job[]
  pagination?: PaginationInfo
  timestamp?: Date
}

export interface ChatResponse {
  success: boolean
  response: string
  jobs: Job[]
  pagination: PaginationInfo
  search_params: Record<string, unknown>  // V6: job_keywords, salary_min, commute_origin 등
  conversation_id: string
  error?: string
}

export interface LoadMoreResponse {
  success: boolean
  response: string
  jobs: Job[]
  pagination: PaginationInfo | null
  has_more: boolean
}

export interface ChatState {
  messages: Message[]
  isLoading: boolean
  conversationId: string | null
  error: string | null
}
