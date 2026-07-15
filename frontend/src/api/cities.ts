import api from './client'

export interface City {
  geoname_id: number
  name: string
  country_iso: string
  population: number
}

export const searchCities = (params: { q: string; country?: string; limit?: number }) =>
  api.get<City[]>('/api/cities', { params })
