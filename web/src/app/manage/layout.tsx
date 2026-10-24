import { Suspense } from "react";

export default function ManageLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <Suspense fallback={<main className="manage-shell manage-loading" />}>
      {children}
    </Suspense>
  );
}
