import { Job } from '../types'
import { JobCard } from './JobCard'

interface Props {
  jobs: Job[]
}

export function JobCardList({ jobs }: Props) {
  if (jobs.length === 0) {
    return null
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-500 mb-2">
        {jobs.length}건의 채용공고를 찾았습니다
      </p>
      <div className="space-y-2">
        {jobs.map((job, index) => (
          <JobCard key={job.id} job={job} index={index} />
        ))}
      </div>
    </div>
  )
}
