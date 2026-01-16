import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useChat } from './useChat'
import { chatApi } from '../services/api'

vi.mock('../services/api')
const mockedApi = vi.mocked(chatApi, true)

describe('useChat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('initializes with welcome message', () => {
    const { result } = renderHook(() => useChat())

    expect(result.current.messages).toHaveLength(1)
    expect(result.current.messages[0].role).toBe('assistant')
    expect(result.current.messages[0].content).toContain('채용 조건')
    expect(result.current.isLoading).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('sends message and receives response', async () => {
    mockedApi.send.mockResolvedValueOnce({
      success: true,
      response: '검색 결과입니다',
      jobs: [
        {
          id: 'job-1',
          company_name: '테스트 회사',
          title: '프론트엔드 개발자',
          location: '서울 강남구',
          salary: '5000만원',
          experience: '3년 이상',
          employment_type: '정규직',
          deadline: '2026-02-01',
          url: 'https://example.com/job/1'
        }
      ],
      pagination: {
        total_count: 100,
        displayed: 1,
        has_more: true,
        remaining: 99
      },
      conversation_id: 'conv-123',
      search_params: {
        job_keywords: ['프론트엔드']
      }
    })

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('프론트엔드 개발자 채용')
    })

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(3) // welcome + user + assistant
    })

    expect(result.current.messages[1].role).toBe('user')
    expect(result.current.messages[1].content).toBe('프론트엔드 개발자 채용')
    expect(result.current.messages[2].role).toBe('assistant')
    expect(result.current.messages[2].jobs).toHaveLength(1)
    expect(result.current.isLoading).toBe(false)
  })

  it('handles API error gracefully', async () => {
    mockedApi.send.mockRejectedValueOnce(new Error('네트워크 오류'))

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('테스트 메시지')
    })

    await waitFor(() => {
      expect(result.current.error).toBe('네트워크 오류')
    })

    // 에러 응답 메시지가 추가됨
    expect(result.current.messages).toHaveLength(3)
    expect(result.current.messages[2].content).toContain('문제가 발생')
  })

  it('loads more jobs', async () => {
    // 초기 검색
    mockedApi.send.mockResolvedValueOnce({
      success: true,
      response: '검색 결과',
      jobs: [{ id: 'job-1', company_name: 'A', title: 'Dev', location: '서울', salary: '', experience: '', employment_type: '', deadline: '', url: '' }],
      pagination: { total_count: 100, displayed: 1, has_more: true, remaining: 99 },
      conversation_id: 'conv-123',
      search_params: {}
    })

    // 더보기
    mockedApi.loadMore.mockResolvedValueOnce({
      success: true,
      response: '',
      jobs: [{ id: 'job-2', company_name: 'B', title: 'Dev2', location: '서울', salary: '', experience: '', employment_type: '', deadline: '', url: '' }],
      pagination: { total_count: 100, displayed: 2, has_more: true, remaining: 98 },
      has_more: true
    })

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('개발자')
    })

    await act(async () => {
      await result.current.loadMoreJobs()
    })

    await waitFor(() => {
      const lastAssistantMsg = result.current.messages.find(
        (m, i) => m.role === 'assistant' && i > 0
      )
      expect(lastAssistantMsg?.jobs).toHaveLength(2)
    })
  })

  it('resets chat to initial state', async () => {
    mockedApi.send.mockResolvedValueOnce({
      success: true,
      response: '결과',
      jobs: [],
      pagination: { total_count: 0, displayed: 0, has_more: false, remaining: 0 },
      conversation_id: 'conv-123',
      search_params: {}
    })

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('테스트')
    })

    expect(result.current.messages.length).toBeGreaterThan(1)

    act(() => {
      result.current.resetChat()
    })

    expect(result.current.messages).toHaveLength(1)
    expect(result.current.error).toBeNull()
  })

  it('clears error', async () => {
    mockedApi.send.mockRejectedValueOnce(new Error('에러'))

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('테스트')
    })

    await waitFor(() => {
      expect(result.current.error).toBe('에러')
    })

    act(() => {
      result.current.clearError()
    })

    expect(result.current.error).toBeNull()
  })
})
