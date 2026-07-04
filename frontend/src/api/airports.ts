import api from './client'

export interface Airport {
  iata: string
  city: string
  country: string
  lat: number
  lon: number
}

export const searchAirports = (q: string) =>
  api.get<Airport[]>('/api/airports', { params: { q } })

export const nearestAirports = (lat: number, lon: number, limit = 5) =>
  api.get<Airport[]>('/api/airports/nearest', { params: { lat, lon, limit } })
