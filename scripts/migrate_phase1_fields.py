#!/usr/bin/env python3
"""
Phase 1 필드 마이그레이션 스크립트

기존 데이터에 다음 필드를 추가/업데이트합니다:
- company_name_raw: 원본 회사명 (기존 company_name 백업)
- company_name: 정규화된 회사명
- company_type: 법인유형 (stock/limited/partnership/None)
- salary_source: 급여 출처 (direct/parsed/unknown)
- dedup_key: 중복 제거용 MD5 해시

Usage:
    cd /Users/stlee/Desktop/jobbot/jobai
    python scripts/migrate_phase1_fields.py

    # 드라이런 (실제 저장 안함)
    python scripts/migrate_phase1_fields.py --dry-run

    # 특정 개수만
    python scripts/migrate_phase1_fields.py --limit 100
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "crawler"))

from google.cloud import firestore

# Normalizer 임포트
from app.normalizers.company import CompanyNormalizer
from app.normalizers.salary import SalaryParser, SalarySource
from app.normalizers.dedup import DedupKeyGenerator


def get_db() -> firestore.Client:
    """Firestore 클라이언트 반환"""
    return firestore.Client(project="jobchat-1768149763")


async def migrate_jobs(dry_run: bool = False, limit: int = None):
    """
    기존 공고에 Phase 1 필드 적용

    Args:
        dry_run: True면 실제 저장 안함
        limit: 처리할 최대 건수 (None이면 전체)
    """
    print("=" * 60)
    print(f"Phase 1 필드 마이그레이션 시작")
    print(f"모드: {'Dry Run (저장 안함)' if dry_run else '실제 저장'}")
    print(f"제한: {limit if limit else '전체'}")
    print("=" * 60)

    db = get_db()
    company_normalizer = CompanyNormalizer()
    salary_parser = SalaryParser()
    dedup_generator = DedupKeyGenerator()

    # 전체 공고 조회
    query = db.collection("jobs")
    if limit:
        query = query.limit(limit)

    docs = list(query.stream())
    total = len(docs)

    print(f"\n총 {total}건 처리 예정\n")

    batch = db.batch()
    batch_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0

    stats = {
        "company_normalized": 0,
        "salary_source_added": 0,
        "dedup_key_added": 0,
    }

    for i, doc in enumerate(docs):
        try:
            data = doc.to_dict()
            updates = {}
            doc_id = doc.id

            # 1. 회사명 정규화
            original_company = data.get("company_name", "")

            # 이미 company_name_raw가 있으면 스킵
            if "company_name_raw" not in data:
                normalized_name, corp_type = company_normalizer.normalize(original_company)
                updates["company_name_raw"] = original_company
                updates["company_name"] = normalized_name
                updates["company_type"] = corp_type
                stats["company_normalized"] += 1
            else:
                # 기존 raw가 있으면 정규화만 다시 적용
                raw_name = data.get("company_name_raw", original_company)
                normalized_name, corp_type = company_normalizer.normalize(raw_name)
                if data.get("company_type") is None:
                    updates["company_type"] = corp_type

            # 2. salary_source 추가
            if "salary_source" not in data or data.get("salary_source") is None:
                salary_text = data.get("salary_text", "")
                if salary_text:
                    result = salary_parser.parse(salary_text)
                    updates["salary_source"] = result.source.value
                else:
                    updates["salary_source"] = "unknown"
                stats["salary_source_added"] += 1

            # 3. dedup_key 생성
            if "dedup_key" not in data or data.get("dedup_key") is None:
                # dedup_key 생성에 필요한 데이터
                job_for_dedup = {
                    "company_name": updates.get("company_name", data.get("company_name", "")),
                    "title": data.get("title", ""),
                    "location_gugun": data.get("location_gugun", ""),
                }
                updates["dedup_key"] = dedup_generator.generate(job_for_dedup)
                stats["dedup_key_added"] += 1

            # 업데이트할 내용이 있으면 배치에 추가
            if updates:
                updates["updated_at"] = datetime.now(timezone.utc).isoformat()

                if not dry_run:
                    batch.update(doc.reference, updates)
                    batch_count += 1

                updated_count += 1

                # 샘플 출력 (처음 3건)
                if updated_count <= 3:
                    print(f"\n[{doc_id}] 업데이트 예정:")
                    for key, value in updates.items():
                        if key != "updated_at":
                            print(f"  - {key}: {value}")
            else:
                skipped_count += 1

            # 배치 커밋 (500건마다)
            if not dry_run and batch_count >= 500:
                batch.commit()
                print(f"  ... {i + 1}/{total} 저장 완료")
                batch = db.batch()
                batch_count = 0

            # 진행 상황 출력 (100건마다)
            if (i + 1) % 100 == 0:
                print(f"  진행: {i + 1}/{total} ({(i + 1) / total * 100:.1f}%)")

        except Exception as e:
            error_count += 1
            print(f"  [ERROR] {doc.id}: {e}")

    # 남은 배치 커밋
    if not dry_run and batch_count > 0:
        batch.commit()
        print(f"  ... 최종 저장 완료")

    # 결과 출력
    print("\n" + "=" * 60)
    print("마이그레이션 완료")
    print("=" * 60)
    print(f"\n처리 결과:")
    print(f"  - 전체: {total}건")
    print(f"  - 업데이트: {updated_count}건")
    print(f"  - 스킵 (변경 없음): {skipped_count}건")
    print(f"  - 에러: {error_count}건")
    print(f"\n필드별 통계:")
    print(f"  - 회사명 정규화: {stats['company_normalized']}건")
    print(f"  - salary_source 추가: {stats['salary_source_added']}건")
    print(f"  - dedup_key 추가: {stats['dedup_key_added']}건")

    if dry_run:
        print("\n[Dry Run] 실제 저장은 수행되지 않았습니다.")
        print("실제 마이그레이션을 수행하려면 --dry-run 옵션을 제거하세요.")


def main():
    parser = argparse.ArgumentParser(description="Phase 1 필드 마이그레이션")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 저장 없이 시뮬레이션만 수행"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="처리할 최대 건수 (기본: 전체)"
    )

    args = parser.parse_args()

    asyncio.run(migrate_jobs(dry_run=args.dry_run, limit=args.limit))


if __name__ == "__main__":
    main()
