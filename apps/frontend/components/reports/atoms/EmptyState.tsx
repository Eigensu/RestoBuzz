export function EmptyState({
  icon: Icon,
  message,
}: {
  readonly icon: React.ElementType;
  readonly message: string;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-16 flex flex-col items-center gap-4 text-center">
      <div className="p-4 bg-[#eff2f0] rounded-2xl">
        <Icon className="w-8 h-8 text-[#24422e]/50" />
      </div>
      <p className="text-sm text-gray-400 font-medium max-w-xs">{message}</p>
    </div>
  );
}
