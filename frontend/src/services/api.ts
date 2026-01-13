import axios, { AxiosError } from 'axios'
import { ChatResponse, Coordinates } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json'
  },
  timeout: 60000  // 2-Stage 처리로 인해 타임아웃 증가
})

export interface ChatRequestParams {
  message: string
  conversationId: string | null
  page?: number
  pageSize?: number
  userCoordinates?: Coordinates | null  // 사용자 GPS 좌표
}

export const chatApi = {
  send: async (params: ChatRequestParams): Promise<ChatResponse> => {
    try {
      const response = await client.post<ChatResponse>('/chat', {
        message: params.message,
        conversation_id: params.conversationId,
        page: params.page || 1,
        page_size: params.pageSize || 20,
        user_lat: params.userCoordinates?.latitude,
        user_lng: params.userCoordinates?.longitude
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
