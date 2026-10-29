"use client";

import type { DecisionType } from "@multiverse/contracts/interventions";
import { DecisionBuilder } from "@/components/decisions/decision-builder";
import { Alert } from "@/components/ui/alert";
import type { CompanyContext } from "@/decisions/context";
import { scenarioFormFromDraft } from "@/decisions/form";
import { findRevision, findScenario } from "@/notebook/model";
import { useNotebook } from "@/notebook/use-notebook";

interface RestoreGateProps {
  context: CompanyContext;
  initialAsOf: string;
  initialType: DecisionType;
  restore: { scenarioId: string; revision: number };
}

/*
 * Opens a saved revision in the Decision Builder ("restore form"). The notebook lives in
 * this browser only, so the revision is looked up once the page runs on the device.
 */
export function RestoreGate({ context, initialAsOf, initialType, restore }: RestoreGateProps) {
  const notebook = useNotebook();
  if (!notebook.ready) {
    return <p className="text-body text-ink-muted">Reading the saved revision on this device…</p>;
  }
  const record = findScenario(notebook.notebook, restore.scenarioId);
  const revision = findRevision(notebook.notebook, {
    scenario_id: restore.scenarioId,
    revision: restore.revision,
  });
  let problem: string | null = null;
  if (!record || !revision) {
    problem =
      "This saved revision is not on this device. The notebook is stored per browser; the form starts from the documented defaults.";
  } else if (revision.draft.company_id !== context.companyId) {
    problem =
      "This saved revision is for another company. The form starts from the documented defaults.";
  } else if (!context.cutoffs.some((facts) => facts.asOf === revision.draft.as_of)) {
    problem = `The cutoff ${revision.draft.as_of} of this revision is not available for this company. The form starts from the documented defaults.`;
  }
  if (problem || !record || !revision) {
    return (
      <div className="flex flex-col gap-6">
        <Alert tone="warning" title="Saved revision not opened">
          {problem}
        </Alert>
        <DecisionBuilder context={context} initialAsOf={initialAsOf} initialType={initialType} />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      <Alert tone="info" title={`Opened revision ${revision.revision} of “${record.name}”`}>
        Saving creates revision {record.revisions.length + 1}; revision {revision.revision} stays as
        it is.
      </Alert>
      <DecisionBuilder
        key={`${record.scenario_id}-${revision.revision}`}
        context={context}
        initialAsOf={revision.draft.as_of}
        initialType={revision.draft.decision.type}
        restored={{
          form: scenarioFormFromDraft(revision.draft),
          scenarioId: record.scenario_id,
          revision: revision.revision,
          name: record.name,
        }}
      />
    </div>
  );
}
