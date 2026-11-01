import AcadSync from "../ui";
import { notFound } from "next/navigation";
export default async function Page({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  if (
    !["dashboard", "review", "calendar", "sources", "settings"].includes(
      section,
    )
  )
    notFound();
  return <AcadSync initial={section} />;
}
