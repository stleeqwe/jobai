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
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  jobs: Job[]
  timestamp?: Date
}

export interface ChatResponse {
  success: boolean
  response: string
  jobs: Job[]
  total_count: number
  search_params: Record<string, unknown>
  conversation_id: string
  error?: string
}

export interface ChatState {
  messages: Message[]
  isLoading: boolean
  conversationId: string | null
  error: string | null
}
