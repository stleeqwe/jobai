import { useRef, useEffect } from 'react'
import { MessageList } from './MessageList'
import { InputBox } from './InputBox'
import { useChat } from '../hooks/useChat'

export function ChatWindow() {
  const { messages, isLoading, error, sendMessage, clearError } = useChat()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 새 메시지 시 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-gray-200">
      <div className="h-[600px] flex flex-col">
        {/* 헤더 */}
        <div className="bg-gradient-to-r from-primary-500 to-primary-600 text-white px-4 py-3">
          <h2 className="font-semibold">채용공고 검색</h2>
          <p className="text-sm text-primary-100">원하는 조건을 자연어로 말씀해주세요</p>
        </div>

        {/* 에러 배너 */}
        {error && (
          <div className="bg-red-50 border-b border-red-200 px-4 py-2 flex justify-between items-center">
            <span className="text-red-700 text-sm">{error}</span>
            <button
              onClick={clearError}
              className="text-red-500 hover:text-red-700 font-bold"
            >
              X
            </button>
          </div>
        )}

        {/* 메시지 영역 */}
        <div className="flex-1 overflow-y-auto p-4 scrollbar-thin bg-gray-50">
          <MessageList messages={messages} isLoading={isLoading} />
          <div ref={messagesEndRef} />
        </div>

        {/* 입력 영역 */}
        <div className="border-t border-gray-200 p-4 bg-white">
          <InputBox onSend={sendMessage} disabled={isLoading} />
        </div>
      </div>
    </div>
  )
}
