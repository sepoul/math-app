import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { cn } from "@/lib/utils";
import { COMPONENTS } from "./markdown";

/**
 * Markdown renderer with KaTeX math, for content that mixes real Markdown
 * structure (headings, bold, lists) with `$...$` inline / `$$...$$` display
 * math — i.e. `daily_note.synthesis.markdown`. `remark-math` lexes the
 * dollar delimiters and `rehype-katex` renders them; `remark-gfm` covers
 * tables/task-lists. No `dangerouslySetInnerHTML` — react-markdown owns the
 * DOM and KaTeX output is sanitised by the rehype pipeline.
 *
 * Reuses the Tailwind component map from `<Markdown>` so typography matches
 * the rest of the app. The KaTeX stylesheet is imported here once (bundled
 * per the import graph; importing the same module elsewhere dedupes).
 *
 * `<Latex>` is still the right tool for unvalidated, prose-with-math strings
 * that are NOT Markdown (conversation turns, latex playground); this is for
 * full Markdown documents.
 */
export function MarkdownMath({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  return (
    <div className={cn("[&>*:first-child]:mt-0", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkMath, remarkGfm]}
        rehypePlugins={[rehypeKatex]}
        components={COMPONENTS}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
