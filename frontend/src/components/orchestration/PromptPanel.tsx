import { useState, type FormEvent } from "react";
import { useAddRunPrompt } from "../../api/useRuns";
import { Button } from "../ui/Button";

/** Adds another prompt to an existing run: the agents run again, seeing the decisions the run has
 * already made, and the run gains an iteration rather than starting over. */
export function PromptPanel({ runId }: { runId: string }) {
  const [objective, setObjective] = useState("");
  const addPrompt = useAddRunPrompt(runId);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!objective.trim()) return;
    addPrompt.mutate(objective, { onSuccess: () => setObjective("") });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-sm" data-testid="prompt-panel">
      <label
        htmlFor="follow-up-prompt"
        className="label text-muted"
      >
        Follow-up prompt
      </label>
      <p className="text-sm text-muted">
        Runs the agents again inside this run. They see the decisions made so far, so a follow-up
        builds on them instead of repeating them.
      </p>
      <textarea
        id="follow-up-prompt"
        value={objective}
        onChange={(event) => setObjective(event.target.value)}
        rows={3}
        className="border border-line-strong bg-canvas p-sm text-base text-ink focus:border-accent focus:outline-none"
        placeholder="Now protect load factor on the thin routes"
      />
      <Button type="submit" disabled={addPrompt.isPending || !objective.trim()} className="self-start">
        {addPrompt.isPending ? "Running…" : "Add prompt"}
      </Button>
      {addPrompt.isError && (
        <span role="alert" className="text-xs text-bad">
          {addPrompt.error?.message ?? "Request failed"}
        </span>
      )}
    </form>
  );
}
