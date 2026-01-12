import { ChatWindow } from './components/ChatWindow'

function App() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100">
      {/* 헤더 */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-4xl mx-auto py-4 px-4">
          <h1 className="text-2xl font-bold text-gray-900">
            잡챗
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            자연어로 채용공고를 검색해보세요
          </p>
        </div>
      </header>

      {/* 메인 */}
      <main className="max-w-4xl mx-auto py-6 px-4">
        <ChatWindow />
      </main>

      {/* 푸터 */}
      <footer className="max-w-4xl mx-auto py-4 px-4 text-center text-xs text-gray-400">
        <p>채용공고 정보는 잡코리아에서 제공됩니다.</p>
      </footer>
    </div>
  )
}

export default App
