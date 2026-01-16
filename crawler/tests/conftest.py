"""
pytest fixtures for crawler tests
"""
import pytest
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_job_data():
    """Sample job data for testing"""
    return {
        "id": "jk_12345678",
        "source": "jobkorea",
        "company_name": "테스트회사",
        "company_name_raw": "(주)테스트회사",
        "company_type": "주식회사",
        "title": "백엔드 개발자 채용",
        "url": "https://www.jobkorea.co.kr/Recruit/GI_Read/12345678",
        "job_type": "백엔드 개발",
        "job_type_raw": "백엔드, 서버 개발",
        "job_category": "IT/개발",
        "mvp_category": "개발",
        "job_keywords": ["백엔드", "Python", "FastAPI"],
        "location_sido": "서울",
        "location_gugun": "강남구",
        "location_dong": "역삼동",
        "location_full": "서울특별시 강남구 역삼동",
        "company_address": "서울특별시 강남구 역삼동 123-45",
        "salary_text": "연봉 5000~7000만원",
        "salary_min": 5000,
        "salary_max": 7000,
        "salary_type": "연봉",
        "company_size": "중소기업",
        "employment_type": "정규직",
        "is_active": True,
        "deadline": "03.31",
        "deadline_type": "date",
    }


@pytest.fixture
def sample_html_content():
    """Sample HTML content for parser testing"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>백엔드 개발자 - 테스트회사</title>
        <meta property="og:title" content="백엔드 개발자 채용" />
    </head>
    <body>
        <script type="application/ld+json">
        {
            "@type": "JobPosting",
            "title": "백엔드 개발자 채용",
            "hiringOrganization": {
                "name": "(주)테스트회사"
            },
            "addressLocality": "서울특별시 강남구 역삼동",
            "employmentType": "PERMANENT",
            "validThrough": "2026-03-31"
        }
        </script>
        <h1 class="title">백엔드 개발자 채용</h1>
        <div class="company-name">(주)테스트회사</div>
    </body>
    </html>
    '''


@pytest.fixture
def mock_firestore_client(mocker):
    """Mock Firestore client for unit tests"""
    mock_client = mocker.MagicMock()
    mocker.patch('app.db.firestore.get_db', return_value=mock_client)
    return mock_client
