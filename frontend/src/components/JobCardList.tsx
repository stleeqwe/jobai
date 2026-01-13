import { Job, PaginationInfo } from '../types'
import { JobCard } from './JobCard'

interface Props {
  jobs: Job[]
  pagination?: PaginationInfo
  onLoadMore?: () => void
  isLoadingMore?: boolean
}

export function JobCardList({ jobs, pagination, onLoadMore, isLoadingMore }: Props) {
  if (jobs.length === 0) {
    return null
  }

  const totalCount = pagination?.total_count ?? jobs.length
  const hasMore = pagination?.has_next ?? false

  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-500 mb-2">
        {totalCount}건의 채용공고를 찾았습니다
        {pagination && pagination.total_count > jobs.length && (
          <span className="text-gray-400"> (현재 {jobs.length}건 표시)</span>
        )}
      </p>
      <div className="space-y-2">
        {jobs.map((job, index) => (
          <JobCard key={job.id} job={job} index={index} />
        ))}
      </div>

      {/* 더 보기 버튼 */}
      {hasMore && onLoadMore && (
        <div className="mt-4 text-center">
          <button
            onClick={onLoadMore}
            disabled={isLoadingMore}
            className="px-4 py-2 text-sm font-medium text-primary-600 bg-primary-50 rounded-lg hover:bg-primary-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isLoadingMore ? (
              <span className="flex items-center justify-center gap-2">
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
              </span>
            ) : (
              `더 보기 (${totalCount - jobs.length}건 남음)`
            )}
          </button>
        </div>
      )}
    </div>
  )
}
