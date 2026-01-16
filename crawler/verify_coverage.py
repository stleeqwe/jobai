#!/usr/bin/env python3
"""
수집률 검증 스크립트
- 잡코리아 서울 전체 공고 ID vs DB 저장 ID 비교
"""

import asyncio
import os
import re
import time
from typing import Set

import httpx
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# Firestore 프로젝트 설정
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "jobchat-1768149763"))

from google.cloud import firestore

# 서울 25개 구 코드
SEOUL_GU_CODES = {
    "I010": "강남구", "I020": "서초구", "I030": "영등포구", "I040": "강서구",
    "I050": "마포구", "I060": "송파구", "I070": "구로구", "I080": "금천구",
    "I090": "중구", "I100": "성동구", "I110": "용산구", "I120": "종로구",
    "I130": "동대문구", "I140": "성북구", "I150": "강북구", "I160": "도봉구",
    "I170": "노원구", "I180": "은평구", "I190": "서대문구", "I200": "양천구",
    "I210": "강동구", "I220": "광진구", "I230": "중랑구", "I240": "동작구",
    "I250": "관악구",
}

BASE_URL = "https://www.jobkorea.co.kr"
LIST_URL = f"{BASE_URL}/Recruit/Home/_GI_List"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html, */*; q=0.01",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.jobkorea.co.kr/recruit/joblist?menucode=local",
}


async def get_jobkorea_ids() -> Set[str]:
    """잡코리아에서 서울 전체 공고 ID 수집 (목록만)"""
    all_ids: Set[str] = set()

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers=HEADERS,
    ) as client:
        # 세션 초기화 (쿠키 획득)
        init_resp = await client.get(
            f"{BASE_URL}/recruit/joblist",
            params={"menucode": "local", "localorder": "I000"}
        )
        print(f"세션 초기화: {init_resp.status_code}")

        print("\n잡코리아 목록 수집 중...")

        for gu_code, gu_name in SEOUL_GU_CODES.items():
            gu_ids: Set[str] = set()
            page = 1
            prev_ids = None

            while page <= 300:  # 안전 제한
                params = {
                    "Page": page,
                    "local": gu_code,
                    "sorder": "RegDate",
                    "orderBySal": "0",
                }

                try:
                    resp = await client.get(LIST_URL, params=params)

                    if resp.status_code != 200:
                        break

                    # ID 추출 (data-gno 속성, 8자리만 유효)
                    raw_ids = re.findall(r'data-gno="(\d+)"', resp.text)
                    ids = set(i for i in raw_ids if len(i) == 8)

                    if not ids:
                        break

                    # 중복 페이지 감지 (API 제한)
                    if ids == prev_ids:
                        break

                    prev_ids = ids
                    gu_ids.update(ids)
                    page += 1

                    await asyncio.sleep(0.05)  # Rate limit

                except Exception as e:
                    print(f"  {gu_name} 오류: {e}")
                    break

            all_ids.update(gu_ids)
            print(f"  {gu_name}: {len(gu_ids):,}건 (누적: {len(all_ids):,})")

    return all_ids


def get_db_ids() -> Set[str]:
    """Firestore에서 저장된 job_id 전체 조회"""
    print("\nDB 공고 ID 조회 중...")

    db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "jobchat-1768149763"))
    jobs_ref = db.collection("jobs")

    # document ID가 jk_{숫자} 형식
    docs = jobs_ref.stream()

    db_ids = set()
    count = 0
    for doc in docs:
        # jk_12345678 -> 12345678 (숫자만 추출)
        doc_id = doc.id
        if doc_id.startswith("jk_"):
            db_ids.add(doc_id[3:])  # jk_ 제거
        else:
            db_ids.add(doc_id)
        count += 1
        if count % 10000 == 0:
            print(f"  진행: {count:,}건...")

    print(f"  DB 저장 공고: {len(db_ids):,}건")
    return db_ids


async def main():
    print("=" * 60)
    print("수집률 검증")
    print("=" * 60)

    start = time.time()

    # 1. 잡코리아 현재 공고 ID
    jobkorea_ids = await get_jobkorea_ids()
    print(f"\n잡코리아 서울 전체: {len(jobkorea_ids):,}건")

    # 2. DB 저장 공고 ID
    db_ids = get_db_ids()

    # 3. 비교
    print("\n" + "=" * 60)
    print("비교 결과")
    print("=" * 60)

    collected = jobkorea_ids & db_ids  # 교집합: 정상 수집
    missing = jobkorea_ids - db_ids     # 미수집
    expired = db_ids - jobkorea_ids     # 만료/삭제

    print(f"\n잡코리아 현재 공고:    {len(jobkorea_ids):,}건")
    print(f"DB 저장 공고:          {len(db_ids):,}건")
    print(f"")
    print(f"정상 수집 (A ∩ B):     {len(collected):,}건")
    print(f"미수집 (A - B):        {len(missing):,}건")
    print(f"만료/삭제 (B - A):     {len(expired):,}건")

    # 수집률
    if len(jobkorea_ids) > 0:
        coverage = len(collected) / len(jobkorea_ids) * 100
        print(f"\n{'=' * 60}")
        print(f"수집률: {coverage:.1f}%")
        print(f"{'=' * 60}")

    # 미수집 샘플
    if missing:
        print(f"\n미수집 공고 샘플 (최대 10개):")
        for job_id in list(missing)[:10]:
            print(f"  - https://www.jobkorea.co.kr/Recruit/GI_Read/{job_id}")

    elapsed = time.time() - start
    print(f"\n소요 시간: {elapsed:.1f}초")


if __name__ == "__main__":
    asyncio.run(main())
