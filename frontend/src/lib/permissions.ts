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
  // T3.42 — renamed with the endpoint it guards: the power is offering *any*
  // role, and the old name described one role and one verb.
  ROLE_OFFER: 'role:offer',
  RULES_EDIT: 'rules:edit',
  RULES_PUBLISH: 'rules:publish',
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
  compliance_editor: [Permission.RULES_EDIT],
  superuser: Object.values(Permission),
}

/** T3.42 — the one reader of `user.roles` on this side.
 *
 *  Every screen used to compare a single string, and there were about twenty of
 *  them. With roles adding up, each of those comparisons had to become a
 *  membership test, and twenty hand-written `.includes()` calls are twenty
 *  chances to test the wrong string — silently, because a wrong role name
 *  simply never matches and the section quietly never appears.
 */
export function hasRole(
  user: User | null | undefined,
  role: UserRole,
): boolean {
  return !!user?.roles?.includes(role)
}

export function isSuperuser(user: User | null | undefined): boolean {
  return hasRole(user, 'superuser')
}

/** Arbiter powers, which the superuser also holds. Named separately because
 *  "can act on disputes" is the question the screens actually ask. */
export function isArbiter(user: User | null | undefined): boolean {
  return hasRole(user, 'arbiter') || isSuperuser(user)
}

export function permsOf(user: User | null | undefined): Set<Permission> {
  if (!user) return new Set()
  // The union over every role held — mirrors `core/permissions.perms_of`.
  const perms = new Set<Permission>()
  for (const role of user.roles ?? []) {
    for (const p of ROLE_PERMS[role] ?? []) perms.add(p)
  }
  if (user.can_carry) perms.add(Permission.TRIP_PUBLISH)
  if (user.can_send) perms.add(Permission.ORDER_CREATE)
  return perms
}

export function hasPerm(user: User | null | undefined, perm: Permission): boolean {
  return permsOf(user).has(perm)
}
