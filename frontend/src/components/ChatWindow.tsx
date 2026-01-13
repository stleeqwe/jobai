import { useRef, useEffect, useMemo } from 'react'
import { InputBox } from './InputBox'
import { WelcomeScreen } from './WelcomeScreen'
import { SearchSummary } from './SearchSummary'
import { JobCardList } from './JobCardList'
import { JobCardSkeletonList } from './JobCardSkeleton'
import { useChat } from '../hooks/useChat'
import { useGeolocation } from '../hooks/useGeolocation'

export function ChatWindow() {
  const geolocation = useGeolocation()
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
  } = useChat({
    userCoordinates: geolocation.coordinates
  })
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 검색 결과가 있는지 확인
  const hasResults = useMemo(() => {
    return messages.some(m => m.role === 'assistant' && m.jobs.length > 0)
  }, [messages])

  // 마지막 검색 결과 메시지
  const lastResultMessage = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant' && messages[i].jobs.length > 0) {
        return messages[i]
      }
    }
    return null
  }, [messages])

  // 대화 메시지만 (welcome 제외)
  const conversationMessages = useMemo(() => {
    return messages.filter(m => m.id !== 'welcome')
  }, [messages])

  // 새 메시지 시 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 메시지 전송 핸들러 (좌표 포함)
  const handleSend = (content: string) => {
    sendMessage(content, geolocation.coordinates)
  }

  // 첫 진입 화면 (메시지 없음)
  if (!isLoading && messages.length <= 1) {
    return (
      <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-primary-100">
        <WelcomeScreen onSubmit={handleSend} disabled={isLoading} />

        {/* 위치 상태 표시 (하단) */}
        <div className="border-t border-primary-50 px-4 py-2 bg-primary-50/50">
          <div className="flex justify-center items-center text-xs text-gray-500">
            {geolocation.loading ? (
              <span className="flex items-center gap-2">
                <span className="animate-pulse">📍</span>
                위치 확인 중...
              </span>
            ) : geolocation.hasLocation ? (
              <span className="flex items-center gap-2 text-green-600">
                <span>📍</span>
                {geolocation.address || '내 위치 사용 중'}
              </span>
            ) : (
              <button
                onClick={geolocation.refreshLocation}
                className="flex items-center gap-2 text-primary-500 hover:text-primary-700"
              >
                <span>📍</span>
                위치 권한을 허용하면 더 정확한 검색이 가능해요
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  // 공통 헤더
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

        {/* 위치 상태 */}
        <div className="text-right">
          {geolocation.hasLocation ? (
            <span className="text-xs text-primary-100 flex items-center gap-1">
              <span className="text-green-300">📍</span>
              {geolocation.address ? geolocation.address.split(' ').slice(-2).join(' ') : '위치 사용중'}
            </span>
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

  // 검색 결과가 없을 때: 일반 채팅 레이아웃
  if (!hasResults) {
    return (
      <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-gray-200">
        <div className="h-[calc(100vh-180px)] min-h-[400px] max-h-[600px] flex flex-col">
          <Header />
          <ErrorBanner />

          {/* 채팅 영역 */}
          <div className="flex-1 overflow-y-auto p-4 bg-gray-50 scrollbar-thin">
            <div className="space-y-4">
              {conversationMessages.map((message) => (
                <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
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
              ))}
              {isLoading && (
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-primary-500 flex items-center justify-center text-white text-sm font-medium flex-shrink-0">
                    AI
                  </div>
                  <div className="bg-white rounded-2xl px-4 py-3 border border-gray-200 shadow-sm">
                    <div className="flex space-x-1.5">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse-soft" />
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse-soft" style={{ animationDelay: '200ms' }} />
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse-soft" style={{ animationDelay: '400ms' }} />
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

  // 검색 결과가 있을 때: 결과 중심 레이아웃
  return (
    <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-gray-200">
      <div className="h-[calc(100vh-180px)] min-h-[600px] max-h-[800px] flex flex-col">
        <Header />
        <ErrorBanner />

        {/* 메인 컨텐츠 영역 */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {/* 대화 영역 (축소됨) */}
          {conversationMessages.length > 0 && (
            <div className="bg-gray-50 border-b border-gray-200 p-4">
              <div className="space-y-3 max-h-[150px] overflow-y-auto scrollbar-thin">
                {conversationMessages.map((message) => (
                  <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    {message.role === 'assistant' && (
                      <div className="w-6 h-6 rounded-full bg-primary-500 flex items-center justify-center text-white text-xs font-medium mr-2 flex-shrink-0">
                        AI
                      </div>
                    )}
                    <div className={`max-w-[85%] rounded-xl px-3 py-2 text-base ${
                      message.role === 'user'
                        ? 'bg-primary-500 text-white'
                        : 'bg-white text-gray-900 border border-gray-200'
                    }`}>
                      {message.content}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 결과 영역 */}
          <div className="p-4">
            {/* 검색 조건 요약 */}
            {lastSearchParams && lastResultMessage && (
              <SearchSummary
                searchParams={lastSearchParams}
                totalCount={lastResultMessage.pagination?.total_count || lastResultMessage.jobs.length}
              />
            )}

            {/* 채용공고 목록 */}
            {lastResultMessage && (
              <JobCardList
                jobs={lastResultMessage.jobs}
                pagination={lastResultMessage.pagination}
                onLoadMore={loadMoreJobs}
                isLoadingMore={isLoadingMore}
              />
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* 입력 영역 */}
        <div className="border-t border-gray-200 p-4 bg-white flex-shrink-0">
          <p className="text-xs text-gray-400 mb-2 text-center">
            조건을 바꿔서 다시 검색해보세요
          </p>
          <InputBox onSend={handleSend} disabled={isLoading} />
        </div>
      </div>
    </div>
  )
}
