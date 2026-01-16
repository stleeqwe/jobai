import { describe, it, expect, vi, beforeEach } from 'vitest'

// Hoist mock functions so they're available in vi.mock
const { mockPost, mockGet } = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockGet: vi.fn()
}))

vi.mock('axios', () => ({
  default: {
    create: () => ({
      post: mockPost,
      get: mockGet
    })
  }
}))

import { chatApi } from './api'

describe('chatApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('send', () => {
    it('sends message without location', async () => {
      const mockResponse = {
        data: {
          success: true,
          response: '검색 결과입니다',
          jobs: [],
          pagination: { total_count: 0, displayed: 0, has_more: false, remaining: 0 },
          conversation_id: 'conv-123',
          search_params: {}
        }
      }
      mockPost.mockResolvedValueOnce(mockResponse)

      const result = await chatApi.send({
        message: '개발자 채용',
        conversationId: null
      })

      expect(mockPost).toHaveBeenCalledWith('/chat', {
        message: '개발자 채용',
        conversation_id: null
      })
      expect(result.success).toBe(true)
      expect(result.conversation_id).toBe('conv-123')
    })

    it('sends message with location', async () => {
      const mockResponse = {
        data: {
          success: true,
          response: '통근시간 포함 검색',
          jobs: [],
          pagination: { total_count: 0, displayed: 0, has_more: false, remaining: 0 },
          conversation_id: 'conv-456',
          search_params: {}
        }
      }
      mockPost.mockResolvedValueOnce(mockResponse)

      const location = {
        latitude: 37.5665,
        longitude: 126.9780,
        address: '서울시청'
      }

      await chatApi.send({
        message: '개발자 채용',
        conversationId: null,
        userLocation: location
      })

      expect(mockPost).toHaveBeenCalledWith('/chat', {
        message: '개발자 채용',
        conversation_id: null,
        user_location: location
      })
    })

    it('throws error on API failure', async () => {
      mockPost.mockRejectedValueOnce({
        response: {
          data: { detail: '서버 오류' }
        }
      })

      await expect(chatApi.send({
        message: '테스트',
        conversationId: null
      })).rejects.toThrow('서버 오류')
    })

    it('throws default error when no detail', async () => {
      mockPost.mockRejectedValueOnce(new Error('network'))

      await expect(chatApi.send({
        message: '테스트',
        conversationId: null
      })).rejects.toThrow('서버와 통신 중 오류가 발생했습니다.')
    })
  })

  describe('loadMore', () => {
    it('loads more jobs', async () => {
      const mockResponse = {
        data: {
          success: true,
          response: '',
          jobs: [{ id: 'job-1', title: '개발자' }],
          pagination: { total_count: 100, displayed: 60, has_more: true, remaining: 40 },
          has_more: true
        }
      }
      mockPost.mockResolvedValueOnce(mockResponse)

      const result = await chatApi.loadMore({
        conversationId: 'conv-123'
      })

      expect(mockPost).toHaveBeenCalledWith('/chat/more', {
        conversation_id: 'conv-123'
      })
      expect(result.jobs).toHaveLength(1)
    })
  })

  describe('healthCheck', () => {
    it('returns true when healthy', async () => {
      mockGet.mockResolvedValueOnce({ data: { status: 'ok' } })

      const result = await chatApi.healthCheck()
      expect(result).toBe(true)
    })

    it('returns false when unhealthy', async () => {
      mockGet.mockRejectedValueOnce(new Error('Connection failed'))

      const result = await chatApi.healthCheck()
      expect(result).toBe(false)
    })
  })
})
