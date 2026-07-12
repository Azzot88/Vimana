import type { User, UserRole } from '../api/auth'

// Mirror of backend app/core/permissions.py — keep in sync when adding perms.
export const Permission = {
  TRIP_PUBLISH: 'trip:publish',
  ORDER_CREATE: 'order:create',
  DISPUTE_CLAIM: 'dispute:claim',
  DISPUTE_RESOLVE: 'dispute:resolve',
  VAULT_READ_AS_ARBITER: 'vault:read_as_arbiter',
  DISPUTE_LIST_ADMIN: 'dispute:list_admin',
  USERS_MANAGE: 'users:manage',
  ARBITER_ASSIGN: 'arbiter:assign',
} as const

export type Permission = (typeof Permission)[keyof typeof Permission]

const ARBITER_PERMS: readonly Permission[] = [
  Permission.DISPUTE_CLAIM,
  Permission.DISPUTE_RESOLVE,
  Permission.VAULT_READ_AS_ARBITER,
  Permission.DISPUTE_LIST_ADMIN,
]

const ROLE_PERMS: Record<UserRole, readonly Permission[]> = {
  user: [],
  arbiter: ARBITER_PERMS,
  superuser: Object.values(Permission),
}

export function permsOf(user: User | null | undefined): Set<Permission> {
  if (!user) return new Set()
  const perms = new Set<Permission>(ROLE_PERMS[user.role] ?? [])
  if (user.can_carry) perms.add(Permission.TRIP_PUBLISH)
  if (user.can_send) perms.add(Permission.ORDER_CREATE)
  return perms
}

export function hasPerm(user: User | null | undefined, perm: Permission): boolean {
  return permsOf(user).has(perm)
}
