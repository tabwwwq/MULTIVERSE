import type { InterventionSpec, ParameterSpec, ValueRange } from "@multiverse/contracts";
import type { Metadata } from "next";
import Link from "next/link";
import { DataTable } from "@/components/ui/data-table";
import { CATALOG, formatMagnitude } from "@/decisions/catalog";
import { formatValue } from "@/decisions/units";
import { PageHeader, Section } from "@/layouts/page-header";

export const metadata: Metadata = { title: "Assumption Matrix" };

/*
 * The documented defaults of every decision type (PRD FR-DE-07), read from the same
 * catalog the form and the contracts use. Nothing here is estimated from data.
 */

const SOURCE_LABELS = {
  accounting_rule: "Accounting rule",
  statutory_rate: "Statutory rate",
  design_default: "Design default",
  placeholder: "Placeholder, not an estimate",
} as const;

interface Row {
  key: string;
  parameter: string;
  allowed: string;
  planning: string;
  default: string;
  source: string;
}

function range(value: ValueRange | null, format: (v: string) => string): string {
  return value ? `${format(value.min)} to ${format(value.max)}` : "No limit beyond allowed";
}

function defaultOf(parameter: ParameterSpec): string {
  const format = (v: string) => formatValue(v, parameter.unit);
  const value = parameter.default;
  if (typeof value === "string") return format(value);
  if (value.shape === "fixed") return format(value.value);
  if (value.shape === "uniform") return `Uniform ${format(value.low)} to ${format(value.high)}`;
  return `Triangular ${format(value.low)}, ${format(value.mode)}, ${format(value.high)}`;
}

function parameterRow(parameter: ParameterSpec): Row {
  const format = (v: string) => formatValue(v, parameter.unit);
  return {
    key: parameter.key,
    parameter: parameter.label,
    allowed: range(parameter.allowed, format),
    planning: range(parameter.planning, format),
    default: defaultOf(parameter),
    source: `${SOURCE_LABELS[parameter.default_source.kind]}. ${parameter.default_source.note}`,
  };
}

function rows(spec: InterventionSpec): Row[] {
  const magnitude: Row[] = spec.magnitude.units.map((unit) => {
    const format = (v: string) => formatMagnitude(v, unit);
    return {
      key: `magnitude-${unit.unit}`,
      parameter: `${spec.magnitude.label} (${unit.label})`,
      allowed: range(unit.allowed, format),
      planning: range(unit.planning, format),
      default:
        spec.magnitude.default_unit === null
          ? `${format(unit.default_value)}; the unit must be chosen`
          : format(unit.default_value),
      source: `${SOURCE_LABELS[spec.magnitude.default_source.kind]}. ${spec.magnitude.default_source.note}`,
    };
  });
  const shares: Row[] = spec.share_group
    ? [
        {
          key: spec.share_group.key,
          parameter: `${spec.share_group.label} shares`,
          allowed: "0% to 100% each, exactly 100% in total",
          planning: "None",
          default: spec.share_group.members
            .map(
              (member, index) =>
                `${member.label} ${formatValue(spec.share_group?.defaults[index] ?? "0", "fraction")}`,
            )
            .join(", "),
          source: `${SOURCE_LABELS[spec.share_group.default_source.kind]}. ${spec.share_group.default_source.note}`,
        },
      ]
    : [];
  return [
    ...magnitude,
    parameterRow(spec.lag_quarters),
    parameterRow(spec.ramp_quarters),
    ...spec.parameters.map(parameterRow),
    ...shares,
  ];
}

const COLUMNS = [
  { key: "parameter", header: "Parameter", rowHeader: true },
  { key: "allowed", header: "Allowed" },
  { key: "planning", header: "Planning range" },
  { key: "default", header: "Default" },
  { key: "source", header: "Source of the default" },
] as const;

export default function AssumptionsPage() {
  return (
    <>
      <PageHeader
        title="Assumption Matrix"
        summary="Every parameter of every decision type: what it means, the values it may take, its default and where that default comes from."
      />
      <div className="max-w-prose text-body text-ink-muted">
        <p>
          Values outside the allowed range are rejected. Values outside the planning range are
          accepted with an out-of-distribution warning. {CATALOG.planning_range_note}
        </p>
        <p className="mt-3">
          Build a decision with these defaults in the{" "}
          <Link href="/decisions" className="text-mint underline underline-offset-4">
            Decision Builder
          </Link>
          .
        </p>
      </div>
      {CATALOG.interventions.map((spec) => (
        <Section key={spec.type} id={spec.type} title={spec.label} intro={spec.summary}>
          <DataTable
            id={`assumptions-${spec.type}`}
            caption={`${spec.label}: parameters, ranges and defaults`}
            columns={COLUMNS}
            rows={rows(spec)}
            rowKey={(row) => row.key}
          />
        </Section>
      ))}
    </>
  );
}
