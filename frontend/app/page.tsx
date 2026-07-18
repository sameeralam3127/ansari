async function getBackendHealth(): Promise<{ status: string; environment: string } | null> {
  const apiUrl = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  try {
    const res = await fetch(`${apiUrl}/health`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as { status: string; environment: string };
  } catch {
    return null;
  }
}

export default async function Home() {
  const health = await getBackendHealth();

  return (
    <div className="flex flex-1 items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex w-full max-w-lg flex-col gap-6 px-8 py-16">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-zinc-500">ANSARI</p>
          <h1 className="text-2xl font-semibold text-zinc-950 dark:text-zinc-50">Admin</h1>
        </div>

        <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
          <p className="mb-1 text-sm text-zinc-500">Backend status</p>
          {health ? (
            <p className="text-base text-emerald-600 dark:text-emerald-400">
              {health.status} · {health.environment}
            </p>
          ) : (
            <p className="text-base text-red-600 dark:text-red-400">unreachable</p>
          )}
        </div>

        <p className="text-sm text-zinc-500">
          Document upload, widget configuration, and conversation logs land in M1–M4.
        </p>
      </main>
    </div>
  );
}
