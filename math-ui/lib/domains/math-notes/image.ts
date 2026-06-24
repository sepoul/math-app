/**
 * Client-side image downscale for the capture path.
 *
 * iPhone/Safari hands back full-resolution notebook photos (~3 MB+); shrinking
 * each in the browser *before* upload means only a few-hundred-KB JPEG ever
 * leaves the device, so multi-photo notes upload fast and reliably on mobile.
 * Pure client-side — no platform/BFF change and no new dependency (canvas).
 * See docs/daily-notes-image-upload-bug.md.
 */

export interface DownscaleOptions {
  /** Longest-edge cap in px. Larger images are scaled down to this. */
  maxDim?: number;
  /** JPEG quality for the re-encode (0–1). */
  quality?: number;
}

// Below this, a re-encode rarely pays for itself — keep the original bytes.
const SMALL_ENOUGH_BYTES = 600_000;

/**
 * Return a downscaled JPEG `File` for `file`, or the original unchanged.
 *
 * - Decodes via `createImageBitmap(file, { imageOrientation: "from-image" })`
 *   so EXIF rotation is baked in (no sideways uploads).
 * - If the image already fits `maxDim` and is already small, returns it as-is.
 * - Otherwise draws it scaled onto a canvas and re-encodes as JPEG, keeping
 *   whichever of {original, re-encoded} is smaller.
 * - Never throws: on ANY failure (unsupported format, no canvas, decode error)
 *   it returns the original file, so capture is never blocked.
 */
export async function downscaleImage(
  file: File,
  { maxDim = 2000, quality = 0.82 }: DownscaleOptions = {}
): Promise<File> {
  try {
    // Non-images (shouldn't happen via accept="image/*") pass through untouched.
    if (!file.type.startsWith("image/")) return file;

    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const { width, height } = bitmap;
    const longest = Math.max(width, height);

    // Already within bounds and already small → nothing to gain.
    if (longest <= maxDim && file.size <= SMALL_ENOUGH_BYTES) {
      bitmap.close();
      return file;
    }

    const scale = longest > maxDim ? maxDim / longest : 1;
    const w = Math.round(width * scale);
    const h = Math.round(height * scale);

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      bitmap.close();
      return file;
    }
    ctx.drawImage(bitmap, 0, 0, w, h);
    bitmap.close();

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", quality)
    );
    // If the re-encode didn't actually help (e.g. a small PNG), keep the original.
    if (!blob || blob.size >= file.size) return file;

    const name = file.name.replace(/\.[^./\\]+$/, "") + ".jpg";
    return new File([blob], name, { type: "image/jpeg", lastModified: Date.now() });
  } catch {
    return file;
  }
}
