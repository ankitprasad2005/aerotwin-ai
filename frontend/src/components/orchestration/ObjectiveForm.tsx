import { useState, type FormEvent } from "react";
import { useCreateRun } from "../../api/useRuns";
import { Button } from "../ui/Button";

export function ObjectiveForm({ onRunCreated }: { onRunCreated: (runId: string) => void }) {
  const [objective, setObjective] = useState("");
  const createRun = useCreateRun();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!objective.trim()) return;
    createRun.mutate(objective, {
      onSuccess: (run) => {
        setObjective("");
        onRunCreated(run.id);
      },
    });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-sm">
      <label className="font-mono text-[11px] uppercase tracking-[0.08em] text-text-secondary" htmlFor="objective">
        Objective
      </label>
      <textarea
        id="objective"
        value={objective}
        onChange={(event) => setObjective(event.target.value)}
        rows={2}
        className="border border-border-visible bg-black p-sm font-body text-body text-text-primary focus:border-accent focus:outline-none"
        placeholder="Improve airline profitability while maintaining passenger capacity"
      />
      <Button type="submit" disabled={createRun.isPending || !objective.trim()} className="self-start">
        {createRun.isPending ? "[RUNNING...]" : "RUN ORCHESTRATION"}
      </Button>
      {createRun.isError && (
        <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-accent">
          [ERROR: {createRun.error?.message ?? "request failed"}]
        </span>
      )}
    </form>
  );
}
