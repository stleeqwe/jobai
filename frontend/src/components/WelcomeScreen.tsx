import { useState, useEffect } from 'react'

interface Props {
  onSubmit: (query: string) => void
  disabled?: boolean
}

const PLACEHOLDER = '예: 강남역 근처 연봉 5천 이상 웹 디자이너'

export function WelcomeScreen({ onSubmit, disabled }: Props) {
  const [input, setInput] = useState('')
  const [animatedPlaceholder, setAnimatedPlaceholder] = useState('')

  // 타이핑 애니메이션 효과
  useEffect(() => {
    let index = 0
    const interval = setInterval(() => {
      if (index <= PLACEHOLDER.length) {
        setAnimatedPlaceholder(PLACEHOLDER.slice(0, index))
        index++
      } else {
        clearInterval(interval)
      }
    }, 50)

    return () => clearInterval(interval)
  }, [])

  const handleSubmit = () => {
    const trimmed = input.trim()
    if (trimmed && !disabled) {
      onSubmit(trimmed)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="relative flex flex-col items-center pt-8 pb-6 px-4">
      {/* 우측 상단 AI 표시 */}
      <p className="absolute top-3 right-4 text-xs text-gray-400">
        powered by <span className="font-medium">Gemini</span>
      </p>

      {/* 로고 & 타이틀 */}
      <div className="text-center mb-8">
        <h1 className="text-5xl font-bold text-primary-600 mb-3" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
          JOBBOT
        </h1>
        <p className="text-xl text-gray-500">
          한 문장으로 원하는 일자리를 찾아보세요
        </p>
      </div>

      {/* 메인 입력 영역 */}
      <div className="w-full max-w-lg">
        <div className="relative">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={animatedPlaceholder || PLACEHOLDER}
            disabled={disabled}
            rows={2}
            className="w-full resize-none rounded-2xl border-2 border-primary-200 bg-white px-6 py-5 pr-16 text-lg
                       focus:ring-2 focus:ring-primary-500 focus:border-primary-500
                       disabled:bg-gray-100 disabled:cursor-not-allowed
                       placeholder:text-gray-400 shadow-sm"
          />
          <button
            onClick={handleSubmit}
            disabled={disabled || !input.trim()}
            className="absolute right-3 bottom-3 p-3 bg-primary-500 text-white rounded-xl
                       hover:bg-primary-600 disabled:bg-gray-300
                       disabled:cursor-not-allowed transition-colors"
          >
            {disabled ? (
              <svg className="animate-spin h-6 w-6" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
