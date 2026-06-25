/**
 * Note flairs — structured learner directives that steer the synthesis.
 *
 * The selectable keys mirror the backend `NoteFlair` enum (so they validate on
 * submit); the directive *text* each key maps to lives in the prompt registry
 * (`math_notes.flair.<key>`, editable via `aiplatform deploy-prompts`). The
 * `label`/`description` here are UI affordances for the picker.
 */
export const NOTE_FLAIRS = [
  {
    key: "dont_spoil",
    label: "Don't spoil",
    description:
      "You're mid-exercise — keep the cleaned-up notes, but don't finish or reveal anything you left unfinished.",
  },
] as const;

export type NoteFlairKey = (typeof NOTE_FLAIRS)[number]["key"];
