"""
상세 페이지 파서 모듈

잡코리아 공고 상세 페이지에서 정보를 추출하는 파서.
정규식을 모듈 레벨에서 컴파일하여 성능 최적화.
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from app.config import CrawlerConfig
from app.normalizers import (
    normalize_job_type,
    get_job_category,
    get_mvp_category,
    normalize_location,
    parse_salary,
)
from app.normalizers.company import CompanyNormalizer


# ========== 컴파일된 정규식 패턴 (성능 최적화) ==========

_PATTERNS = {
    # 제목 추출
    "json_ld_title": re.compile(r'"@type"\s*:\s*"JobPosting"[^}]*"title"\s*:\s*"([^"]+)"', re.DOTALL),
    "json_ld_title_fallback": re.compile(r'"title"\s*:\s*"([^"]{10,})"'),
    "html_title": re.compile(r'<title>([^<]+)</title>'),
    "title_filter": re.compile(r'^.{2,20}\s*채용$'),

    # 회사명 추출
    "hiring_org": re.compile(r'"hiringOrganization"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"'),

    # 직무 필드
    "work_fields": re.compile(r'workFields\\?":\s*\[([^\]]*)\]'),
    "work_fields_values": re.compile(r'\\?"([^"\\]+)\\?"'),

    # 급여 패턴 (순서대로 매칭 시도)
    "salary_patterns": [
        re.compile(r'(월급?\s*[\d,]+\s*~\s*[\d,]+\s*만원)', re.IGNORECASE),
        re.compile(r'(연봉?\s*[\d,]+\s*~\s*[\d,]+\s*만원)', re.IGNORECASE),
        re.compile(r'([\d,]+\s*~\s*[\d,]+\s*만원)', re.IGNORECASE),
        re.compile(r'(월급?\s*[\d,]+\s*만원)', re.IGNORECASE),
        re.compile(r'(연봉?\s*[\d,]+\s*만원)', re.IGNORECASE),
        re.compile(r'salaryName["\s:]+([^"]+)"', re.IGNORECASE),
    ],
    "html_tags": re.compile(r'<[^>]+>'),

    # 위치/주소
    "address_locality": re.compile(r'"addressLocality"\s*:\s*"([^"]+)"'),

    # 기업 규모
    "company_size": re.compile(r'(중소기업|중견기업|대기업|대기업\(계열사\)|스타트업|외국계|공기업|공공기관)'),

    # 고용형태
    "employment_type": re.compile(r'"employmentType"\s*:\s*"([^"]+)"'),
    "job_type_name": re.compile(r'"jobTypeName"\s*:\s*"([^"]+)"'),

    # 제목 토큰화
    "whitespace": re.compile(r'\s+'),
    "non_alphanumeric": re.compile(r'[^0-9a-zA-Z가-힣+#]'),

    # 마감일 패턴
    "deadline_patterns": [
        (re.compile(r'마감일\s*:\s*(\d{4}\.\d{2}\.\d{2})'), "date_dot"),
        (re.compile(r'"validThrough"\s*:\s*"?(\d{4}\.\d{2}\.\d{2})"?'), "date_dot"),
        (re.compile(r'"validThrough"\s*:\s*"([^"]+)"'), "date_iso"),
        (re.compile(r'"applicationEndAt"\s*:\s*"([^"]+)"'), "date_iso"),
    ],
    "ongoing_patterns": [
        (re.compile(r'상시\s*채용|상시채용', re.IGNORECASE), "ongoing"),
        (re.compile(r'채용\s*시\s*마감|채용시까지', re.IGNORECASE), "until_hired"),
    ],

    # 기술 스택 추출 (HARD_SKILL 타입)
    "skills": re.compile(r'\\?"name\\?":\\?"([^"\\]+)\\?",\\?"rank\\?":\d+,\\?"manualInput\\?":(true|false),\\?"skillTypeCode\\?":\\?"HARD_SKILL\\?"'),
}

# 제목 필터링용 불용어
_STOPWORDS = frozenset({
    "채용", "모집", "신입", "경력", "경력무관", "인턴", "정규직", "계약직",
    "수습", "모집중", "모집요강", "채용공고", "모집공고", "긴급", "급구",
    "우대", "가능", "담당", "업무", "직원", "구인", "사원", "신규", "전환",
    "잡코리아", "jobkorea"
})

# 고용형태 매핑
_EMPLOYMENT_TYPE_MAP = {
    "PERMANENT": "정규직",
    "CONTRACT": "계약직",
    "INTERN": "인턴",
    "PARTTIME": "파트타임",
    "DISPATCH": "파견직",
    "FREELANCE": "프리랜서",
}

_EMPLOYMENT_TYPES = ["정규직", "계약직", "인턴", "파트타임", "파견직", "프리랜서"]


class DetailPageParser:
    """잡코리아 상세 페이지 파서"""

    def __init__(self, company_normalizer: Optional[CompanyNormalizer] = None):
        """
        Args:
            company_normalizer: 회사명 정규화 객체 (None이면 새로 생성)
        """
        self.company_normalizer = company_normalizer or CompanyNormalizer()

    def parse(self, job_id: str, html: str) -> Dict:
        """
        상세 페이지 파싱

        Args:
            job_id: 공고 ID
            html: HTML 문자열

        Returns:
            파싱된 공고 데이터 딕셔너리
        """
        soup = BeautifulSoup(html, "lxml")

        # 개별 필드 파싱
        title = self._parse_title(html, soup)
        company_name = self._parse_company_name(html, soup)
        work_fields = self._parse_work_fields(html)
        skills = self._parse_skills(html)
        salary_data = self._parse_salary(html)
        company_address = self._parse_address(html)
        company_size = self._parse_company_size(html)
        employment_type = self._parse_employment_type(html)
        job_keywords = self._build_keywords(work_fields, title, skills)
        deadline_info = self._parse_deadline(html)

        # 정규화 처리
        primary_job_type = work_fields[0] if work_fields else ""
        normalized = normalize_job_type(primary_job_type) if primary_job_type else ""
        category = get_job_category(normalized) if normalized else "기타"
        mvp_category = get_mvp_category(category)
        location_info = normalize_location(company_address) if company_address else {}

        company_name_normalized, company_type = self.company_normalizer.normalize(company_name)

        now = datetime.now()

        return {
            "id": f"jk_{job_id}",
            "source": "jobkorea",
            "company_name_raw": company_name,
            "company_name": company_name_normalized,
            "company_type": company_type,
            "title": title,
            "url": CrawlerConfig.get_detail_url(job_id),
            "job_type": normalized or primary_job_type,
            "job_type_raw": ", ".join(work_fields[:3]),
            "job_category": category,
            "mvp_category": mvp_category,
            "job_keywords": job_keywords,  # skills + workFields + title 전부 포함
            "location_sido": location_info.get("sido", "서울"),
            "location_gugun": location_info.get("gugun", ""),
            "location_dong": location_info.get("dong", ""),
            "location_full": company_address or location_info.get("full", ""),
            "company_address": company_address,
            "salary_text": salary_data["text"],
            "salary_min": salary_data["min"],
            "salary_max": salary_data["max"],
            "salary_type": salary_data["type"],
            "company_size": company_size,
            "employment_type": employment_type,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "dedup_key": "",  # 나중에 계산
            **deadline_info,
        }

    def _parse_title(self, html: str, soup: BeautifulSoup) -> str:
        """제목 추출"""
        title = ""

        # 1. JSON-LD의 title 필드
        match = _PATTERNS["json_ld_title"].search(html)
        if not match:
            match = _PATTERNS["json_ld_title_fallback"].search(html)
        if match:
            title = match.group(1)

        # 2. CSS 셀렉터
        if not title:
            title_el = soup.select_one("h1.title, .tit_job, .job-title, .recruit-title")
            if title_el:
                title = title_el.get_text(strip=True)

        # 3. og:title 메타태그
        if not title:
            og_title = soup.select_one('meta[property="og:title"]')
            if og_title:
                title = og_title.get("content", "")

        # 4. <title> 태그 (최후 수단)
        if not title:
            match = _PATTERNS["html_title"].search(html)
            if match:
                raw_title = match.group(1).split(" - ")[0].split(" | ")[0].strip()
                # "XXX 채용" 패턴 필터링
                if not _PATTERNS["title_filter"].match(raw_title):
                    title = raw_title

        return title

    def _parse_company_name(self, html: str, soup: BeautifulSoup) -> str:
        """회사명 추출"""
        company_name = ""

        # 1. JSON-LD hiringOrganization.name
        match = _PATTERNS["hiring_org"].search(html)
        if match:
            company_name = match.group(1)

        # 2. CSS selector 폴백
        if not company_name:
            company_el = soup.select_one(".company-name, .coname, .co_name a")
            if company_el:
                company_name = company_el.get_text(strip=True)

        return company_name

    def _parse_work_fields(self, html: str) -> List[str]:
        """직무 필드 추출"""
        match = _PATTERNS["work_fields"].search(html)
        if not match:
            return []

        content = match.group(1)
        raw_fields = _PATTERNS["work_fields_values"].findall(content)
        return [f.rstrip('\\').strip() for f in raw_fields if f.strip()]

    def _parse_salary(self, html: str) -> Dict:
        """급여 정보 추출"""
        salary_text = ""

        for pattern in _PATTERNS["salary_patterns"]:
            match = pattern.search(html)
            if match:
                extracted = match.group(1).strip()
                extracted = _PATTERNS["html_tags"].sub('', extracted)
                if len(extracted) < 30:
                    salary_text = extracted
                    break

        return parse_salary(salary_text)

    def _parse_address(self, html: str) -> str:
        """회사 주소 추출"""
        match = _PATTERNS["address_locality"].search(html)
        if match:
            return match.group(1).strip()
        return ""

    def _parse_company_size(self, html: str) -> str:
        """기업 규모 추출"""
        match = _PATTERNS["company_size"].search(html)
        if match:
            return match.group(1)
        return ""

    def _parse_employment_type(self, html: str) -> str:
        """고용형태 추출"""
        employment_type = ""

        # 1. JSON에서 employmentType 추출
        match = _PATTERNS["employment_type"].search(html)
        if match:
            emp_code = match.group(1).upper()
            employment_type = _EMPLOYMENT_TYPE_MAP.get(emp_code, "")

        # 2. jobTypeName 폴백
        if not employment_type:
            match = _PATTERNS["job_type_name"].search(html)
            if match:
                employment_type = match.group(1)

        # 3. HTML 텍스트에서 직접 추출
        if not employment_type:
            for emp in _EMPLOYMENT_TYPES:
                if emp in html:
                    employment_type = emp
                    break

        return employment_type

    def _parse_skills(self, html: str) -> List[str]:
        """기술 스택 추출 (HARD_SKILL 타입)"""
        matches = _PATTERNS["skills"].findall(html)
        # matches는 (name, manualInput) 튜플 리스트
        skills = []
        seen = set()
        for match in matches:
            skill_name = match[0].strip()
            if skill_name and skill_name.lower() not in seen:
                skills.append(skill_name)
                seen.add(skill_name.lower())
        return skills

    def _build_keywords(self, work_fields: List[str], title: str, skills: List[str] = None) -> List[str]:
        """job_keywords 생성 (skills + work_fields + 제목 토큰)

        우선순위: skills(기술스택) > work_fields(직무분류) > title(제목토큰)
        """
        if skills is None:
            skills = []

        # 제목에서 토큰 추출
        title_tokens = []
        for raw_token in _PATTERNS["whitespace"].split(title):
            token = _PATTERNS["non_alphanumeric"].sub("", raw_token)
            if len(token) >= 2 and token.lower() not in _STOPWORDS:
                title_tokens.append(token)

        # skills + work_fields + 제목 토큰 병합 (중복 제거, skills 우선)
        job_keywords = []
        seen = set()

        # skills를 먼저 추가 (기술스택 우선)
        for skill in skills:
            kw = skill.strip()
            if not kw:
                continue
            kw_lower = kw.lower()
            if kw_lower not in seen:
                job_keywords.append(kw)
                seen.add(kw_lower)

        # work_fields + title_tokens 추가
        for keyword in work_fields + title_tokens:
            kw = keyword.strip()
            if not kw or kw.lower() in _STOPWORDS:
                continue
            kw_lower = kw.lower()
            if kw_lower not in seen:
                job_keywords.append(kw)
                seen.add(kw_lower)

        return job_keywords

    def _parse_deadline(self, html: str) -> Dict:
        """마감일 정보 추출"""
        result = {
            "deadline": "",
            "deadline_type": "unknown",
            "deadline_date": None,
        }

        # 1. 날짜 패턴 먼저 시도
        for pattern, dtype in _PATTERNS["deadline_patterns"]:
            match = pattern.search(html)
            if match:
                date_str = match.group(1).strip()
                try:
                    if dtype == "date_dot":
                        parsed = datetime.strptime(date_str, "%Y.%m.%d")
                        result["deadline"] = parsed.strftime("%m.%d")
                        result["deadline_date"] = parsed
                        result["deadline_type"] = "date"
                        return result
                    elif dtype == "date_iso":
                        if "T" in date_str:
                            parsed = datetime.fromisoformat(
                                date_str.replace("Z", "+00:00").split("+")[0]
                            )
                        elif "-" in date_str:
                            parsed = datetime.strptime(date_str[:10], "%Y-%m-%d")
                        else:
                            continue
                        result["deadline"] = parsed.strftime("%m.%d")
                        result["deadline_date"] = parsed
                        result["deadline_type"] = "date"
                        return result
                except (ValueError, TypeError):
                    pass

        # 2. 상시채용/채용시마감 패턴
        for pattern, dtype in _PATTERNS["ongoing_patterns"]:
            if pattern.search(html):
                if dtype == "ongoing":
                    result["deadline"] = "상시채용"
                    result["deadline_type"] = "ongoing"
                else:
                    result["deadline"] = "채용시 마감"
                    result["deadline_type"] = "until_hired"
                return result

        return result
