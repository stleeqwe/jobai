"""
기존 채용공고 데이터에 mvp_category 필드 추가 및 job_category 재분류

실행 방법:
    cd /Users/iseungtae/Desktop/jobai
    source crawler/venv/bin/activate
    python scripts/migrate_mvp_category.py
"""

import asyncio
import os
import sys
from collections import Counter

# 프로젝트 경로 설정
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'crawler'))

from google.cloud import firestore

# job_type.py의 매핑을 직접 가져옴
JOB_TYPE_MAPPING = {
    # IT/개발
    "백엔드": ["백엔드", "서버개발", "서버 개발", "backend", "server", "java개발", "python개발"],
    "프론트엔드": ["프론트엔드", "프론트", "frontend", "front-end", "웹퍼블리셔", "퍼블리셔"],
    "풀스택": ["풀스택", "full-stack", "fullstack", "풀스택개발"],
    "앱개발": ["앱개발", "ios", "android", "안드로이드", "모바일개발", "앱 개발", "flutter", "react native"],
    "데이터엔지니어": ["데이터엔지니어", "data engineer", "데이터 엔지니어", "빅데이터"],
    "데이터분석가": ["데이터분석", "data analyst", "데이터 분석", "bi"],
    "AI엔지니어": ["ai엔지니어", "머신러닝", "machine learning", "딥러닝", "ml엔지니어", "ai 개발"],
    "DevOps": ["devops", "데브옵스", "sre", "인프라", "클라우드엔지니어"],
    "QA": ["qa", "테스터", "품질관리", "테스트엔지니어"],
    "DBA": ["dba", "데이터베이스", "db관리"],
    "보안": ["보안", "security", "정보보안", "사이버보안"],
    "소프트웨어개발": ["소프트웨어 개발", "software", "sw개발", "개발자"],
    "임베디드": ["임베디드", "embedded", "펌웨어", "firmware"],
    "게임개발": ["게임개발", "게임 개발", "유니티", "언리얼"],

    # 디자인
    "웹디자이너": ["웹디자이너", "ui디자이너", "ux디자이너", "ui/ux", "웹디자인", "uiux"],
    "그래픽디자이너": ["그래픽디자이너", "시각디자인", "편집디자인", "그래픽 디자인"],
    "영상디자이너": ["영상디자이너", "모션그래픽", "영상편집", "영상 디자인"],
    "3D디자이너": ["3d디자이너", "3d모델러", "3d 디자인"],
    "제품디자이너": ["제품디자이너", "product designer", "프로덕트디자이너"],
    "브랜드디자이너": ["브랜드디자이너", "bi디자이너", "브랜드 디자인"],
    "인테리어디자이너": ["인테리어 디자이너", "인테리어디자이너", "공간디자인"],
    "패션디자이너": ["패션디자이너", "의상디자인"],

    # 기획/PM
    "서비스기획": ["서비스기획", "기획자", "pm", "product manager", "프로덕트매니저", "상품기획"],
    "프로젝트매니저": ["프로젝트매니저", "pmo", "프로젝트 관리"],
    "사업기획": ["사업기획", "사업개발", "bd", "business development"],
    "전략기획": ["전략기획", "경영기획", "전략 기획"],

    # 마케팅
    "마케터": ["마케터", "마케팅", "마케팅담당"],
    "퍼포먼스마케터": ["퍼포먼스마케터", "퍼포먼스 마케팅", "그로스마케터", "그로스해커"],
    "콘텐츠마케터": ["콘텐츠마케터", "콘텐츠 마케팅", "콘텐츠기획"],
    "브랜드마케터": ["브랜드마케터", "브랜드 마케팅", "브랜드매니저"],
    "CRM마케터": ["crm", "crm마케터", "고객관리"],

    # 영업
    "영업": ["영업", "세일즈", "sales", "영업담당", "영업직", "아웃바운드"],
    "기술영업": ["기술영업", "se", "솔루션영업"],
    "해외영업": ["해외영업", "글로벌영업", "무역"],
    "매장관리": ["매장관리", "매장 매니저", "점장", "스토어매니저"],

    # 경영지원
    "인사": ["인사", "hr", "채용", "인사담당"],
    "총무": ["총무", "경영지원", "관리", "사무"],
    "재무회계": ["재무", "회계", "경리", "재무회계", "기장", "세무"],
    "법무": ["법무", "법률", "계약", "법률사무"],
    "비서": ["비서", "행정", "사무보조"],

    # 고객서비스
    "고객상담": ["고객상담", "cs", "고객서비스", "상담원", "콜센터", "상담사", "인바운드"],
    "CS매니저": ["cs매니저", "고객경험", "cx"],

    # 서비스/외식
    "바리스타": ["바리스타", "카페"],
    "조리사": ["조리사", "요리사", "셰프", "주방", "브런치", "베이커", "쉐프"],
    "서비스매니저": ["서비스매니저", "홀매니저", "레스토랑"],

    # 의료/헬스케어
    "간호사": ["간호사", "간호"],
    "의료기사": ["의료기사", "방사선사", "임상병리"],
    "물리치료사": ["물리치료", "재활"],

    # 교육
    "강사": ["강사", "교사", "선생님", "튜터", "멘토"],
    "교육기획": ["교육기획", "교육컨텐츠"],

    # 연구개발
    "연구원": ["연구원", "연구", "r&d"],

    # 크리에이티브
    "콘텐츠크리에이터": ["크리에이터", "bj", "유튜버", "인플루언서", "영상 컨텐츠", "컨텐츠 제작"],
    "PD": ["pd", "디렉터", "td"],

    # 추가 직무 (기타 방지)
    "MD": ["md", "쇼핑몰 md", "온라인 md", "상품md", "머천다이저", "merchandiser"],
    "웹운영": ["홈페이지 지원", "홈페이지 운영", "웹운영", "웹 관리", "사이트 관리"],
    "부동산": ["부동산", "빌딩매매", "공인중개", "중개사", "분양"],
    "의료코디": ["병원 코디네이터", "의료코디", "병원코디", "상담코디"],
}

JOB_CATEGORY_MAPPING = {
    # IT개발
    "백엔드": "IT개발", "프론트엔드": "IT개발", "풀스택": "IT개발",
    "앱개발": "IT개발", "데이터엔지니어": "IT개발", "데이터분석가": "IT개발",
    "AI엔지니어": "IT개발", "DevOps": "IT개발", "QA": "IT개발",
    "DBA": "IT개발", "보안": "IT개발", "소프트웨어개발": "IT개발",
    "임베디드": "IT개발", "게임개발": "IT개발",
    # 디자인
    "웹디자이너": "디자인", "그래픽디자이너": "디자인", "영상디자이너": "디자인",
    "3D디자이너": "디자인", "제품디자이너": "디자인", "브랜드디자이너": "디자인",
    "인테리어디자이너": "디자인", "패션디자이너": "디자인",
    # 기획
    "서비스기획": "기획", "프로젝트매니저": "기획", "사업기획": "기획", "전략기획": "기획",
    # 마케팅
    "마케터": "마케팅", "퍼포먼스마케터": "마케팅", "콘텐츠마케터": "마케팅",
    "브랜드마케터": "마케팅", "CRM마케터": "마케팅",
    # 영업
    "영업": "영업", "기술영업": "영업", "해외영업": "영업", "매장관리": "영업",
    # 경영지원
    "인사": "경영지원", "총무": "경영지원", "재무회계": "경영지원",
    "법무": "경영지원", "비서": "경영지원",
    # 서비스
    "고객상담": "서비스", "CS매니저": "서비스", "바리스타": "서비스",
    "조리사": "서비스", "서비스매니저": "서비스",
    # 의료
    "간호사": "의료", "의료기사": "의료", "물리치료사": "의료",
    # 교육
    "강사": "교육", "교육기획": "교육",
    # 연구
    "연구원": "연구개발",
    # 크리에이티브
    "콘텐츠크리에이터": "크리에이티브", "PD": "크리에이티브",
    # 추가 직무
    "MD": "마케팅", "웹운영": "마케팅", "부동산": "영업", "의료코디": "의료",
}

MVP_CATEGORY_MAPPING = {
    "IT개발": "개발", "디자인": "디자인", "마케팅": "마케팅",
    "기획": "기획", "영업": "영업", "경영지원": "경영지원",
    "서비스": "서비스", "의료": "의료", "교육": "교육",
    "연구개발": "연구개발", "크리에이티브": "크리에이티브", "기타": "기타",
}


def normalize_job_type(raw_text: str) -> str:
    """원본 직무명을 정규화된 직무명으로 변환"""
    if not raw_text:
        return ""
    raw_lower = raw_text.lower().strip()
    for normalized, variants in JOB_TYPE_MAPPING.items():
        for variant in variants:
            if variant.lower() in raw_lower:
                return normalized
    return raw_text.strip()


def get_job_category(job_type: str) -> str:
    """정규화된 직무명에서 카테고리 추출"""
    return JOB_CATEGORY_MAPPING.get(job_type, "기타")


def get_mvp_category(job_category: str) -> str:
    """직무 카테고리에서 MVP 카테고리 추출"""
    return MVP_CATEGORY_MAPPING.get(job_category, "기타")


async def migrate_data():
    """기존 데이터 마이그레이션"""

    # 환경변수 설정
    os.environ.setdefault('GOOGLE_CLOUD_PROJECT', 'jobchat-1768149763')
    credentials_path = os.path.expanduser('~/jobchat-credentials.json')
    if os.path.exists(credentials_path):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path

    db = firestore.AsyncClient()

    print("=" * 60)
    print("JobChat 데이터 마이그레이션")
    print("=" * 60)

    # 모든 활성 공고 조회
    query = db.collection("jobs").where("is_active", "==", True)

    total_count = 0
    updated_count = 0
    category_changes = Counter()
    mvp_added = 0

    print("\n마이그레이션 시작...")

    async for doc in query.stream():
        total_count += 1
        job = doc.to_dict()
        updates = {}

        # 1. job_type_raw를 기반으로 재정규화
        job_type_raw = job.get("job_type_raw", "") or job.get("title", "")
        current_category = job.get("job_category", "기타")

        # job_type_raw로 다시 정규화 시도
        new_job_type = normalize_job_type(job_type_raw)
        new_category = get_job_category(new_job_type) if new_job_type else "기타"
        new_mvp_category = get_mvp_category(new_category)

        # 2. 변경 사항 확인
        if current_category == "기타" and new_category != "기타":
            updates["job_type"] = new_job_type
            updates["job_category"] = new_category
            category_changes[f"기타 → {new_category}"] += 1

        # 3. mvp_category 추가 (항상)
        current_mvp = job.get("mvp_category", "")
        if not current_mvp:
            # mvp_category가 없으면 job_category 기반으로 설정
            final_category = updates.get("job_category", current_category)
            updates["mvp_category"] = get_mvp_category(final_category)
            mvp_added += 1

        # 4. 업데이트 실행
        if updates:
            await doc.reference.update(updates)
            updated_count += 1

        # 진행 상황 출력
        if total_count % 50 == 0:
            print(f"  처리 중: {total_count}건...")

    # 결과 출력
    print("\n" + "=" * 60)
    print("마이그레이션 완료")
    print("=" * 60)
    print(f"총 처리: {total_count}건")
    print(f"업데이트: {updated_count}건")
    print(f"mvp_category 추가: {mvp_added}건")

    if category_changes:
        print("\n카테고리 변경 내역:")
        for change, count in category_changes.most_common():
            print(f"  {change}: {count}건")

    print("\n검증 중...")

    # 검증
    etc_count = 0
    mvp_empty = 0
    verify_query = db.collection("jobs").where("is_active", "==", True)

    async for doc in verify_query.stream():
        job = doc.to_dict()
        if job.get("job_category") == "기타":
            etc_count += 1
        if not job.get("mvp_category"):
            mvp_empty += 1

    print(f"\n검증 결과:")
    print(f"  '기타' 카테고리: {etc_count}건 ({etc_count/total_count*100:.1f}%)")
    print(f"  mvp_category 없음: {mvp_empty}건 ({mvp_empty/total_count*100:.1f}%)")

    if etc_count / total_count > 0.05:
        print("\n⚠️  '기타' 비율이 5% 초과입니다. 추가 매핑이 필요합니다.")
    else:
        print("\n✓ 마이그레이션 성공!")


if __name__ == "__main__":
    asyncio.run(migrate_data())
