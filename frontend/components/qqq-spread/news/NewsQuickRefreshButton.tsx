"use client";

type Props = {
  onRefresh: () => void;
  loading: boolean;
  disabled?: boolean;
};

export default function NewsQuickRefreshButton({ onRefresh, loading, disabled = false }: Props) {
  return (
    <button
      type="button"
      className="qqq-btn qqq-btn-primary ni-refresh-btn"
      onClick={onRefresh}
      disabled={loading || disabled}
    >
      {loading ? (
        <>
          <span className="ni-spinner" aria-hidden />
          Refreshing…
        </>
      ) : (
        "Quick Refresh"
      )}
    </button>
  );
}
