import { useState, useCallback, useRef } from 'react'
import { Message, Job, PaginationInfo } from '../types'
import { chatApi, UserLocation } from '../services/api'

// V6: 검색 파라미터 (Simple Agentic)
interface SearchParams {
  job_keywords?: string[]
  salary_min?: number
  commute_origin?: string
  commute_max_minutes?: number
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
  pagination: PaginationInfo | null
  allJobs: Job[]
  searchParams?: SearchParams
}

// V6: 위치 정보 포함 옵션
interface UseChatOptions {
  userLocation?: UserLocation | null
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

  // V6: 위치 정보 포함하여 전송
  const sendMessage = useCallback(async (content: string, locationOverride?: UserLocation | null) => {
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

    // 위치 정보: override가 있으면 사용, 없으면 options에서 가져옴
    const userLocation = locationOverride !== undefined ? locationOverride : options.userLocation

    try {
      const response = await chatApi.send({
        message: content,
        conversationId,
        userLocation
      })

      // V6: 검색 파라미터 저장
      const searchParams: SearchParams = {
        job_keywords: response.search_params?.job_keywords as string[],
        salary_min: response.search_params?.salary_min as number,
        commute_origin: response.search_params?.commute_origin as string,
        commute_max_minutes: response.search_params?.commute_max_minutes as number
      }
      setLastSearchParams(searchParams)

      // 검색 컨텍스트 저장
      searchContextRef.current = {
        message: content,
        pagination: response.pagination,
        allJobs: response.jobs,
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
  }, [conversationId, options.userLocation])

  // V6: 더보기 (캐시 기반, AI 호출 없음)
  const loadMoreJobs = useCallback(async () => {
    const context = searchContextRef.current
    if (!context || !context.pagination?.has_more || !conversationId) return

    setIsLoadingMore(true)

    try {
      // V6: 단순히 conversation_id만 전달
      const response = await chatApi.loadMore({
        conversationId
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
              pagination: response.pagination ?? undefined
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
