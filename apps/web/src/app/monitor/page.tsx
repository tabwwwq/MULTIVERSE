import type { Metadata } from "next";
import { realData } from "@/companies/real-data";
import { RunMonitor } from "@/components/monitor/run-monitor";
import { PageHeader } from "@/layouts/page-header";

export const metadata: Metadata = { title: "Simulation Monitor" };

export default function MonitorPage() {
  const names = Object.fromEntries(
    (realData()?.index.companies ?? []).map((row) => [String(Number(row.cik)), row.name]),
  );
  return (
    <>
      <PageHeader
        title="Simulation Monitor"
        summary="Every run of this computer as it goes: queued, running, paused, finished or stopped. The worker owns the runs, so closing this page changes nothing."
      />
      <RunMonitor names={names} />
    </>
  );
}
