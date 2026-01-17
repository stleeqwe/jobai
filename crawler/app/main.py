"""크롤러 메인 모듈

실제 크롤링은 run_crawler.py 사용:
    python run_crawler.py                 # 전체 크롤링
    python run_crawler.py --skip-existing # 증분 크롤링

이 모듈은 패키지 import 용도로만 유지됩니다.
"""

import sys
import os

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    """CLI 진입점 - run_crawler.py로 리다이렉트"""
    print("=" * 60)
    print("안내: 크롤링은 run_crawler.py를 사용하세요.")
    print()
    print("사용법:")
    print("  python run_crawler.py                 # 전체 크롤링")
    print("  python run_crawler.py --skip-existing # 증분 크롤링")
    print("  python run_crawler.py --list-only     # 목록만 수집")
    print("=" * 60)


if __name__ == "__main__":
    main()
