"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { buttonVariants } from "@/components/ui/button";
import { mediaRefUrl } from "@/lib/domains/math-notes";

/**
 * Notebook-photo thumbnails for a note. Clicking a thumbnail opens it large in
 * a dialog with a download button. Both the preview and the download go
 * through the BFF (`mediaRefUrl` → `/api/media/download`), so they stay
 * same-origin.
 */
export function NotePhotos({ refs }: { refs: string[] }) {
  const [active, setActive] = useState<number | null>(null);
  const activeRef = active !== null ? refs[active] : null;

  return (
    <>
      <div className="flex flex-wrap gap-2 pt-1">
        {refs.map((ref, i) => (
          <button
            key={ref}
            type="button"
            onClick={() => setActive(i)}
            aria-label={`Open photo ${i + 1}`}
            className="overflow-hidden rounded-md border transition-transform hover:-translate-y-0.5 hover:shadow-e2"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={mediaRefUrl(ref)}
              alt={`notebook photo ${i + 1}`}
              className="size-28 object-cover"
            />
          </button>
        ))}
      </div>

      <Dialog open={activeRef !== null} onOpenChange={(o) => !o && setActive(null)}>
        {activeRef && (
          <DialogContent className="max-w-[min(92vw,900px)] gap-3 p-3">
            <DialogTitle className="text-xs font-medium text-muted-foreground">
              Photo {(active ?? 0) + 1} of {refs.length}
            </DialogTitle>
            <div className="flex max-h-[78vh] justify-center overflow-auto">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={mediaRefUrl(activeRef)}
                alt={`notebook photo ${(active ?? 0) + 1}`}
                className="h-auto max-w-full rounded-md object-contain"
              />
            </div>
            <div className="flex justify-end">
              <a
                href={mediaRefUrl(activeRef)}
                download
                className={buttonVariants({ variant: "tonal", size: "sm" })}
              >
                <Download /> Download
              </a>
            </div>
          </DialogContent>
        )}
      </Dialog>
    </>
  );
}
