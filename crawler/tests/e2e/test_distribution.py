#!/usr/bin/env python3
"""구별 분산 크롤링 가능성 검토"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.session_manager import SessionManager
from app.core.ajax_client import AjaxClient


# 서울 25개 구 코드
SEOUL_GU_CODES = {
    "강남구": "I010", "강동구": "I020", "강북구": "I030", "강서구": "I040",
    "관악구": "I050", "광진구": "I060", "구로구": "I070", "금천구": "I080",
    "노원구": "I090", "도봉구": "I100", "동대문구": "I110", "동작구": "I120",
    "마포구": "I130", "서대문구": "I140", "서초구": "I150", "성동구": "I160",
    "성북구": "I170", "송파구": "I180", "양천구": "I190", "영등포구": "I200",
    "용산구": "I210", "은평구": "I220", "종로구": "I230", "중구": "I240", "중랑구": "I250",
}


async def test_gu_distribution():
    """구별 공고 수 및 페이지네이션 확인"""
    print("=" * 70)
    print("구별 분산 크롤링 가능성 검토")
    print("=" * 70)

    session = SessionManager()
    client = await session.initialize()
    ajax = AjaxClient(client)

    total_jobs = 0
    gu_stats = []

    print(f"\n{'구':<10} {'공고수':>10} {'페이지':>8} {'500p제한':>10}")
    print("-" * 45)

    for gu_name, gu_code in SEOUL_GU_CODES.items():
        # 해당 구의 전체 공고 수 조회
        count = await ajax.get_total_count(local=gu_code)
        pages = (count // 40) + 1 if count > 0 else 0
        within_limit = "✅" if pages <= 500 else f"❌ ({pages}p)"

        gu_stats.append({
            "name": gu_name,
            "code": gu_code,
            "count": count,
            "pages": pages,
        })
        total_jobs += count

        print(f"{gu_name:<10} {count:>10,} {pages:>8} {within_limit:>10}")

    print("-" * 45)
    print(f"{'합계':<10} {total_jobs:>10,}")

    # 500페이지 초과하는 구 확인
    over_limit = [g for g in gu_stats if g["pages"] > 500]

    print(f"\n[분석]")
    print(f"  - 총 공고: {total_jobs:,}건")
    print(f"  - 500p 초과 구: {len(over_limit)}개")

    if over_limit:
        print(f"  - 초과 구: {', '.join([g['name'] for g in over_limit])}")
        print(f"  → 이 구들은 추가 분할 필요")
    else:
        print(f"  → 모든 구가 500p 이내! 구별 크롤링으로 전체 수집 가능")

    # 페이지네이션 테스트 (상위 3개 구)
    print(f"\n[페이지네이션 테스트]")
    top3 = sorted(gu_stats, key=lambda x: x["count"], reverse=True)[:3]

    for gu in top3:
        print(f"\n{gu['name']} ({gu['count']:,}건):")

        # 1페이지, 중간, 마지막 페이지 샘플
        test_pages = [1, min(50, gu["pages"]), min(100, gu["pages"])]
        all_ids = set()

        for page in test_pages:
            ids = await ajax.fetch_page(page, local=gu["code"])
            new_ids = set(ids) - all_ids
            all_ids.update(ids)
            print(f"  페이지 {page:3d}: {len(ids)}개, 신규 {len(new_ids)}개")

    await session.close()

    print("\n" + "=" * 70)
    print("결론")
    print("=" * 70)

    if not over_limit:
        print("✅ 구별 분산 크롤링으로 전체 63,000+건 수집 가능!")
        print("   → 25개 구 각각 크롤링 후 ID 통합")
    else:
        print("⚠️ 일부 구가 500p 초과")
        print("   → 해당 구는 추가 필터(직무, 경력 등) 필요")


if __name__ == "__main__":
    asyncio.run(test_gu_distribution())
