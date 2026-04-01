interface StatusBadgeProps {
  status: string;
}

export function StatusBadge({ status }: Readonly<StatusBadgeProps>) {
  const approved = status === "APPROVED";
  return (
    <span
      className={`text-[10px] font-bold px-2.5 py-1 rounded-full shrink-0 tracking-wider ${
        approved ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"
      }`}
    >
      {status}
    </span>
  );
}
