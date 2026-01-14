import { useRef, useEffect, useMemo } from 'react'
import { InputBox } from './InputBox'
import { WelcomeScreen } from './WelcomeScreen'
import { SearchSummary } from './SearchSummary'
import { JobCardList } from './JobCardList'
import { JobCardSkeletonList } from './JobCardSkeleton'
import { useChat } from '../hooks/useChat'
import { useGeolocation } from '../hooks/useGeolocation'

// V6: 위치 기반 통근시간 계산 복구
export function ChatWindow() {
  // 위치 정보 가져오기
  const {
    coordinates,
    address,
    loading: locationLoading,
    error: locationError,
    permission
  } = useGeolocation()

  // 위치 정보를 useChat에 전달
  const userLocation = useMemo(() => {
    if (coordinates) {
      return {
        latitude: coordinates.latitude,
        longitude: coordinates.longitude,
        address: address
      }
    }
    return null
  }, [coordinates, address])

  const {
    messages,
    isLoading,
    isLoadingMore,
    error,
    sendMessage,
    loadMoreJobs,
    clearError,
    resetChat,
    lastSearchParams
  } = useChat({ userLocation })
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 대화 메시지만 (welcome 제외)
  const conversationMessages = useMemo(() => {
    return messages.filter(m => m.id !== 'welcome')
  }, [messages])

  // 새 메시지 시 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // V6: 간소화된 메시지 전송
  const handleSend = (content: string) => {
    sendMessage(content)
  }

  // 첫 진입 화면 (메시지 없음)
  if (!isLoading && messages.length <= 1) {
    return (
      <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-primary-100">
        <WelcomeScreen onSubmit={handleSend} disabled={isLoading} />

        {/* 위치 정보 상태 표시 */}
        <div className="border-t border-primary-50 px-4 py-2 bg-primary-50/50">
          <div className="flex justify-center items-center text-xs text-gray-500">
            {locationLoading ? (
              <span className="flex items-center gap-2">
                <span className="animate-pulse">📍</span>
                위치 정보를 가져오는 중...
              </span>
            ) : permission === 'denied' ? (
              <span className="flex items-center gap-2 text-amber-600">
                <span>⚠️</span>
                위치 권한이 거부됨 - 메시지에 위치를 직접 입력해주세요
              </span>
            ) : address ? (
              <span className="flex items-center gap-2 text-green-600">
                <span>📍</span>
                현재 위치: {address}
              </span>
            ) : coordinates ? (
              <span className="flex items-center gap-2 text-green-600">
                <span>📍</span>
                위치 확인됨
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <span>🚇</span>
                출발 위치를 메시지에 포함하면 통근시간을 계산해드려요
              </span>
            )}
          </div>
        </div>
      </div>
    )
  }

  // V6: 간소화된 헤더
  const Header = () => (
    <div className="bg-gradient-to-r from-primary-500 to-primary-600 text-white px-4 py-3 flex-shrink-0">
      <div className="flex justify-between items-center">
        <button
          onClick={resetChat}
          className="flex items-center gap-2 text-white/80 hover:text-white transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          <span className="text-sm font-medium">새 검색</span>
        </button>

        <h2 className="font-bold" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>JOBBOT</h2>

        {/* 위치 정보 표시 */}
        <div className="text-right">
          {address ? (
            <span className="text-xs text-primary-100 flex items-center gap-1">
              <span>📍</span>
              {address}
            </span>
          ) : (
            <span className="text-xs text-primary-100 flex items-center gap-1">
              <span>🚇</span>
              지하철 통근 계산
            </span>
          )}
        </div>
      </div>
    </div>
  )

  // 에러 배너
  const ErrorBanner = () => error ? (
    <div className="bg-red-50 border-b border-red-200 px-4 py-3 flex justify-between items-center flex-shrink-0">
      <div className="flex items-center gap-2">
        <span className="text-red-500">⚠️</span>
        <span className="text-red-700 text-sm">{error}</span>
      </div>
      <button
        onClick={clearError}
        className="text-red-400 hover:text-red-600 p-1"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  ) : null

  // 통합 채팅 레이아웃
  return (
    <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-gray-200">
      <div className="h-[calc(100vh-240px)] min-h-[500px] flex flex-col">
        <Header />
        <ErrorBanner />

        {/* 채팅 영역 - 모든 메시지와 결과가 자연스럽게 흐름 */}
        <div className="flex-1 overflow-y-auto p-4 bg-gray-50 scrollbar-thin">
          <div className="space-y-4">
            {conversationMessages.map((message, idx) => (
              <div key={message.id}>
                {/* 메시지 버블 */}
                <div className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {message.role === 'assistant' && (
                    <div className="w-8 h-8 rounded-full bg-primary-500 flex items-center justify-center text-white text-sm font-medium mr-2 flex-shrink-0">
                      AI
                    </div>
                  )}
                  <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                    message.role === 'user'
                      ? 'bg-primary-500 text-white'
                      : 'bg-white text-gray-900 border border-gray-200 shadow-sm'
                  }`}>
                    <p className="text-base whitespace-pre-wrap">{message.content}</p>
                  </div>
                </div>

                {/* AI 응답에 채용공고가 있으면 바로 아래에 표시 */}
                {message.role === 'assistant' && message.jobs && message.jobs.length > 0 && (
                  <div className="mt-4 ml-10">
                    {/* 검색 조건 요약 */}
                    {lastSearchParams && idx === conversationMessages.length - 1 && (
                      <SearchSummary
                        searchParams={lastSearchParams}
                        totalCount={message.pagination?.total_count || message.jobs.length}
                      />
                    )}

                    {/* 채용공고 목록 */}
                    <JobCardList
                      jobs={message.jobs}
                      pagination={message.pagination}
                      onLoadMore={idx === conversationMessages.length - 1 ? loadMoreJobs : undefined}
                      isLoadingMore={isLoadingMore}
                    />
                  </div>
                )}
              </div>
            ))}

            {/* 로딩 인디케이터 */}
            {isLoading && (
              <div className="flex items-start gap-2">
                <div className="w-8 h-8 rounded-full bg-primary-500 flex items-center justify-center text-white text-sm font-medium flex-shrink-0">
                  AI
                </div>
                <div className="flex-1">
                  <div className="bg-white rounded-2xl px-4 py-3 border border-gray-200 shadow-sm inline-block">
                    <div className="flex space-x-1.5">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse-soft" />
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse-soft" style={{ animationDelay: '200ms' }} />
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse-soft" style={{ animationDelay: '400ms' }} />
                    </div>
                  </div>
                  {/* 로딩 중 스켈레톤 */}
                  <div className="mt-4">
                    <JobCardSkeletonList count={3} />
                  </div>
                </div>
              </div>
            )}
          </div>
          <div ref={messagesEndRef} />
        </div>

        {/* 입력 영역 */}
        <div className="border-t border-gray-200 p-4 bg-white flex-shrink-0">
          <InputBox onSend={handleSend} disabled={isLoading} />
        </div>
      </div>
    </div>
  )
}
