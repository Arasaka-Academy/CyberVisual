export function NotificationToast({ notice, error }: { notice: string; error: string | null }) {
  if (!notice && !error) return null;

  return (
    <div className={`toast ${error ? "error" : "success"}`} role="status">
      {error || notice}
    </div>
  );
}
