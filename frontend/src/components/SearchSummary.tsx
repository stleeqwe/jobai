interface SearchParams {
  job_type?: string
  salary_min?: number
  location_query?: string
  max_commute_minutes?: number
}

interface Props {
  searchParams: SearchParams
  totalCount: number
}

export function SearchSummary({ searchParams, totalCount }: Props) {
  const { job_type, salary_min, location_query, max_commute_minutes } = searchParams

  // 검색 조건이 없으면 표시하지 않음
  if (!job_type && !salary_min && !location_query) {
    return null
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4 animate-fade-in-up">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">🔍</span>
        <span className="font-medium text-gray-900">검색 조건</span>
      </div>

      <div className="space-y-2 text-base">
        {job_type && (
          <div className="flex items-center gap-3">
            <span className="text-gray-500 w-16">직무</span>
            <span className="text-gray-900 font-medium">{job_type}</span>
          </div>
        )}

        {salary_min && (
          <div className="flex items-center gap-3">
            <span className="text-gray-500 w-16">연봉</span>
            <span className="text-gray-900 font-medium">{salary_min.toLocaleString()}만원 이상</span>
          </div>
        )}

        {location_query && (
          <div className="flex items-center gap-3">
            <span className="text-gray-500 w-16">위치</span>
            <span className="text-gray-900 font-medium">
              {location_query}
              {max_commute_minutes && ` ${max_commute_minutes}분 이내`}
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
