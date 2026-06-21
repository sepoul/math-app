You are reading a photo of a page of handwritten mathematics study notes. Return ONLY a JSON object (no prose, no markdown fences) with these keys:
  "text": a faithful plain-text transcription of the page,
  "latex": the mathematical content as LaTeX (empty string if none),
  "diagram_description": a short description of any diagram or figure on the page (empty string if none),
  "concepts": an array of the mathematical concepts the page touches (e.g. ["tangent space", "smooth atlas"]).
If the page is unreadable, return the object with empty values.
