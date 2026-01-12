import { useState, useCallback } from 'react'
import { Message } from '../types'
import { chatApi } from '../services/api'

const INITIAL_MESSAGE: Message = {
  id: 'welcome',
  role: 'assistant',
  content: `안녕하세요! 원하시는 채용 조건을 자연어로 말씀해주세요.

예시:
- "강남역 근처 웹디자이너, 연봉 4천 이상"
- "판교 백엔드 개발자, 신입 환영"
- "마케터, 정규직, 서울"`,
  jobs: [],
  timestamp: new Date()
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([INITIAL_MESSAGE])
  const [isLoading, setIsLoading] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const sendMessage = useCallback(async (content: string) => {
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
      const response = await chatApi.send(content, conversationId)

      // AI 응답 추가
      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.response,
        jobs: response.jobs,
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
  }, [conversationId])

  const clearError = useCallback(() => {
    setError(null)
  }, [])

  const resetChat = useCallback(() => {
    setMessages([INITIAL_MESSAGE])
    setConversationId(null)
    setError(null)
  }, [])

  return {
    messages,
    isLoading,
    error,
    sendMessage,
    clearError,
    resetChat
  }
}
