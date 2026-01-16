"""크롤러 커스텀 예외 모듈"""


class CrawlerError(Exception):
    """크롤러 기본 예외"""
    pass


class BlockedError(CrawlerError):
    """차단 감지 예외 (캡차, IP 차단 등)"""
    pass


class RateLimitError(CrawlerError):
    """레이트 리밋 초과 예외 (429)"""
    pass


class ParseError(CrawlerError):
    """파싱 실패 예외"""
    pass


class SessionError(CrawlerError):
    """세션/쿠키 관련 예외"""
    pass


class ProxyError(CrawlerError):
    """프록시 관련 예외"""
    pass
