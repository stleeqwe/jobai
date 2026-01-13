import { useRef, useEffect } from 'react'
import { MessageList } from './MessageList'
import { InputBox } from './InputBox'
import { useChat } from '../hooks/useChat'
import { useGeolocation } from '../hooks/useGeolocation'

export function ChatWindow() {
  const geolocation = useGeolocation()
  const { messages, isLoading, isLoadingMore, error, sendMessage, loadMoreJobs, clearError } = useChat({
    userCoordinates: geolocation.coordinates
  })
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 새 메시지 시 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 메시지 전송 핸들러 (좌표 포함)
  const handleSend = (content: string) => {
    sendMessage(content, geolocation.coordinates)
  }

  return (
    <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-gray-200">
      <div className="h-[600px] flex flex-col">
        {/* 헤더 */}
        <div className="bg-gradient-to-r from-primary-500 to-primary-600 text-white px-4 py-3">
          <div className="flex justify-between items-start">
            <div>
              <h2 className="font-semibold">채용공고 검색</h2>
              <p className="text-sm text-primary-100">원하는 조건을 자연어로 말씀해주세요</p>
            </div>
            {/* 위치 상태 표시 */}
            <div className="text-right">
              {geolocation.loading ? (
                <span className="text-xs text-primary-200">위치 확인 중...</span>
              ) : geolocation.hasLocation ? (
                <div className="flex items-center gap-1 text-xs">
                  <span className="text-green-300">📍</span>
                  <span className="text-primary-100">
                    {geolocation.address || '내 위치 사용 중'}
                  </span>
                </div>
              ) : geolocation.permission === 'denied' ? (
                <button
                  onClick={geolocation.refreshLocation}
                  className="text-xs text-primary-200 hover:text-white"
                >
                  📍 위치 권한 필요
                </button>
              ) : (
                <button
                  onClick={geolocation.refreshLocation}
                  className="text-xs text-primary-200 hover:text-white"
                >
                  📍 위치 설정
                </button>
              )}
            </div>
          </div>
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
          <MessageList
            messages={messages}
            isLoading={isLoading}
            onLoadMore={loadMoreJobs}
            isLoadingMore={isLoadingMore}
          />
          <div ref={messagesEndRef} />
        </div>

        {/* 입력 영역 */}
        <div className="border-t border-gray-200 p-4 bg-white">
          <InputBox onSend={handleSend} disabled={isLoading} />
        </div>
      </div>
    </div>
  )
}
