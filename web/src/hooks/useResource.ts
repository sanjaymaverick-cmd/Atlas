import { useCallback, useEffect, useState } from "react";

import { ApiError, request } from "../api/client";

interface ResourceState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
}

/**
 * Load one GET endpoint, with the loading and error handling every list needs.
 *
 * `path` is null when the scope is incomplete — no legal entity chosen yet, for
 * instance — which means "do not fetch", as distinct from "fetch and fail".
 */
export function useResource<T>(path: string | null): ResourceState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async () => {
    if (path === null) {
      setData(null);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setData(await request<T>(path));
    } catch (caught) {
      setData(null);
      if (caught instanceof ApiError) {
        setError(
          caught.status === 403
            ? "This session is not scoped to read that."
            : `${caught.code}: ${caught.message}`,
        );
      } else {
        setError("Could not load.");
      }
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload };
}
