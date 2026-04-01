interface EmptyStateProps {
  icon: React.ElementType;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: Readonly<EmptyStateProps>) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-20 h-20 bg-[#eff2f0] rounded-3xl flex items-center justify-center mb-6 shadow-sm">
        <Icon className="w-10 h-10 text-[#24422e]" />
      </div>
      <h2 className="text-xl font-black text-gray-900 tracking-tight">
        {title}
      </h2>
      {description && (
        <p className="text-sm text-gray-500 mt-2 font-medium max-w-sm">
          {description}
        </p>
      )}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
