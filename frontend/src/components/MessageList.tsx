import { useMemo } from 'react'
import { Message } from '../types'
import { MessageBubble } from './MessageBubble'
import { LoadingIndicator } from './LoadingIndicator'

interface Props {
  messages: Message[]
  isLoading: boolean
  onLoadMore?: () => void
  isLoadingMore?: boolean
}

export function MessageList({ messages, isLoading, onLoadMore, isLoadingMore }: Props) {
  // 마지막 assistant 메시지 ID 찾기 (더 보기 버튼 표시용)
  const lastAssistantMessageId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant' && messages[i].jobs.length > 0) {
        return messages[i].id
      }
    }
    return null
  }, [messages])

  return (
    <div className="space-y-4">
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
          onLoadMore={onLoadMore}
          isLoadingMore={isLoadingMore}
          showLoadMore={message.id === lastAssistantMessageId}
        />
      ))}

      {isLoading && <LoadingIndicator />}
    </div>
  )
}
