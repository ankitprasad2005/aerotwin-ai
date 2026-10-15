import { useEffect, useMemo, useState } from "react";
import { useDecisionWeights, useSaveDecisionWeights } from "../api/useDecisionWeights";
import { BreakdownBars } from "../components/charts/BreakdownBars";
import { WeightGroup } from "../components/weights/WeightGroup";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel } from "../components/ui/Panel";
import { ErrorState, LoadingState } from "../components/ui/States";
import type { DecisionWeights, WeightAgent, WeightFactor } from "../types/api";
import { formatDateTime } from "../utils/format";
import {
  AGENT_KEYS,
  DEFAULT_WEIGHTS,
  FACTOR_HELP,
  FACTOR_KEYS,
  FACTOR_LABELS,
  normalizeGroup,
  toWeightsPayload,
  validateWeights,
  weightsEqual,
} from "../utils/weights";

const FACTOR_ROWS = FACTOR_KEYS.map((key) => ({ key, label: FACTOR_LABELS[key], help: FACTOR_HELP[key] }));
const AGENT_ROWS = AGENT_KEYS.map((key) => ({ key, label: key.charAt(0) + key.slice(1).toLowerCase() }));

function NumberField({
  id,
  label,
  value,
  onChange,
  help,
  step = 1,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
  help: string;
  step?: number;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="label text-muted">
        {label}
      </label>
      <input
        id={id}
        type="number"
        step={step}
        value={Number.isFinite(value) ? value : ""}
        onChange={(event) => onChange(event.target.value === "" ? Number.NaN : Number(event.target.value))}
        className="field w-40 font-mono"
        aria-describedby={`${id}-help`}
      />
      <span id={`${id}-help`} className="max-w-xs text-xs text-muted">
        {help}
      </span>
    </div>
  );
}

function ThresholdPreview({ review, recommend }: { review: number; recommend: number }) {
  const valid = Number.isFinite(review) && Number.isFinite(recommend) && review >= 0 && recommend <= 100 && review < recommend;
  if (!valid) {
    return <p className="text-xs text-muted">Fix the thresholds to preview the score zones.</p>;
  }
  return (
    <div data-testid="threshold-preview" role="img" aria-label={`Reject below ${review}, review from ${review}, recommend from ${recommend}`}>
      <div className="flex h-3 overflow-hidden rounded-sm">
        <div className="bg-bad/70" style={{ width: `${review}%` }} />
        <div className="bg-warn/70" style={{ width: `${recommend - review}%` }} />
        <div className="bg-ok/70" style={{ width: `${100 - recommend}%` }} />
      </div>
      <div className="mt-1 flex justify-between font-mono text-2xs text-muted">
        <span>0</span>
        <span>{review}</span>
        <span>{recommend}</span>
        <span>100</span>
      </div>
      <p className="mt-1 text-xs text-muted">
        Red: reject. Amber: needs review. Green: recommend. Any blocking conflict rejects regardless of score.
      </p>
    </div>
  );
}

export function WeightsPage() {
  const { data: saved, isLoading, isError, error, refetch } = useDecisionWeights();
  const save = useSaveDecisionWeights();
  const [draft, setDraft] = useState<DecisionWeights | null>(null);
  const [justSaved, setJustSaved] = useState(false);

  // Seed the draft from the server once, and again whenever the saved version changes (a save, or
  // another tab's save) provided the user has no unsaved edits to lose.
  useEffect(() => {
    if (!saved) return;
    setDraft((current) => (current === null || weightsEqual(current, saved) ? toWeightsPayload(saved) : current));
  }, [saved]);

  const errors = useMemo(() => (draft ? validateWeights(draft) : []), [draft]);
  const dirty = draft !== null && saved !== undefined && !weightsEqual(draft, saved);

  if (isLoading) {
    return (
      <div data-testid="page-content">
        <LoadingState label="Loading weights…" />
      </div>
    );
  }
  if (isError || !saved || !draft) {
    return (
      <div data-testid="page-content" className="max-w-xl">
        <ErrorState title="Could not load the decision weights" error={error} onRetry={() => void refetch()} />
      </div>
    );
  }

  function update(change: (current: DecisionWeights) => DecisionWeights) {
    setJustSaved(false);
    save.reset();
    setDraft((current) => (current ? change(current) : current));
  }

  const factorShares = normalizeGroup(draft.factors);

  return (
    <div data-testid="page-content" className="max-w-6xl">
      <PageHeader
        title="Decision weights"
        subtitle="How the decision engine turns the five agents' outputs into a 0-100 score. Weights are relative: only their ratios matter, and each group is normalised before use. Changes apply to new runs."
        actions={
          saved.updated_at ? <span className="text-xs text-muted">Last saved {formatDateTime(saved.updated_at)}</span> : null
        }
      />
      <div className="grid gap-3 lg:grid-cols-2">
        <WeightGroup<WeightFactor>
          title="Score factors"
          description="How much each factor contributes to the score."
          rows={FACTOR_ROWS}
          values={draft.factors}
          onChange={(key, value) => update((current) => ({ ...current, factors: { ...current.factors, [key]: value } }))}
        />
        <WeightGroup<WeightAgent>
          title="Agent confidence"
          description="How much each agent's stated confidence counts towards the confidence factor."
          rows={AGENT_ROWS}
          values={draft.agent_confidence}
          onChange={(key, value) =>
            update((current) => ({ ...current, agent_confidence: { ...current.agent_confidence, [key]: value } }))
          }
        />

        <Panel title="Verdict thresholds">
          <div className="flex flex-wrap gap-4">
            <NumberField
              id="recommend-threshold"
              label="Recommend at or above"
              value={draft.thresholds.recommend}
              onChange={(value) => update((current) => ({ ...current, thresholds: { ...current.thresholds, recommend: value } }))}
              help="Scores from here up are recommended (0-100)."
            />
            <NumberField
              id="review-threshold"
              label="Review at or above"
              value={draft.thresholds.review}
              onChange={(value) => update((current) => ({ ...current, thresholds: { ...current.thresholds, review: value } }))}
              help="Scores from here up to the recommend threshold need review; below it is rejected."
            />
            <NumberField
              id="profit-scale"
              label="Profit scale (USD / week)"
              value={draft.profit_scale_usd}
              step={500}
              onChange={(value) => update((current) => ({ ...current, profit_scale_usd: value }))}
              help="A weekly profit of this size scores about 0.73 on the profit factor; zero profit scores 0.5."
            />
          </div>
          <div className="mt-3">
            <ThresholdPreview review={draft.thresholds.review} recommend={draft.thresholds.recommend} />
          </div>
        </Panel>

        <Panel title="Preview: share of the score per factor">
          <BreakdownBars
            label="Normalised factor weights"
            items={FACTOR_KEYS.map((key) => ({
              key,
              label: FACTOR_LABELS[key],
              fraction: factorShares[key],
              detail: `${Math.round(factorShares[key] * 100)}%`,
              hint: FACTOR_HELP[key],
            }))}
          />
          <p className="mt-2 text-xs text-muted">A factor valued 100% adds its share of the 100 points; the score is the sum.</p>
        </Panel>
      </div>

      {errors.length > 0 && (
        <div role="alert" className="mt-3 rounded-sm border border-bad/40 bg-bad/5 px-3 py-2 text-sm" data-testid="weights-errors">
          <div className="font-medium text-bad">These weights cannot be saved yet</div>
          <ul className="mt-1 list-disc pl-4 text-ink">
            {errors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </div>
      )}
      {save.isError && (
        <div role="alert" className="mt-3 rounded-sm border border-bad/40 bg-bad/5 px-3 py-2 text-sm text-bad" data-testid="weights-server-error">
          The server rejected the weights: {save.error.message}
        </div>
      )}
      {justSaved && !dirty && (
        <div role="status" className="mt-3 rounded-sm border border-ok/40 bg-ok/5 px-3 py-2 text-sm text-ok">
          Weights saved. New runs will use them.
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          disabled={!dirty || errors.length > 0 || save.isPending}
          onClick={() =>
            save.mutate(draft, {
              onSuccess: () => setJustSaved(true),
            })
          }
        >
          {save.isPending ? "Saving…" : "Save weights"}
        </Button>
        <Button variant="ghost" disabled={!dirty} onClick={() => update(() => toWeightsPayload(saved))}>
          Discard changes
        </Button>
        <Button
          variant="ghost"
          disabled={weightsEqual(draft, DEFAULT_WEIGHTS)}
          onClick={() => update(() => toWeightsPayload(DEFAULT_WEIGHTS))}
        >
          Reset to defaults
        </Button>
        {dirty && <span className="text-xs text-warn">Unsaved changes</span>}
      </div>
    </div>
  );
}
