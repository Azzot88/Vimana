import api from './client'

/** T3.12.03 pt.2 — a description of cargo a sender keeps for the next trip.
 *
 *  Copied into the response form as a snapshot, and from the form into the
 *  cargo: the cargo never points back at the template, so editing one later
 *  changes nothing already in a deal. Several per person, each named.
 */
export interface CargoTemplate {
  id: string
  name: string
  category: string | null
  declared_value: number | null
  description: string | null
  /** T3.12.04 — the rest of what the response form asks. No photograph: a
   *  picture is of one parcel, not of a kind of one. */
  weight_kg: number | null
  dimensions_cm: number[] | null
  fragile: boolean
  open_on_handover: boolean
  cargo_url: string | null
  created_at: string
  updated_at: string
}

export interface CargoTemplateInput {
  name: string
  category?: string | null
  declared_value?: number | null
  description?: string | null
  weight_kg?: number | null
  dimensions_cm?: number[] | null
  fragile?: boolean
  open_on_handover?: boolean
  cargo_url?: string | null
}

export const listCargoTemplates = () =>
  api.get<CargoTemplate[]>('/api/me/cargo-templates')

export const createCargoTemplate = (data: CargoTemplateInput) =>
  api.post<CargoTemplate>('/api/me/cargo-templates', data)

export const updateCargoTemplate = (id: string, patch: Partial<CargoTemplateInput>) =>
  api.patch<CargoTemplate>(`/api/me/cargo-templates/${id}`, patch)

export const deleteCargoTemplate = (id: string) =>
  api.delete<void>(`/api/me/cargo-templates/${id}`)
