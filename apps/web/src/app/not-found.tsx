import { ButtonLink } from "@/components/ui/button";
import { PageHeader } from "@/layouts/page-header";

export default function NotFound() {
  return (
    <>
      <PageHeader
        title="This page does not exist"
        summary="The address may be mistyped, or the page was moved. Every section of MULTIVERSE is listed in the navigation."
      />
      <ButtonLink href="/">Go to the overview</ButtonLink>
    </>
  );
}
