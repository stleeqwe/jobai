export function LoadingIndicator() {
  return (
    <div className="flex justify-start animate-fade-in-up">
      {/* AI 아바타 */}
      <div className="w-8 h-8 rounded-full bg-primary-500 flex items-center justify-center text-white text-sm font-medium mr-2 flex-shrink-0">
        AI
      </div>

      {/* 로딩 버블 */}
      <div className="bg-white rounded-2xl rounded-bl-md px-4 py-3 shadow-sm border border-gray-100">
        <div className="flex space-x-1.5">
          <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse-soft" style={{ animationDelay: '0ms' }} />
          <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse-soft" style={{ animationDelay: '200ms' }} />
          <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse-soft" style={{ animationDelay: '400ms' }} />
        </div>
      </div>
    </div>
  )
}
