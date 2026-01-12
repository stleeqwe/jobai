import axios, { AxiosError } from 'axios'
import { ChatResponse } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json'
  },
  timeout: 30000
})

export const chatApi = {
  send: async (message: string, conversationId: string | null): Promise<ChatResponse> => {
    try {
      const response = await client.post<ChatResponse>('/chat', {
        message,
        conversation_id: conversationId
      })
      return response.data
    } catch (error) {
      const axiosError = error as AxiosError<{ detail: string }>
      throw new Error(
        axiosError.response?.data?.detail ||
        '서버와 통신 중 오류가 발생했습니다.'
      )
    }
  },

  healthCheck: async (): Promise<boolean> => {
    try {
      await client.get('/health')
      return true
    } catch {
      return false
    }
  }
}
