import api from './client'

export interface Airport {
  iata: string
  city: string
  country: string
  country_iso: string
  lat: number
  lon: number
}

export interface CountryCount {
  iso: string
  count: number
}

export interface CityCount {
  city: string
  count: number
}

export const searchAirports = (q: string) =>
  api.get<Airport[]>('/api/airports', { params: { q } })

export const nearestAirports = (lat: number, lon: number, limit = 5) =>
  api.get<Airport[]>('/api/airports/nearest', { params: { lat, lon, limit } })

export const listCountries = () =>
  api.get<CountryCount[]>('/api/airports/countries')

export const listCitiesInCountry = (countryIso: string) =>
  api.get<CityCount[]>('/api/airports/cities', { params: { country: countryIso } })

export const airportsInCity = (countryIso: string, city: string) =>
  api.get<Airport[]>('/api/airports/by-city', { params: { country: countryIso, city } })
