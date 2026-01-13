import { useState, useCallback, useRef } from 'react'
import { Message, Job, PaginationInfo, Coordinates } from '../types'
import { chatApi } from '../services/api'

interface SearchParams {
  job_type?: string
  salary_min?: number
  location_query?: string
  max_commute_minutes?: number
}

const INITIAL_MESSAGE: Message = {
  id: 'welcome',
  role: 'assistant',
  content: '원하시는 채용 조건을 자연어로 말씀해주세요.',
  jobs: [],
  timestamp: new Date()
}

interface SearchContext {
  message: string
  pagination: PaginationInfo
  allJobs: Job[]
  userCoordinates?: Coordinates | null
  searchParams?: SearchParams
}

interface UseChatOptions {
  userCoordinates?: Coordinates | null
}

export function useChat(options: UseChatOptions = {}) {
  const [messages, setMessages] = useState<Message[]>([INITIAL_MESSAGE])
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastSearchParams, setLastSearchParams] = useState<SearchParams | null>(null)

  // 현재 검색 컨텍스트 저장 (더 보기용)
  const searchContextRef = useRef<SearchContext | null>(null)

  const sendMessage = useCallback(async (content: string, coordinates?: Coordinates | null) => {
    // 좌표는 파라미터로 받은 것 우선, 없으면 옵션에서
    const userCoordinates = coordinates ?? options.userCoordinates
    // 사용자 메시지 추가
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      jobs: [],
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    setIsLoading(true)
    setError(null)

    try {
      const response = await chatApi.send({
        message: content,
        conversationId,
        page: 1,
        pageSize: 20,
        userCoordinates
      })

      // 검색 파라미터 저장
      const searchParams: SearchParams = {
        job_type: response.search_params?.job_type as string,
        salary_min: response.search_params?.salary_min as number,
        location_query: response.search_params?.location_query as string,
        max_commute_minutes: response.search_params?.max_commute_minutes as number
      }
      setLastSearchParams(searchParams)

      // 검색 컨텍스트 저장
      searchContextRef.current = {
        message: content,
        pagination: response.pagination,
        allJobs: response.jobs,
        userCoordinates,
        searchParams
      }

      // AI 응답 추가
      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.response,
        jobs: response.jobs,
        pagination: response.pagination,
        timestamp: new Date()
      }

      setMessages(prev => [...prev, assistantMessage])
      setConversationId(response.conversation_id)

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.'
      setError(errorMessage)

      // 에러 응답 메시지
      const errorResponse: Message = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: '죄송합니다. 요청 처리 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.',
        jobs: [],
        timestamp: new Date()
      }
      setMessages(prev => [...prev, errorResponse])
    } finally {
      setIsLoading(false)
    }
  }, [conversationId, options.userCoordinates])

  const loadMoreJobs = useCallback(async () => {
    const context = searchContextRef.current
    if (!context || !context.pagination.has_next || !conversationId) return

    setIsLoadingMore(true)

    try {
      const nextPage = context.pagination.page + 1
      // 캐시 기반 API 사용 (AI 재호출 없음)
      const response = await chatApi.loadMore({
        conversationId,
        page: nextPage,
        pageSize: 20
      })

      // 새 공고들을 기존에 추가
      const newAllJobs = [...context.allJobs, ...response.jobs]

      // 컨텍스트 업데이트
      searchContextRef.current = {
        ...context,
        pagination: response.pagination,
        allJobs: newAllJobs
      }

      // 마지막 AI 메시지 업데이트
      setMessages(prev => {
        const newMessages = [...prev]
        // 마지막 assistant 메시지 찾기
        for (let i = newMessages.length - 1; i >= 0; i--) {
          if (newMessages[i].role === 'assistant' && newMessages[i].jobs.length > 0) {
            newMessages[i] = {
              ...newMessages[i],
              jobs: newAllJobs,
              pagination: response.pagination
            }
            break
          }
        }
        return newMessages
      })

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '더 불러오기 실패'
      setError(errorMessage)
    } finally {
      setIsLoadingMore(false)
    }
  }, [conversationId])

  const clearError = useCallback(() => {
    setError(null)
  }, [])

  const resetChat = useCallback(() => {
    setMessages([INITIAL_MESSAGE])
    setConversationId(null)
    setError(null)
    setLastSearchParams(null)
    searchContextRef.current = null
  }, [])

  return {
    messages,
    isLoading,
    isLoadingMore,
    error,
    sendMessage,
    loadMoreJobs,
    clearError,
    resetChat,
    lastSearchParams
  }
}
