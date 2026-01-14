import { useState, useEffect } from 'react'
import { Job, PaginationInfo } from '../types'
import { JobCard } from './JobCard'

interface Props {
  jobs: Job[]
  pagination?: PaginationInfo
  onLoadMore?: () => void
  isLoadingMore?: boolean
}

const ITEMS_PER_PAGE = 10

export function JobCardList({ jobs, pagination, onLoadMore, isLoadingMore }: Props) {
  // 클라이언트 페이지네이션: 10건씩 표시
  const [displayCount, setDisplayCount] = useState(ITEMS_PER_PAGE)

  // 새 검색 시 페이지네이션 리셋
  useEffect(() => {
    setDisplayCount(ITEMS_PER_PAGE)
  }, [jobs.length, pagination?.total_count])

  if (jobs.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="text-4xl mb-4">🔍</div>
        <p className="text-gray-500">조건에 맞는 채용공고가 없습니다</p>
        <p className="text-gray-400 text-sm mt-2">다른 조건으로 검색해보세요</p>
      </div>
    )
  }

  // 현재 표시할 공고들
  const displayedJobs = jobs.slice(0, displayCount)
  const hasMoreLocal = displayCount < jobs.length
  const remainingLocal = jobs.length - displayCount

  // 서버 페이지네이션 정보
  const totalCount = pagination?.total_count ?? jobs.length
  const hasMoreServer = pagination?.has_more ?? false
  const remainingServer = pagination?.remaining ?? 0

  // 더 보기 핸들러
  const handleLoadMore = () => {
    if (hasMoreLocal) {
      // 클라이언트에서 더 표시
      setDisplayCount(prev => Math.min(prev + ITEMS_PER_PAGE, jobs.length))
    } else if (hasMoreServer && onLoadMore) {
      // 서버에서 더 불러오기
      onLoadMore()
    }
  }

  const showLoadMore = hasMoreLocal || hasMoreServer
  const remainingCount = hasMoreLocal ? remainingLocal : remainingServer

  return (
    <div>
      {/* 결과 카운트 */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">
          {totalCount.toLocaleString()}건의 채용공고
        </h3>
        {totalCount > displayedJobs.length && (
          <span className="text-sm text-gray-500">
            {displayedJobs.length}건 표시 중
          </span>
        )}
      </div>

      {/* 카드 목록 */}
      <div className="space-y-3">
        {displayedJobs.map((job, index) => (
          <div
            key={job.id}
            className="animate-fade-in-up"
            style={{ animationDelay: `${Math.min(index % ITEMS_PER_PAGE, 5) * 50}ms` }}
          >
            <JobCard job={job} index={index} />
          </div>
        ))}
      </div>

      {/* 더 보기 버튼 */}
      {showLoadMore && (
        <div className="mt-6 text-center">
          <button
            onClick={handleLoadMore}
            disabled={isLoadingMore}
            className="inline-flex items-center justify-center gap-2 px-6 py-3 text-sm font-medium
                       text-primary-600 bg-primary-50 rounded-xl
                       hover:bg-primary-100 hover:text-primary-700
                       disabled:opacity-50 disabled:cursor-not-allowed
                       transition-all duration-200 min-w-[200px]"
          >
            {isLoadingMore ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                    fill="none"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                불러오는 중...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
                더 보기 ({remainingCount.toLocaleString()}건 남음)
              </>
            )}
          </button>
        </div>
      )}

      {/* 모든 결과 로드 완료 */}
      {!showLoadMore && displayedJobs.length > 0 && (
        <div className="mt-6 text-center text-sm text-gray-400">
          모든 결과를 불러왔습니다
        </div>
      )}

      {/* 출처 표시 */}
      <div className="mt-6 pt-4 border-t border-gray-100 text-center">
        <p className="text-xs text-gray-400">
          sourced from <span className="font-medium text-primary-500">JOBKOREA</span>
        </p>
      </div>
    </div>
  )
}
