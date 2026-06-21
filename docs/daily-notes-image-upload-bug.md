# Daily Notes — iPhone large-photo upload fix

> Tracked bug + final solution. Companion to memory
> `daily-notes-image-upload-bug`. Separate from the extract→synthesize redesign
> (`docs/daily-notes-redesign.md`) but on the same capture surface.

## Problem

On iPhone/Safari the capture form uploads **full-resolution** notebook photos
(~3MB+ each) straight to `POST /media`. Several photos per note × multi-MB each
→ slow, janky uploads and occasional failures on the exact device students use
most. This kills usability in production.

**Where (no size reduction anywhere on the path):**
- `math-ui/app/math-notes/page.tsx` — `onPickPhotos` collects raw `File`
  objects; `onSave` loops `notesClient.uploadMedia(photos[i])`.
- `math-ui/lib/domains/math-notes/client.ts` — `uploadMedia` POSTs the raw blob
  to `/api/media` → platform `POST /media`.

## Final solution — client-side downscale before upload (no new deps)

Shrink each picked photo in the browser so only a small JPEG
(~200–500 KB) ever leaves the device. Pure client-side; no platform/BFF change,
no new npm dependency (uses canvas).

1. **New util** `math-ui/lib/domains/math-notes/image.ts`:
   `downscaleImage(file, { maxDim = 2000, quality = 0.82 }): Promise<File>`
   - decode via `createImageBitmap(file, { imageOrientation: "from-image" })`
     (respects EXIF rotation → no sideways photos);
   - if `max(w, h) <= maxDim` and the file is already small, return it unchanged;
   - else draw scaled onto a canvas, export `canvas.toBlob("image/jpeg",
     quality)`, wrap as a new `File("<name>.jpg")`;
   - wrap in `try/catch` → on **any** failure return the original file (never
     block capture).
2. **Wire it in `onPickPhotos`** (compress on selection): map picked files
   through `downscaleImage` before `setPhotos` / `setPhotoUrls`, so previews
   *and* uploads use the shrunk version and the big 3 MB `File` is released
   early. Keep the existing `accept="image/*"` / `capture="environment"` inputs.

Result: a 3 MB HEIC/JPEG → a ~2000px JPEG of a few hundred KB; multi-photo notes
upload fast and reliably on mobile.

**Edge cases:**
- **HEIC:** through `<input accept="image/*">` Safari generally hands back a
  decodable JPEG; `createImageBitmap` covers common formats, and the
  fallback-to-original keeps anything unusual working.
- **Orientation:** `imageOrientation: "from-image"` avoids rotated uploads.
- **Optional later:** add a server-side max-bytes guardrail too, but the
  client downscale is the usability fix.

## Verify
On a real iPhone: take a notebook photo and save a note → the `/api/media`
request payload is a few hundred KB (not multi-MB), the preview and stored image
render correctly and right-side-up, and a 3–4 photo note uploads quickly.
