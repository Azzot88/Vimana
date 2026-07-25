// Scheme: 0.{phase_two_digits}.{last_completed_task}
// Examples: 0.01.6 → 0.01.12 → 0.02.1
// Update this after each completed task in TASKS.md
// Phase 2 fully closed (T2.1 – T2.4). Now on Phase 3.
// T_UX.4 fully closed (addresses + avatars + edit modal + landing on logo).
// T2.1 pt.3 closed — a Phase 2 leftover, but the version is a monotonic progress
// counter, so it keeps counting inside the current phase instead of going back.
// T3.6 closed — deal_events hash chain + Nostr anchoring.
// T3.7 closed — vault content chain (messages/files/seal) + verify_content.
// T3.8 closed — upload content validation (signatures + image decode).
export const APP_VERSION = '0.03.15'
