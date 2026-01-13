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
  // V3: Maps API 이동시간 정보
  travel_time_minutes?: number
  travel_time_text?: string
}

export interface PaginationInfo {
  page: number
  page_size: number
  total_count: number
  total_pages: number
  has_next: boolean
  has_prev: boolean
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
  search_params: Record<string, unknown>  // V3: job_type, salary_min, user_location, max_commute_minutes
  conversation_id: string
  error?: string
}

export interface LoadMoreResponse {
  success: boolean
  jobs: Job[]
  pagination: PaginationInfo
  search_params: Record<string, unknown>
}

export interface ChatState {
  messages: Message[]
  isLoading: boolean
  conversationId: string | null
  error: string | null
}
