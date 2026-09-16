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
        className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary"
      >
        Follow-up prompt
      </label>
      <p className="text-body-sm text-text-secondary">
        Runs the agents again inside this run. They see the decisions made so far, so a follow-up
        builds on them instead of repeating them.
      </p>
      <textarea
        id="follow-up-prompt"
        value={objective}
        onChange={(event) => setObjective(event.target.value)}
        rows={3}
        className="border border-border-visible bg-black p-sm font-body text-body text-text-primary focus:border-accent focus:outline-none"
        placeholder="Now protect load factor on the thin routes"
      />
      <Button type="submit" disabled={addPrompt.isPending || !objective.trim()} className="self-start">
        {addPrompt.isPending ? "[RUNNING...]" : "ADD PROMPT"}
      </Button>
      {addPrompt.isError && (
        <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-accent">
          [ERROR: {addPrompt.error?.message ?? "request failed"}]
        </span>
      )}
    </form>
  );
}
