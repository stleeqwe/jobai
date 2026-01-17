import { useState, useEffect, useCallback, useRef } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export interface Coordinates {
  latitude: number
  longitude: number
}

export interface GeolocationState {
  coordinates: Coordinates | null
  address: string | null
  loading: boolean
  error: string | null
  permission: 'granted' | 'denied' | 'prompt' | 'unknown'
}

export function useGeolocation() {
  const [state, setState] = useState<GeolocationState>({
    coordinates: null,
    address: null,
    loading: true,
    error: null,
    permission: 'unknown'
  })

  const watchIdRef = useRef<number | null>(null)

  // 좌표 -> 주소 변환 (역지오코딩)
  const reverseGeocode = useCallback(async (coords: Coordinates): Promise<string | null> => {
    try {
      const response = await fetch(
        `${API_BASE}/geocode/reverse?lat=${coords.latitude}&lng=${coords.longitude}`
      )
      if (response.ok) {
        const data = await response.json()
        return data.address || null
      }
    } catch {
      console.warn('역지오코딩 실패')
    }
    return null
  }, [])

  // 위치 업데이트 핸들러
  const handlePositionUpdate = useCallback(async (position: GeolocationPosition) => {
    const coords: Coordinates = {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude
    }

    // 역지오코딩으로 주소 가져오기
    const address = await reverseGeocode(coords)

    setState({
      coordinates: coords,
      address,
      loading: false,
      error: null,
      permission: 'granted'
    })
  }, [reverseGeocode])

  // 위치 에러 핸들러
  const handlePositionError = useCallback((error: GeolocationPositionError) => {
    let errorMessage = '위치를 가져올 수 없습니다.'
    let permission: GeolocationState['permission'] = 'unknown'

    switch (error.code) {
      case error.PERMISSION_DENIED:
        // 시스템 위치 서비스 비활성화 또는 브라우저 권한 거부
        errorMessage = '위치 권한이 필요합니다. 시스템 설정 > 개인정보 보호 > 위치 서비스에서 브라우저를 허용해주세요.'
        permission = 'denied'
        console.warn('[Geolocation] PERMISSION_DENIED - 시스템 위치 서비스 또는 브라우저 권한 확인 필요')
        break
      case error.POSITION_UNAVAILABLE:
        errorMessage = '위치 정보를 사용할 수 없습니다.'
        console.warn('[Geolocation] POSITION_UNAVAILABLE')
        break
      case error.TIMEOUT:
        errorMessage = '위치 요청 시간이 초과되었습니다.'
        console.warn('[Geolocation] TIMEOUT')
        break
    }

    setState(prev => ({
      ...prev,
      loading: false,
      error: errorMessage,
      permission
    }))
  }, [])

  // 위치 감시 시작
  const startWatching = useCallback(() => {
    if (!navigator.geolocation) {
      setState(prev => ({
        ...prev,
        loading: false,
        error: '이 브라우저에서는 위치 서비스를 지원하지 않습니다.'
      }))
      return
    }

    setState(prev => ({ ...prev, loading: true, error: null }))

    // 기존 watch 정리
    if (watchIdRef.current !== null) {
      navigator.geolocation.clearWatch(watchIdRef.current)
    }

    // watchPosition으로 변경 - 권한 승인 시 자동으로 콜백 호출됨
    watchIdRef.current = navigator.geolocation.watchPosition(
      handlePositionUpdate,
      handlePositionError,
      {
        enableHighAccuracy: true,
        timeout: 15000,
        maximumAge: 60000 // 1분 캐시
      }
    )
  }, [handlePositionUpdate, handlePositionError])

  // 컴포넌트 마운트 시 위치 감시 시작
  useEffect(() => {
    startWatching()

    // 클린업: 언마운트 시 watch 정리
    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current)
      }
    }
  }, [startWatching])

  // 위치 새로고침
  const refreshLocation = useCallback(() => {
    startWatching()
  }, [startWatching])

  // 위치 초기화
  const clearLocation = useCallback(() => {
    if (watchIdRef.current !== null) {
      navigator.geolocation.clearWatch(watchIdRef.current)
      watchIdRef.current = null
    }
    setState(prev => ({
      ...prev,
      coordinates: null,
      address: null,
      error: null
    }))
  }, [])

  return {
    ...state,
    refreshLocation,
    clearLocation,
    hasLocation: state.coordinates !== null
  }
}
