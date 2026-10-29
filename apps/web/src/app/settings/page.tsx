import type { Metadata } from "next";
import { PrivacySettings } from "@/components/notebook/privacy-settings";
import { PageHeader } from "@/layouts/page-header";

export const metadata: Metadata = { title: "Settings & Privacy" };

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        title="Settings & Privacy"
        summary="What this prototype keeps in your browser, and how to delete all of it."
      />
      <PrivacySettings />
    </>
  );
}
