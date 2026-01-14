import axios, { AxiosError } from 'axios'
import { ChatResponse, LoadMoreResponse } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json'
  },
  timeout: 60000  // Simple Agentic 처리 타임아웃
})

// 사용자 위치 정보
export interface UserLocation {
  latitude: number
  longitude: number
  address: string | null
}

// V6: 요청 파라미터 (위치 정보 포함)
export interface ChatRequestParams {
  message: string
  conversationId: string | null
  userLocation?: UserLocation | null
}

export interface LoadMoreParams {
  conversationId: string
}

export const chatApi = {
  // V6: 채팅 API (위치 정보 포함)
  send: async (params: ChatRequestParams): Promise<ChatResponse> => {
    try {
      const requestBody: Record<string, unknown> = {
        message: params.message,
        conversation_id: params.conversationId
      }

      // 위치 정보가 있으면 추가
      if (params.userLocation) {
        requestBody.user_location = {
          latitude: params.userLocation.latitude,
          longitude: params.userLocation.longitude,
          address: params.userLocation.address
        }
      }

      const response = await client.post<ChatResponse>('/chat', requestBody)
      return response.data
    } catch (error) {
      const axiosError = error as AxiosError<{ detail: string }>
      throw new Error(
        axiosError.response?.data?.detail ||
        '서버와 통신 중 오류가 발생했습니다.'
      )
    }
  },

  // V6: 캐시된 결과에서 추가 로드 (AI 호출 없음)
  loadMore: async (params: LoadMoreParams): Promise<LoadMoreResponse> => {
    try {
      const response = await client.post<LoadMoreResponse>('/chat/more', {
        conversation_id: params.conversationId
      })
      return response.data
    } catch (error) {
      const axiosError = error as AxiosError<{ detail: string }>
      throw new Error(
        axiosError.response?.data?.detail ||
        '추가 결과를 불러오는 중 오류가 발생했습니다.'
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
