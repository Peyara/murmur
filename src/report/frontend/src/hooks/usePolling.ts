/** React Query hooks with 15-minute polling — matches Murmur's scoring window. */

import { useQuery } from '@tanstack/react-query'
import { fetchPulse, fetchZones, fetchTimeline } from '../api/client'

const POLL_INTERVAL = 15 * 60 * 1000 // 15 minutes

export function usePulse(window?: string) {
  return useQuery({
    queryKey: ['pulse', window],
    queryFn: () => fetchPulse(window),
    refetchInterval: window ? false : POLL_INTERVAL,
    staleTime: 0, // always refetch when window changes — prevents flash of cached attack data
  })
}

export function useZones(window?: string) {
  return useQuery({
    queryKey: ['zones', window],
    queryFn: () => fetchZones(window),
    refetchInterval: window ? false : POLL_INTERVAL,
    staleTime: 0,
  })
}

export function useTimeline(hours = 24, actor?: string) {
  return useQuery({
    queryKey: ['timeline', hours, actor],
    queryFn: () => fetchTimeline(hours, actor),
    refetchInterval: POLL_INTERVAL,
  })
}
