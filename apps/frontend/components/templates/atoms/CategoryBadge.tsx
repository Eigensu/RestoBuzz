interface CategoryBadgeProps {
  category: string;
}

export function CategoryBadge({ category }: Readonly<CategoryBadgeProps>) {
  const isUtility = category === "UTILITY";
  return (
    <span
      className={`text-[10px] font-black px-2.5 py-1 rounded-full uppercase tracking-widest ${
        isUtility ? "bg-blue-50 text-blue-600" : "bg-[#eff2f0] text-[#24422e]"
      }`}
    >
      {category}
    </span>
  );
}
