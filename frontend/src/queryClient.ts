// Shared React Query client. Server state lives here now — screens and
// hooks subscribe via src/hooks/queries.ts instead of hand caches.
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      gcTime: 10 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
