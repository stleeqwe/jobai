export function JobCardSkeleton() {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 animate-pulse">
      {/* 상단: 이동시간 & 연봉 */}
      <div className="flex justify-between items-center mb-3 pb-3 border-b border-gray-100">
        <div className="h-6 w-20 bg-gray-200 rounded-full" />
        <div className="h-6 w-24 bg-gray-200 rounded-full" />
      </div>

      {/* 제목 & 회사 */}
      <div className="space-y-2 mb-4">
        <div className="h-5 w-3/4 bg-gray-200 rounded" />
        <div className="h-4 w-1/2 bg-gray-200 rounded" />
      </div>

      {/* 태그들 */}
      <div className="flex gap-2 mb-4">
        <div className="h-5 w-16 bg-gray-200 rounded" />
        <div className="h-5 w-12 bg-gray-200 rounded" />
        <div className="h-5 w-14 bg-gray-200 rounded" />
      </div>

      {/* 하단 */}
      <div className="flex justify-between items-center">
        <div className="h-4 w-20 bg-gray-200 rounded" />
        <div className="h-4 w-16 bg-gray-200 rounded" />
      </div>
    </div>
  )
}

export function JobCardSkeletonList({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, index) => (
        <JobCardSkeleton key={index} />
      ))}
    </div>
  )
}
