"""
기존 company_address 데이터를 location_full로 복사하는 스크립트
"""
import asyncio
import sys
sys.path.insert(0, '/Users/stlee/Desktop/jobbot/backend')

from google.cloud import firestore

async def update_location_full():
    db = firestore.Client(project="jobbot-1768149763")
    jobs_ref = db.collection("jobs")

    # 모든 jobs 가져오기
    docs = jobs_ref.stream()

    updated = 0
    skipped = 0
    already_has = 0

    for doc in docs:
        data = doc.to_dict()
        location_full = data.get("location_full", "")
        company_address = data.get("company_address", "")

        # location_full이 비어있고 company_address가 있는 경우
        if not location_full and company_address:
            doc.reference.update({"location_full": company_address})
            updated += 1
            print(f"[업데이트] {doc.id}: {company_address}")
        elif location_full:
            already_has += 1
        else:
            skipped += 1

    print(f"\n=== 완료 ===")
    print(f"업데이트: {updated}건")
    print(f"이미 있음: {already_has}건")
    print(f"주소 없음: {skipped}건")

if __name__ == "__main__":
    asyncio.run(update_location_full())
