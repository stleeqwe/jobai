import { Message } from '../types'
import { JobCardList } from './JobCardList'

interface Props {
  message: Message
  onLoadMore?: () => void
  isLoadingMore?: boolean
  showLoadMore?: boolean
}

export function MessageBubble({ message, onLoadMore, isLoadingMore, showLoadMore }: Props) {
  const isUser = message.role === 'user'

  return (
    <div
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} animate-fade-in-up`}
    >
      {/* AI 아바타 */}
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-primary-500 flex items-center justify-center text-white text-sm font-medium mr-2 flex-shrink-0">
          AI
        </div>
      )}

      <div className={`max-w-[80%] ${isUser ? '' : 'flex flex-col'}`}>
        {/* 메시지 버블 */}
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? 'bg-primary-500 text-white rounded-br-md'
              : 'bg-white text-gray-900 rounded-bl-md shadow-sm border border-gray-100'
          }`}
        >
          <p className="whitespace-pre-wrap text-sm leading-relaxed">
            {message.content}
          </p>
        </div>

        {/* 채용공고 목록 */}
        {!isUser && message.jobs && message.jobs.length > 0 && (
          <div className="mt-3">
            <JobCardList
              jobs={message.jobs}
              pagination={message.pagination}
              onLoadMore={showLoadMore ? onLoadMore : undefined}
              isLoadingMore={isLoadingMore}
            />
          </div>
        )}

        {/* 타임스탬프 */}
        {message.timestamp && (
          <span className={`text-xs text-gray-400 mt-1 ${isUser ? 'text-right block' : ''}`}>
            {new Date(message.timestamp).toLocaleTimeString('ko-KR', {
              hour: '2-digit',
              minute: '2-digit'
            })}
          </span>
        )}
      </div>
    </div>
  )
}
