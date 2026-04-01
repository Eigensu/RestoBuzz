interface CategoryBadgeProps {
  category: string;
}

export function CategoryBadge({ category }: Readonly<CategoryBadgeProps>) {
  const isUtility = category === "UTILITY";
  return (
    <span
      className={`text-[10px] font-bold px-2.5 py-1 rounded-full tracking-wider ${
        isUtility ? "bg-blue-50 text-blue-600" : "bg-purple-50 text-purple-600"
      }`}
    >
      {category}
    </span>
  );
}
