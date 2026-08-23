import DisplayPrefsSection from '../components/DisplayPrefsSection'

/**
 * T_UX.20 — «Регион и форматы».
 *
 * Open and named in TASKS: `carriage_rules` travels here inside
 * `DisplayPrefsSection`, and it is not a display preference — it is the
 * carrier's standing terms, copied into every trip (T_UX.15). The component was
 * not split for this task: it has one save path, and dividing that in passing
 * is a separate edit with its own diff.
 */
export default function ProfilePrefsPage() {
  return (
    <div className="space-y-4">
      <DisplayPrefsSection />
    </div>
  )
}
