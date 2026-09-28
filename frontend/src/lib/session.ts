// Session management — the JWT rides an httpOnly cookie set by the backend.
// beginSession/endSession own the react-query cache so a sign-out never leaks the
// previous account's data into the next login.

import { useQuery } from "@tanstack/react-query";
import { apiGet, apiPost } from "./api";
import type { User } from "./types";

export async function beginSession() {
  await queryClient.invalidateQueries({ queryKey: ["me"] });
}

export async function endSession() {
  try {
    await apiPost("/auth/logout");
  } finally {
    queryClient.clear();
  }
}

export function useSession() {
  const q = useQuery<User | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await apiGet<User>("/auth/me");
      } catch (e) {
        const status = (e as { status?: number }).status;
        if (status === 401) return null;
        throw e;
      }
    },
    retry: false,
    staleTime: 60_000,
  });
  return {
    user: q.data ?? null,
    loading: q.isLoading,
    error: q.error,
    refetch: q.refetch,
  };
}

// Imported last to avoid a cycle with queryClient at module init in some bundlers.
import { queryClient } from "./queryClient";
