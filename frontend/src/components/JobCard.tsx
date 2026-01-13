import { Job } from '../types'

interface Props {
  job: Job
  index: number
}

// 마감일 D-day 계산
function calculateDday(deadline: string): string | null {
  if (!deadline || deadline === '상시채용' || deadline === '채용시까지') {
    return null
  }

  try {
    // "2026-02-28" 또는 "~02.28(금)" 형식 처리
    let dateStr = deadline
    if (deadline.includes('~')) {
      // "~02.28(금)" -> "2026-02-28"
      const match = deadline.match(/(\d{2})\.(\d{2})/)
      if (match) {
        const year = new Date().getFullYear()
        const month = parseInt(match[1], 10)
        const day = parseInt(match[2], 10)
        dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
      }
    }

    const deadlineDate = new Date(dateStr)
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    deadlineDate.setHours(0, 0, 0, 0)

    const diffTime = deadlineDate.getTime() - today.getTime()
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))

    if (diffDays < 0) return null
    if (diffDays === 0) return 'D-Day'
    if (diffDays <= 7) return `D-${diffDays}`
    return null
  } catch {
    return null
  }
}

export function JobCard({ job, index }: Props) {
  const dday = calculateDday(job.deadline)
  const hasTravelTime = job.travel_time_minutes !== undefined

  return (
    <a
      href={job.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block bg-white border border-gray-200 rounded-xl p-5 hover:shadow-lg hover:border-primary-300 transition-all duration-200 group"
    >
      {/* 상단: 핵심 정보 (이동시간 & 연봉) */}
      <div className="flex justify-between items-center mb-4 pb-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          {hasTravelTime ? (
            <span className="inline-flex items-center gap-1 bg-blue-100 text-blue-700 px-3 py-1.5 rounded-full text-base font-medium">
              <span>🚇</span>
              {job.travel_time_text || `${job.travel_time_minutes}분`}
            </span>
          ) : (
            <span className="text-sm text-gray-400 px-2">이동시간 정보 없음</span>
          )}
        </div>
        <span className="text-primary-600 font-semibold text-base">
          💰 {job.salary || '협의'}
        </span>
      </div>

      {/* 중앙: 제목 & 회사 */}
      <div className="mb-4">
        <div className="flex items-start gap-2 mb-2">
          <span className="bg-primary-100 text-primary-600 text-sm font-bold px-2.5 py-1 rounded flex-shrink-0 mt-0.5">
            {index + 1}
          </span>
          <h3 className="font-semibold text-gray-900 text-lg line-clamp-2 group-hover:text-primary-600 transition-colors">
            {job.title}
          </h3>
        </div>
        <p className="text-gray-600 text-base ml-9">
          {job.company_name}
        </p>
      </div>

      {/* 태그: 위치, 경력, 고용형태 */}
      <div className="flex flex-wrap gap-2 text-sm mb-4">
        <span className="inline-flex items-center gap-1 bg-gray-100 text-gray-600 px-3 py-1.5 rounded">
          <span>📍</span>
          {job.location}
        </span>
        <span className="bg-gray-100 text-gray-600 px-3 py-1.5 rounded">
          {job.experience}
        </span>
        {job.employment_type && (
          <span className="bg-gray-100 text-gray-600 px-3 py-1.5 rounded">
            {job.employment_type}
          </span>
        )}
      </div>

      {/* 하단: 마감일 & 상세보기 */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-2">
          {dday && (
            <span className={`text-sm font-medium px-2.5 py-1 rounded ${
              dday === 'D-Day' ? 'bg-red-100 text-red-600' :
              dday.startsWith('D-') && parseInt(dday.slice(2)) <= 3 ? 'bg-orange-100 text-orange-600' :
              'bg-yellow-100 text-yellow-700'
            }`}>
              {dday}
            </span>
          )}
          <span className="text-sm text-gray-500">
            마감: {job.deadline || '상시채용'}
          </span>
        </div>
        <span className="text-base text-primary-500 group-hover:text-primary-700 font-medium flex items-center gap-1">
          상세보기
          <svg className="w-5 h-5 group-hover:translate-x-0.5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </span>
      </div>
    </a>
  )
}
