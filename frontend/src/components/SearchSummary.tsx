// V6: Simple Agentic 검색 파라미터
interface SearchParams {
  job_keywords?: string[]
  salary_min?: number
  commute_origin?: string
  commute_max_minutes?: number
}

interface Props {
  searchParams: SearchParams
  totalCount: number
}

export function SearchSummary({ searchParams, totalCount }: Props) {
  const { job_keywords, salary_min, commute_origin, commute_max_minutes } = searchParams

  // 검색 조건이 없으면 표시하지 않음
  if (!job_keywords?.length && !salary_min && !commute_origin) {
    return null
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4 animate-fade-in-up">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">🔍</span>
        <span className="font-medium text-gray-900">검색 조건</span>
      </div>

      <div className="space-y-2 text-base">
        {job_keywords && job_keywords.length > 0 && (
          <div className="flex items-center gap-3">
            <span className="text-gray-500 w-16">직무</span>
            <span className="text-gray-900 font-medium">{job_keywords.join(', ')}</span>
          </div>
        )}

        {salary_min != null && salary_min > 0 && (
          <div className="flex items-center gap-3">
            <span className="text-gray-500 w-16">연봉</span>
            <span className="text-gray-900 font-medium">{salary_min.toLocaleString()}만원 이상</span>
          </div>
        )}

        {commute_origin && (
          <div className="flex items-center gap-3">
            <span className="text-gray-500 w-16">출발지</span>
            <span className="text-gray-900 font-medium">
              {commute_origin}
              {commute_max_minutes && ` (${commute_max_minutes}분 이내)`}
            </span>
          </div>
        )}
      </div>

      <div className="mt-4 pt-3 border-t border-gray-100">
        <p className="text-primary-600 font-medium">
          {totalCount.toLocaleString()}건의 공고를 찾았습니다
        </p>
      </div>
    </div>
  )
}
