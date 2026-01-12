import { Message } from '../types'
import { MessageBubble } from './MessageBubble'
import { LoadingIndicator } from './LoadingIndicator'

interface Props {
  messages: Message[]
  isLoading: boolean
}

export function MessageList({ messages, isLoading }: Props) {
  return (
    <div className="space-y-4">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      {isLoading && <LoadingIndicator />}
    </div>
  )
}
