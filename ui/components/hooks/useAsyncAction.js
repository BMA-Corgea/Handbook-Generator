// ui/components/hooks/useAsyncAction.js
const { useCallback, useState } = React;

export default function useAsyncAction(asyncFn) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = useCallback(
    async (...args) => {
      setLoading(true);
      setError("");
      try {
        return await asyncFn(...args);
      } catch (e) {
        const msg = e?.message || String(e);
        setError(msg);
        throw e;
      } finally {
        setLoading(false);
      }
    },
    [asyncFn]
  );

  return { run, loading, error, setError };
}
