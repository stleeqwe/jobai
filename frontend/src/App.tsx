import { ChatWindow } from './components/ChatWindow'

function App() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-primary-100 to-primary-50 flex flex-col">
      {/* 메인 */}
      <main className="flex-1 max-w-4xl w-full mx-auto pt-12 sm:pt-20 pb-4 px-4">
        <ChatWindow />
      </main>

      {/* 푸터 */}
      <footer className="py-4 px-4 text-center text-xs text-gray-400">
        <p>채용공고 정보는 잡코리아에서 제공됩니다.</p>
      </footer>
    </div>
  )
}

export default App
