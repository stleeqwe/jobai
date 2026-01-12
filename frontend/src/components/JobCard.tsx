import { Job } from '../types'

interface Props {
  job: Job
  index: number
}

export function JobCard({ job, index }: Props) {
  return (
    <a
      href={job.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md hover:border-primary-300 transition-all duration-200"
    >
      {/* 순번 + 제목 */}
      <div className="flex items-start gap-2 mb-2">
        <span className="bg-primary-100 text-primary-600 text-xs font-medium px-2 py-0.5 rounded flex-shrink-0">
          {index + 1}
        </span>
        <h3 className="font-medium text-gray-900 line-clamp-2 flex-1 text-sm">
          {job.title}
        </h3>
      </div>

      {/* 회사명 */}
      <p className="text-sm text-gray-600 mb-3">
        {job.company_name}
      </p>

      {/* 조건 태그 */}
      <div className="flex flex-wrap gap-1.5 text-xs">
        <span className="bg-gray-100 text-gray-700 px-2 py-1 rounded-full">
          {job.location}
        </span>
        <span className="bg-gray-100 text-gray-700 px-2 py-1 rounded-full">
          {job.salary}
        </span>
        <span className="bg-gray-100 text-gray-700 px-2 py-1 rounded-full">
          {job.experience}
        </span>
        {job.employment_type && (
          <span className="bg-gray-100 text-gray-700 px-2 py-1 rounded-full">
            {job.employment_type}
          </span>
        )}
      </div>

      {/* 마감일 */}
      <div className="mt-3 flex justify-between items-center">
        <span className="text-xs text-gray-500">
          마감: {job.deadline || '상시채용'}
        </span>
        <span className="text-xs text-primary-500 hover:text-primary-700 font-medium">
          상세보기 &rarr;
        </span>
      </div>
    </a>
  )
}
