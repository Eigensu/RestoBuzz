import { api } from "./api";
import type { Restaurant } from "@/types";

export async function getRestaurants(): Promise<Restaurant[]> {
  const response = await api.get("/restaurants/");
  return response.data;
}
