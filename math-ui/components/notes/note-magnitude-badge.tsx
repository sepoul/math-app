import { Clock, FileText, Gauge } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type {
  DensityTier,
  NoteSynthesis,
  NoteMagnitude,
} from "@/lib/domains/math-notes";

const DEPTH_LABEL: Record<DensityTier, string> = {
  brief: "brief",
  standard: "standard",
  deep: "deep",
};

/** Audio duration → a compact human string (notes live in the 2–7 min band). */
function formatAudioDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

/**
 * A small "how substantial was this session" badge for a daily note, built
 * from the enriched synthesis (epic #14): the depth tier the synthesis rendered
 * at and the number of topical sections — e.g. "deep · 3 topics" — plus the
 * persisted study-scope proxies from `NoteMagnitude` (page count, audio length).
 *
 * Graceful fallback: a flat / old note (no `depth_tier`, no `sections`, no
 * `magnitude`) yields nothing to show, so the badge renders `null` and the note
 * looks exactly as it did before the enrichment.
 *
 * The learner's *stated* study scope (`study_scope_hint`, e.g. "~5h studied")
 * is NOT shown: it lives on the in-flight `SynthesisPlan`, which is not
 * persisted on the artifact. `page_count` is the persisted scope proxy.
 */
export function MagnitudeBadge({
  synthesis,
  magnitude,
}: {
  synthesis: NoteSynthesis | null;
  magnitude: NoteMagnitude | null;
}) {
  const depth: DensityTier | null =
    synthesis?.depth_tier ?? magnitude?.density_tier ?? null;
  const topicCount = synthesis?.sections?.length ?? 0;
  const pageCount = magnitude?.page_count ?? 0;
  const durationSeconds = magnitude?.duration_seconds ?? null;

  // Nothing measured → render nothing (no regression for flat/old notes).
  if (!depth && topicCount === 0 && pageCount === 0 && durationSeconds == null) {
    return null;
  }

  // "deep · 3 topics" — depth first, topic count when the note is sectioned.
  const summaryParts: string[] = [];
  if (depth) summaryParts.push(DEPTH_LABEL[depth]);
  if (topicCount > 0) {
    summaryParts.push(`${topicCount} ${topicCount === 1 ? "topic" : "topics"}`);
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {summaryParts.length > 0 && (
        <Badge variant="outline">
          <Gauge />
          {summaryParts.join(" · ")}
        </Badge>
      )}
      {pageCount > 0 && (
        <Badge variant="ghost" className="text-muted-foreground">
          <FileText />
          {pageCount} {pageCount === 1 ? "page" : "pages"}
        </Badge>
      )}
      {durationSeconds != null && (
        <Badge variant="ghost" className="text-muted-foreground">
          <Clock />
          {formatAudioDuration(durationSeconds)}
        </Badge>
      )}
    </div>
  );
}
