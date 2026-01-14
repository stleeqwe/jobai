import { useState, useEffect } from 'react'
import { ChatWindow } from './components/ChatWindow'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// EmailJS 설정
const EMAILJS_SERVICE_ID = import.meta.env.VITE_EMAILJS_SERVICE_ID || ''
const EMAILJS_TEMPLATE_ID = import.meta.env.VITE_EMAILJS_TEMPLATE_ID || ''
const EMAILJS_USER_ID = import.meta.env.VITE_EMAILJS_USER_ID || ''

interface ModelInfo {
  model: string
  is_gemini3: boolean
  thinking_enabled: boolean
  thinking_level: string | null
  valid: boolean
  message: string
}

function App() {
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null)
  const [modelError, setModelError] = useState<string | null>(null)
  const [isCheckingModel, setIsCheckingModel] = useState(true)

  const [showFeedback, setShowFeedback] = useState(false)
  const [feedbackText, setFeedbackText] = useState('')
  const [isSending, setIsSending] = useState(false)

  // 앱 시작 시 모델 확인
  useEffect(() => {
    const checkModel = async () => {
      try {
        const res = await fetch(`${API_BASE}/model-info`)
        if (!res.ok) throw new Error('서버 응답 오류')
        const data: ModelInfo = await res.json()
        setModelInfo(data)
        if (!data.valid) {
          setModelError(`AI 모델 설정 오류: ${data.message}`)
        }
      } catch (err) {
        setModelError('백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.')
      } finally {
        setIsCheckingModel(false)
      }
    }
    checkModel()
  }, [])

  const handleSendFeedback = async () => {
    if (!feedbackText.trim() || isSending) return
    setIsSending(true)
    try {
      const res = await fetch('https://api.emailjs.com/api/v1.0/email/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          service_id: EMAILJS_SERVICE_ID,
          template_id: EMAILJS_TEMPLATE_ID,
          user_id: EMAILJS_USER_ID,
          template_params: {
            name: 'JOBBOT 사용자',
            email: 'anonymous@jobbot.com',
            message: feedbackText
          }
        })
      })
      if (res.ok) {
        alert('피드백이 전송되었습니다. 감사합니다!')
        setShowFeedback(false)
        setFeedbackText('')
      } else {
        alert('전송에 실패했습니다. 잠시 후 다시 시도해주세요.')
      }
    } catch {
      alert('전송에 실패했습니다. 잠시 후 다시 시도해주세요.')
    } finally {
      setIsSending(false)
    }
  }

  // 모델 확인 중
  if (isCheckingModel) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-primary-100 to-primary-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto mb-4"></div>
          <p className="text-gray-600">AI 모델 확인 중...</p>
        </div>
      </div>
    )
  }

  // 모델 오류
  if (modelError) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-red-100 to-red-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-xl shadow-lg p-8 max-w-md w-full text-center">
          <div className="text-red-500 text-5xl mb-4">!</div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">서비스 시작 불가</h1>
          <p className="text-gray-600 mb-4">{modelError}</p>
          {modelInfo && (
            <div className="bg-gray-100 rounded-lg p-3 text-sm text-left mb-4">
              <p><strong>현재 모델:</strong> {modelInfo.model}</p>
              <p><strong>필요 모델:</strong> gemini-3-flash-preview</p>
              <p><strong>Thinking:</strong> {modelInfo.thinking_enabled ? 'O' : 'X'}</p>
            </div>
          )}
          <p className="text-xs text-gray-400">backend/.env 파일에서 GEMINI_MODEL 설정을 확인하세요.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-primary-100 to-primary-50 flex flex-col">
      {/* 메인 */}
      <main className="flex-1 max-w-4xl w-full mx-auto py-12 sm:py-20 px-4">
        <ChatWindow />
      </main>

      {/* 푸터 */}
      <footer className="py-4 px-4 text-center text-xs text-gray-400 space-y-1">
        <p>
          <span className="font-medium text-gray-500">Beta Version</span>
          <span className="mx-2">·</span>
          서울시 내 채용공고 (개발, 디자인, 마케팅, 기획, 경영지원)
        </p>
        <p>채용공고 정보는 잡코리아에서 제공됩니다.</p>
      </footer>

      {/* 피드백 버튼 - 우측 하단 고정 */}
      <button
        onClick={() => setShowFeedback(true)}
        className="fixed bottom-6 right-6 bg-gray-700 hover:bg-gray-800 text-white text-sm px-4 py-2 rounded-full shadow-lg transition-colors"
      >
        개발자에게 쓴소리하기
      </button>

      {/* 피드백 모달 */}
      {showFeedback && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">개발자에게 쓴소리하기</h3>
            <textarea
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              placeholder="불편한 점, 개선 아이디어, 버그 제보 등 자유롭게 작성해주세요"
              rows={5}
              className="w-full border border-gray-300 rounded-lg px-4 py-3 text-sm resize-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
            <div className="flex gap-3 mt-4">
              <button
                onClick={() => {
                  setShowFeedback(false)
                  setFeedbackText('')
                }}
                className="flex-1 py-2 text-sm text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleSendFeedback}
                disabled={!feedbackText.trim() || isSending}
                className="flex-1 py-2 text-sm text-white bg-primary-500 hover:bg-primary-600 disabled:bg-gray-300 rounded-lg transition-colors"
              >
                {isSending ? '전송 중...' : '보내기'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
