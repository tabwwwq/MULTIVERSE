"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { REVIEWS_KEY, parseReviews, withReview, type LocalReview } from "@/events/registry";
import { downloadText } from "@/lib/download";

const CONTROL =
  "min-h-10 rounded-control border border-line-strong bg-canvas px-3 text-small text-ink";

function stored(): LocalReview[] {
  try {
    return parseReviews(window.localStorage.getItem(REVIEWS_KEY));
  } catch {
    return [];
  }
}

/*
 * A second reader's verdict. It stays in this browser until it is downloaded and merged into
 * the registry with `python -m multiverse_pipelines.events reviews --file <path>`.
 */
export function ReviewForm({ eventId }: { eventId: string }) {
  const [reviews, setReviews] = useState<LocalReview[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const first = window.setTimeout(() => setReviews(stored()), 0);
    return () => window.clearTimeout(first);
  }, []);

  function submit(form: FormEvent<HTMLFormElement>) {
    form.preventDefault();
    const data = new FormData(form.currentTarget);
    const notes = String(data.get("notes") ?? "").trim();
    const next = withReview(reviews, {
      event_id: eventId,
      reviewer: String(data.get("reviewer") ?? "owner"),
      decision: String(data.get("decision")) as LocalReview["decision"],
      confidence: String(data.get("confidence")) as LocalReview["confidence"],
      notes: notes === "" ? null : notes,
      reviewed_at: new Date().toISOString(),
    });
    try {
      window.localStorage.setItem(REVIEWS_KEY, JSON.stringify(next));
    } catch {
      // Without storage the review still counts for this visit.
    }
    setReviews(next);
    setSaved(true);
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 rounded-panel border border-line p-4">
      <h3 className="font-medium text-ink">Your review</h3>
      <p className="text-small text-ink-muted">
        Read the filing, then record what you found. Reviews stay in this browser until you download
        them.
      </p>
      <div className="grid gap-3 md:grid-cols-3">
        <label className="flex flex-col gap-1 text-small text-ink">
          Reviewer
          <input
            name="reviewer"
            required
            pattern="[a-z][a-z0-9_]*"
            defaultValue="owner"
            className={CONTROL}
          />
        </label>
        <label className="flex flex-col gap-1 text-small text-ink">
          Decision
          <select name="decision" defaultValue="confirmed" className={CONTROL}>
            <option value="confirmed">Confirmed</option>
            <option value="corrected">Corrected</option>
            <option value="rejected">Rejected</option>
            <option value="unsure">Unsure</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-small text-ink">
          Confidence
          <select name="confidence" defaultValue="medium" className={CONTROL}>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </label>
      </div>
      <label className="flex flex-col gap-1 text-small text-ink">
        Notes
        <textarea name="notes" rows={2} maxLength={400} className={CONTROL} />
      </label>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm">
          Save review
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={reviews.length === 0}
          onClick={() =>
            downloadText(
              "event-reviews.json",
              `${JSON.stringify(reviews, null, 2)}\n`,
              "application/json",
            )
          }
        >
          Download {reviews.length} reviews
        </Button>
      </div>
      {saved ? (
        <Alert tone="success" title="Saved in this browser" live>
          Download the reviews to add them to the registry.
        </Alert>
      ) : null}
    </form>
  );
}
