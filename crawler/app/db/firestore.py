"""Firestore 데이터베이스 모듈"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Union
from google.cloud import firestore
from google.oauth2 import service_account

from app.config import settings


def _normalize_datetime(dt: Union[datetime, str, None]) -> Optional[datetime]:
    """
    다양한 형태의 datetime을 UTC aware datetime으로 정규화

    Args:
        dt: datetime 객체, ISO 문자열, 또는 None

    Returns:
        UTC timezone aware datetime 또는 None
    """
    if dt is None:
        return None

    try:
        # 문자열인 경우
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))

        # datetime 객체인 경우
        if isinstance(dt, datetime):
            # timezone이 없으면 UTC로 가정
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

    except (ValueError, TypeError):
        pass

    return None

# Firestore 클라이언트 (lazy initialization)
_db: Optional[firestore.Client] = None


def get_db() -> firestore.Client:
    """Firestore 클라이언트 반환 (싱글톤)"""
    global _db
    if _db is None:
        credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        project = settings.GOOGLE_CLOUD_PROJECT or None
        if credentials_path:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path
            )
            if not project:
                project = getattr(credentials, "project_id", None)
            if project:
                _db = firestore.Client(
                    project=project,
                    credentials=credentials
                )
            else:
                _db = firestore.Client(credentials=credentials)
        else:
            if project:
                _db = firestore.Client(project=project)
            else:
                _db = firestore.Client()
    return _db


async def save_jobs(jobs: list[dict]) -> dict[str, int]:
    """
    채용공고 배치 저장 (Upsert 방식 - doc.get() 제거)

    - batch.set(merge=True)로 신규/업데이트 통합 처리
    - N번의 read 연산 제거 → 속도/비용 대폭 개선

    Args:
        jobs: 저장할 채용공고 리스트

    Returns:
        저장 통계 {'new': 신규 추정, 'updated': 업데이트 추정, 'failed': 실패}

    Note:
        merge=True 사용으로 신규/업데이트 구분이 정확하지 않음.
        정확한 카운트가 필요하면 existing_ids를 미리 조회하는 방식 사용.
    """
    db = get_db()
    stats = {"new": 0, "updated": 0, "failed": 0}

    if not jobs:
        return stats

    batch = db.batch()
    batch_count = 0
    now = datetime.now(timezone.utc).isoformat()

    # 기존 ID 조회 (한 번만 스트림으로)
    job_ids = [job["id"] for job in jobs]
    existing_ids = set()

    try:
        # 배치 크기가 크면 in 쿼리 분할 필요 (Firestore 제한: 30개)
        for i in range(0, len(job_ids), 30):
            chunk = job_ids[i:i + 30]
            query = db.collection("jobs").where("__name__", "in", chunk).select([])
            for doc in query.stream():
                existing_ids.add(doc.id)
    except Exception as e:
        # 조회 실패 시 전부 업데이트로 처리 (안전하게)
        if settings.DEBUG:
            print(f"[DB] 기존 ID 조회 실패: {e}")

    for job in jobs:
        try:
            doc_ref = db.collection("jobs").document(job["id"])
            is_existing = job["id"] in existing_ids

            if is_existing:
                # 기존 공고: crawled_at 유지, updated_at 갱신
                update_data = {**job, "updated_at": now}
                update_data.pop("crawled_at", None)
                update_data.pop("view_count", None)  # view_count도 유지
                batch.set(doc_ref, update_data, merge=True)
                stats["updated"] += 1
            else:
                # 신규 공고: 모든 필드 설정
                job_data = {
                    **job,
                    "crawled_at": now,
                    "updated_at": now,
                    "view_count": 0,
                }
                batch.set(doc_ref, job_data)
                stats["new"] += 1

            batch_count += 1

            # Firestore 배치는 최대 500개
            if batch_count >= 500:
                await asyncio.to_thread(batch.commit)
                batch = db.batch()
                batch_count = 0

        except Exception as e:
            stats["failed"] += 1
            if settings.DEBUG:
                print(f"[DB] 저장 실패 {job.get('id')}: {e}")

    # 남은 배치 커밋
    if batch_count > 0:
        await asyncio.to_thread(batch.commit)

    return stats


async def mark_expired_jobs(active_ids: set[str]) -> int:
    """
    크롤링되지 않은 공고를 만료 처리

    Args:
        active_ids: 현재 활성 공고 ID 집합

    Returns:
        만료 처리된 공고 수
    """
    db = get_db()

    # 기존 활성 공고 조회
    query = db.collection("jobs").where("is_active", "==", True)
    docs = query.stream()

    batch = db.batch()
    count = 0
    batch_count = 0

    for doc in docs:
        if doc.id not in active_ids:
            batch.update(doc.reference, {
                "is_active": False,
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            count += 1
            batch_count += 1

            if batch_count >= 500:
                await asyncio.to_thread(batch.commit)
                batch = db.batch()
                batch_count = 0

    if batch_count > 0:
        await asyncio.to_thread(batch.commit)

    return count


async def save_crawl_log(log_data: dict) -> None:
    """
    크롤링 로그 저장

    Args:
        log_data: 크롤링 로그 데이터
    """
    db = get_db()

    today = datetime.now().strftime("%Y-%m-%d")
    doc_ref = db.collection("crawl_logs").document(today)

    # 기존 로그가 있으면 업데이트, 없으면 생성
    doc = doc_ref.get()

    if doc.exists:
        # 오늘 이미 크롤링 기록이 있으면 업데이트
        existing = doc.to_dict()
        log_data["run_count"] = existing.get("run_count", 0) + 1
        doc_ref.update(log_data)
    else:
        log_data["id"] = today
        log_data["run_count"] = 1
        doc_ref.set(log_data)


async def get_active_job_count() -> int:
    """활성 공고 수 조회"""
    db = get_db()
    query = db.collection("jobs").where("is_active", "==", True)

    # count() aggregation 사용
    count_query = query.count()
    result = count_query.get()

    return result[0][0].value if result else 0


async def get_job_stats() -> dict:
    """
    채용공고 통계 조회

    Returns:
        통계 정보 딕셔너리
    """
    db = get_db()

    # 전체 공고 수
    total_query = db.collection("jobs").count()
    total_result = total_query.get()
    total_jobs = total_result[0][0].value if total_result else 0

    # 활성 공고 수
    active_count = await get_active_job_count()

    # 최근 크롤링 로그
    crawl_logs = (
        db.collection("crawl_logs")
        .order_by("started_at", direction=firestore.Query.DESCENDING)
        .limit(1)
        .get()
    )

    last_crawl = None
    for log in crawl_logs:
        last_crawl = log.to_dict().get("finished_at")

    return {
        "total_jobs": total_jobs,
        "active_jobs": active_count,
        "last_crawl": last_crawl,
    }


async def expire_by_deadline() -> int:
    """
    마감일 기준 공고 만료 처리

    처리 규칙:
    - deadline_type == "date" and deadline_date < 오늘: 만료
    - deadline_type == "ongoing" (상시채용): 90일 후 검증 대상으로만 표시
    - deadline_type == "until_hired" (채용시 마감): 30일 후 검증 대상으로 표시

    Returns:
        만료 처리된 공고 수
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 활성 공고 중 마감일이 지난 것 조회
    query = db.collection("jobs").where("is_active", "==", True)
    docs = query.stream()

    batch = db.batch()
    count = 0
    batch_count = 0

    for doc in docs:
        job = doc.to_dict()
        should_expire = False
        update_data = {}

        deadline_type = job.get("deadline_type", "unknown")
        deadline_date = job.get("deadline_date")

        if deadline_type == "date" and deadline_date:
            # datetime 객체로 변환
            deadline_date = _normalize_datetime(deadline_date)
            if deadline_date and deadline_date < today:
                should_expire = True

        elif deadline_type == "ongoing":
            # 상시채용: 90일 후 needs_verification 플래그
            created_at = job.get("created_at")
            created_at = _normalize_datetime(created_at)
            if created_at and (now - created_at).days >= 90:
                update_data["needs_verification"] = True

        elif deadline_type == "until_hired":
            # 채용시 마감: 30일 후 needs_verification 플래그
            created_at = job.get("created_at")
            created_at = _normalize_datetime(created_at)
            if created_at and (now - created_at).days >= 30:
                update_data["needs_verification"] = True

        if should_expire:
            update_data["is_active"] = False
            update_data["expired_at"] = now.isoformat()
            count += 1

        if update_data:
            update_data["updated_at"] = now.isoformat()
            batch.update(doc.reference, update_data)
            batch_count += 1

            if batch_count >= 500:
                await asyncio.to_thread(batch.commit)
                batch = db.batch()
                batch_count = 0

    if batch_count > 0:
        await asyncio.to_thread(batch.commit)

    return count


async def get_jobs_for_verification(
    days_since_verified: int = 7,
    max_count: int = 10000
) -> list[str]:
    """
    검증이 필요한 공고 ID 조회

    Args:
        days_since_verified: 마지막 검증 이후 경과 일수
        max_count: 최대 조회 건수

    Returns:
        검증이 필요한 공고 ID 리스트
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    cutoff_date = now - timedelta(days=days_since_verified)

    job_ids = []

    # 1. needs_verification 플래그가 있는 공고
    query1 = (
        db.collection("jobs")
        .where("is_active", "==", True)
        .where("needs_verification", "==", True)
        .limit(max_count // 2)
    )

    for doc in query1.stream():
        job_ids.append(doc.id)

    # 2. last_verified가 오래된 공고
    # 참고: Firestore 복합 쿼리 제한으로 클라이언트 필터링 필요
    remaining = max_count - len(job_ids)
    if remaining > 0:
        query2 = (
            db.collection("jobs")
            .where("is_active", "==", True)
            .limit(remaining * 2)  # 여유 있게 조회
        )

        for doc in query2.stream():
            if doc.id in job_ids:
                continue

            job = doc.to_dict()
            last_verified = job.get("last_verified")

            if last_verified:
                if isinstance(last_verified, str):
                    try:
                        last_verified = datetime.fromisoformat(
                            last_verified.replace("Z", "+00:00")
                        )
                    except:
                        last_verified = None

                if last_verified and last_verified < cutoff_date:
                    job_ids.append(doc.id)
            else:
                # last_verified가 없으면 검증 대상
                job_ids.append(doc.id)

            if len(job_ids) >= max_count:
                break

    return job_ids[:max_count]


async def mark_jobs_expired(job_ids: list[str]) -> int:
    """
    지정된 공고들을 만료 처리

    Args:
        job_ids: 만료 처리할 공고 ID 리스트

    Returns:
        만료 처리된 공고 수
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    batch = db.batch()
    count = 0
    batch_count = 0

    for job_id in job_ids:
        doc_ref = db.collection("jobs").document(job_id)
        batch.update(doc_ref, {
            "is_active": False,
            "expired_at": now,
            "updated_at": now,
        })
        count += 1
        batch_count += 1

        if batch_count >= 500:
            await asyncio.to_thread(batch.commit)
            batch = db.batch()
            batch_count = 0

    if batch_count > 0:
        await asyncio.to_thread(batch.commit)

    return count


async def update_last_verified(job_ids: list[str]) -> None:
    """
    공고들의 last_verified 갱신

    Args:
        job_ids: 갱신할 공고 ID 리스트
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    batch = db.batch()
    batch_count = 0

    for job_id in job_ids:
        doc_ref = db.collection("jobs").document(job_id)
        batch.update(doc_ref, {
            "last_verified": now,
            "needs_verification": False,
        })
        batch_count += 1

        if batch_count >= 500:
            await asyncio.to_thread(batch.commit)
            batch = db.batch()
            batch_count = 0

    if batch_count > 0:
        await asyncio.to_thread(batch.commit)
