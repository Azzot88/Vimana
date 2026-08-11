// Scheme: 0.{phase}.{part of that phase}
//
//   0    — beta. Stays 0 until every phase is closed; then Alpha 1 ships.
//   03   — the phase, two digits with a leading zero.
//   7    — which part of it, i.e. phase 3.7. A whole phase reads .0 (4 → 0.04.0).
//
// So the version answers "where in the roadmap is this build", not "how many
// tasks got done". It moves when a phase does — rarely, and meaningfully.
//
// Earlier this counted closed tasks (0.03.22 after T3.15) and drifted from the
// documented rule, so a reader could not tell what the number meant. Owner's
// decision 2026-07-30: the number tracks the phase.
export const APP_VERSION = '0.03.8'
