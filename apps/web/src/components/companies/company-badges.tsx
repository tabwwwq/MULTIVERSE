import type { Company, SupportStatus } from "@multiverse/contracts";
import { Ban, CircleCheck, Clock, FlaskConical, LogOut } from "lucide-react";
import { STATUS_LABELS, SUPPORT_LABELS } from "@/companies/labels";
import { Badge, type BadgeTone } from "@/components/ui/badge";

const SUPPORT: Record<SupportStatus, { tone: BadgeTone; icon: typeof CircleCheck }> = {
  supported: { tone: "mint", icon: CircleCheck },
  insufficient_history: { tone: "warning", icon: Clock },
  unsupported: { tone: "negative", icon: Ban },
};

export function SupportBadge({ status }: { status: SupportStatus }) {
  const { tone, icon } = SUPPORT[status];
  return (
    <Badge tone={tone} icon={icon}>
      {SUPPORT_LABELS[status]}
    </Badge>
  );
}

/** Only companies that left the market get a badge; active is the default. */
export function LifecycleBadge({ company }: { company: Company }) {
  if (company.status === "active") return null;
  return (
    <Badge tone="neutral" icon={LogOut}>
      {STATUS_LABELS[company.status]}
      {company.status_date ? ` on ${company.status_date}` : null}
    </Badge>
  );
}

export function SyntheticBadge() {
  return (
    <Badge tone="warning" icon={FlaskConical}>
      Synthetic
    </Badge>
  );
}
