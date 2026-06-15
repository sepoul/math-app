"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import {
  AlertCircle,
  Check,
  ChevronRight,
  Clock,
  Loader2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  getAllActiveJobs,
  clearAllActiveJobs,
  type ActiveJobEntry,
  type ActiveJobType,
} from "@/lib/platform";

const POLL_MS = 2000;
const DONE_DISPLAY_MS = 5000;

const JOB_LABELS: Record<ActiveJobType, string> = {
  math_qa: "Math Q&A",
  math_conversation: "Math Conversation",
};

const JOB_LINKS: Record<ActiveJobType, (entry: ActiveJobEntry) => string> = {
  math_qa: (e) => (e.entityId ? `/math-qa/${e.entityId}` : "/"),
  math_conversation: (e) => (e.entityId ? `/math-conversation/${e.entityId}` : "/"),
};

interface DoneEntry {
  jobType: ActiveJobType;
  label: string;
  link: string;
  expiresAt: number;
}

export function GlobalJobIndicator() {
  const [allJobs, setAllJobs] = useState<ActiveJobEntry[]>([]);
  const [doneList, setDoneList] = useState<DoneEntry[]>([]);
  const [open, setOpen] = useState(false);
  const prevKeys = useRef<Set<string>>(new Set());

  const tick = useCallback(() => {
    const jobs = getAllActiveJobs();
    const currentKeys = new Set(jobs.map((j) => `${j.jobType}::${j.entityId ?? ""}`));
    const now = Date.now();
    const newDone: DoneEntry[] = [];

    for (const key of prevKeys.current) {
      if (!currentKeys.has(key)) {
        const [jobType, entityId] = key.split("::") as [ActiveJobType, string | undefined];
        const fakeEntry = { jobType, entityId } as ActiveJobEntry;
        newDone.push({
          jobType,
          label: JOB_LABELS[jobType] ?? jobType,
          link: JOB_LINKS[jobType]?.(fakeEntry) ?? "/",
          expiresAt: now + DONE_DISPLAY_MS,
        });
      }
    }

    prevKeys.current = currentKeys;
    setAllJobs(jobs);

    if (newDone.length > 0) {
      setDoneList((prev) => [...prev.filter((d) => d.expiresAt > now), ...newDone]);
      setOpen(true);
    } else {
      setDoneList((prev) => {
        const filtered = prev.filter((d) => d.expiresAt > now);
        return filtered.length === prev.length ? prev : filtered;
      });
    }
  }, []);

  useEffect(() => {
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => clearInterval(id);
  }, [tick]);

  const handleDebugClear = useCallback(() => {
    if (process.env.NODE_ENV === "production") return;
    if (!window.confirm("Debug: clear local active jobs?")) return;
    clearAllActiveJobs();
    prevKeys.current = new Set();
    setDoneList([]);
    setAllJobs([]);
  }, []);

  const running = allJobs.filter((j) => j.status !== "waiting_input");
  const waiting = allJobs.filter((j) => j.status === "waiting_input");
  const runningCount = running.length;
  const waitingCount = waiting.length;
  const count = allJobs.length;
  const hasDone = doneList.length > 0;
  const hasAnything = count > 0 || hasDone;

  // Accent colour for the rail by state.
  const railTone =
    runningCount > 0
      ? "border-primary text-primary"
      : waitingCount > 0
        ? "border-warning text-warning"
        : hasDone
          ? "border-success text-success"
          : "border-border text-muted-foreground";

  return (
    <>
      {/* Edge rail toggle */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close job panel" : "Open job panel"}
        className={cn(
          "fixed right-0 top-1/2 z-50 flex -translate-y-1/2 flex-col items-center gap-2 rounded-l-2xl border border-r-0 bg-card px-2.5 py-4 shadow-e3 transition-all hover:px-3",
          railTone
        )}
      >
        {runningCount > 0 ? (
          <span className="relative flex size-3.5">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex size-3.5 rounded-full bg-primary" />
          </span>
        ) : waitingCount > 0 ? (
          <AlertCircle className="size-4 text-warning" />
        ) : hasDone ? (
          <span className="flex size-3.5 rounded-full bg-success" />
        ) : (
          <Clock className="size-4 text-muted-foreground" />
        )}
        <span
          className="text-[11px] font-bold tracking-widest"
          style={{ writingMode: "vertical-rl", letterSpacing: "0.12em" }}
        >
          {runningCount > 0
            ? `${runningCount} JOB${runningCount > 1 ? "S" : ""}`
            : waitingCount > 0
              ? "REVIEW"
              : hasDone
                ? "DONE"
                : "JOBS"}
        </span>
      </button>

      {/* Slide-out panel */}
      <div
        className="fixed right-0 top-0 z-40 flex h-full w-72 flex-col border-l border-border bg-card shadow-e4 transition-transform duration-200 ease-in-out"
        style={{ transform: open ? "translateX(0)" : "translateX(100%)" }}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="font-heading text-sm font-semibold text-foreground">Jobs</h2>
          <div className="flex items-center gap-1">
            {process.env.NODE_ENV !== "production" && (
              <Button
                variant="ghost"
                size="xs"
                onClick={handleDebugClear}
                title="Debug: clear local active jobs"
              >
                Clear local
              </Button>
            )}
            <Button variant="ghost" size="icon-sm" onClick={() => setOpen(false)} aria-label="Close">
              <X />
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {!hasAnything && (
            <div className="flex h-full flex-col items-center justify-center px-4 text-center">
              <div className="mb-3 flex size-11 items-center justify-center rounded-full bg-accent">
                <Clock className="size-5 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">No jobs running</p>
              <p className="mt-1 text-xs text-muted-foreground/70">
                Submit a math question to get started.
              </p>
            </div>
          )}

          {runningCount > 0 && (
            <JobGroup label="Running">
              {running.map((job) => (
                <JobRow
                  key={`run-${job.jobType}::${job.entityId ?? ""}`}
                  href={JOB_LINKS[job.jobType]?.(job) ?? "/"}
                  onClick={() => setOpen(false)}
                  icon={<Loader2 className="size-4 shrink-0 animate-spin text-primary" />}
                  title={JOB_LABELS[job.jobType]}
                  subtitle={`Started ${formatAge(job.timestamp)}`}
                />
              ))}
            </JobGroup>
          )}

          {waitingCount > 0 && (
            <JobGroup label="Needs your review" tone="text-warning">
              {waiting.map((job) => (
                <JobRow
                  key={`wait-${job.jobType}::${job.entityId ?? ""}`}
                  href={JOB_LINKS[job.jobType]?.(job) ?? "/"}
                  onClick={() => setOpen(false)}
                  icon={<AlertCircle className="size-4 shrink-0 text-warning" />}
                  title={JOB_LABELS[job.jobType]}
                  subtitle="Awaiting your input"
                  titleClassName="text-warning"
                />
              ))}
            </JobGroup>
          )}

          {hasDone && (
            <JobGroup label="Just finished">
              {doneList.map((d, i) => (
                <JobRow
                  key={`done-${d.jobType}-${i}`}
                  href={d.link}
                  onClick={() => setOpen(false)}
                  icon={
                    <span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-success/20">
                      <Check className="size-2.5 text-success" />
                    </span>
                  }
                  title={`${d.label} completed`}
                  titleClassName="text-success"
                />
              ))}
            </JobGroup>
          )}
        </div>
      </div>
    </>
  );
}

function JobGroup({
  label,
  tone = "text-muted-foreground",
  children,
}: {
  label: string;
  tone?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="px-3 pt-3 pb-1">
      <p className={cn("mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider", tone)}>
        {label}
      </p>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function JobRow({
  href,
  onClick,
  icon,
  title,
  subtitle,
  titleClassName,
}: {
  href: string;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  titleClassName?: string;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className="group flex items-center gap-2.5 rounded-xl px-2.5 py-2 transition-colors hover:bg-accent"
    >
      {icon}
      <div className="min-w-0 flex-1">
        <p className={cn("truncate text-xs font-medium text-foreground", titleClassName)}>
          {title}
        </p>
        {subtitle && <p className="text-[10px] text-muted-foreground">{subtitle}</p>}
      </div>
      <ChevronRight className="size-3.5 shrink-0 text-muted-foreground/40" />
    </Link>
  );
}

function formatAge(timestamp: number): string {
  const sec = Math.floor((Date.now() - timestamp) / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  return `${Math.floor(min / 60)}h ago`;
}
