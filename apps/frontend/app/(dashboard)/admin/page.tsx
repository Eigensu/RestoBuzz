"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Shield, UserPlus } from "lucide-react";
import { api } from "@/lib/api";
import { parseApiError } from "@/lib/errors";
import { toast } from "sonner";
import { useAuthStore } from "@/store/auth";
import { getRestaurants } from "@/lib/restaurants";
import type { Restaurant } from "@/types";

type AdminUser = {
  id: string;
  email: string;
  role: "super_admin" | "admin" | "viewer";
  first_name?: string | null;
  last_name?: string | null;
  phone?: string | null;
  is_active: boolean;
  created_at: string;
};

type RestaurantUserRole = {
  user_id: string;
  restaurant_id: string;
  role: "admin" | "viewer";
};

const INPUT_CLS =
  "w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]";

export default function AdminPage() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [selectedRestaurantByUser, setSelectedRestaurantByUser] = useState<
    Record<string, string>
  >({});

  const isSuperAdmin = user?.role === "super_admin";

  const { data: admins = [], isLoading } = useQuery<AdminUser[]>({
    queryKey: ["admin-users"],
    queryFn: () => api.get("/admin/users").then((r) => r.data),
    enabled: isSuperAdmin,
  });

  const { data: restaurants = [] } = useQuery<Restaurant[]>({
    queryKey: ["admin-restaurants"],
    queryFn: getRestaurants,
    enabled: isSuperAdmin,
  });

  const { data: assignmentsByUser = {}, isLoading: loadingAssignments } =
    useQuery<Record<string, Restaurant[]>>({
      queryKey: [
        "admin-user-restaurant-links",
        restaurants.map((r) => r.id).sort(),
      ],
      enabled: isSuperAdmin && restaurants.length > 0,
      queryFn: async () => {
        const results = await Promise.all(
          restaurants.map(async (restaurant) => {
            const { data } = await api.get<RestaurantUserRole[]>(
              `/restaurants/${restaurant.id}/users`,
            );
            return { restaurant, users: data };
          }),
        );

        const map: Record<string, Restaurant[]> = {};
        for (const result of results) {
          for (const row of result.users) {
            if (!map[row.user_id]) map[row.user_id] = [];
            map[row.user_id].push(result.restaurant);
          }
        }

        return map;
      },
    });

  const createAdmin = useMutation({
    mutationFn: () =>
      api.post("/admin/users", {
        email,
        password,
        first_name: firstName || null,
        last_name: lastName || null,
        phone: phone || null,
      }),
    onSuccess: () => {
      toast.success("Admin user created");
      setEmail("");
      setPassword("");
      setFirstName("");
      setLastName("");
      setPhone("");
      qc.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (err: unknown) => toast.error(parseApiError(err).message),
  });

  const canCreate = useMemo(
    () => isSuperAdmin && !!email.trim() && password.length >= 6,
    [isSuperAdmin, email, password],
  );

  const linkRestaurant = useMutation({
    mutationFn: (input: { userId: string; restaurantId: string }) =>
      api.post(`/restaurants/${input.restaurantId}/assign`, {
        user_id: input.userId,
        role: "admin",
      }),
    onSuccess: () => {
      toast.success("Admin linked to restaurant");
      qc.invalidateQueries({ queryKey: ["admin-user-restaurant-links"] });
    },
    onError: (err: unknown) => toast.error(parseApiError(err).message),
  });

  if (!isSuperAdmin) {
    return (
      <div className="max-w-2xl mx-auto p-4 md:p-8">
        <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4">
          <h1 className="text-lg font-bold text-red-700">Access denied</h1>
          <p className="text-sm text-red-600 mt-1">
            Only super admins can create new admin users.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto p-4 md:p-8 pb-16">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-[#eff2f0] rounded-lg">
          <Shield className="w-6 h-6 text-[#24422e]" />
        </div>
        <div>
          <h1 className="text-2xl font-black text-gray-900 tracking-tight">
            Admin Management
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Create admin users. Super admins only.
          </p>
        </div>
      </div>

      <div className="rounded-2xl border border-gray-100 bg-white shadow-sm p-5 space-y-4">
        <div className="flex items-center gap-2">
          <UserPlus className="w-4 h-4 text-[#24422e]" />
          <h2 className="text-sm font-bold text-gray-800">Create New Admin</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="md:col-span-2">
            <label
              htmlFor="admin-email"
              className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5"
            >
              Email
            </label>
            <input
              id="admin-email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@yourcompany.com"
              className={INPUT_CLS}
              type="email"
            />
          </div>

          <div className="md:col-span-2">
            <label
              htmlFor="admin-password"
              className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5"
            >
              Password
            </label>
            <input
              id="admin-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Minimum 6 characters"
              className={INPUT_CLS}
              type="password"
            />
          </div>

          <div>
            <label
              htmlFor="admin-first-name"
              className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5"
            >
              First Name
            </label>
            <input
              id="admin-first-name"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              className={INPUT_CLS}
              type="text"
            />
          </div>

          <div>
            <label
              htmlFor="admin-last-name"
              className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5"
            >
              Last Name
            </label>
            <input
              id="admin-last-name"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              className={INPUT_CLS}
              type="text"
            />
          </div>

          <div className="md:col-span-2">
            <label
              htmlFor="admin-phone"
              className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5"
            >
              Phone (optional)
            </label>
            <input
              id="admin-phone"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className={INPUT_CLS}
              type="text"
            />
          </div>
        </div>

        <button
          onClick={() => createAdmin.mutate()}
          disabled={!canCreate || createAdmin.isPending}
          className="inline-flex items-center justify-center text-white text-sm font-bold px-5 py-2.5 rounded-xl transition disabled:opacity-50"
          style={{ background: "linear-gradient(135deg, #24422e, #3a6b47)" }}
        >
          {createAdmin.isPending ? "Creating..." : "Create Admin"}
        </button>
      </div>

      <div className="rounded-2xl border border-gray-100 bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b bg-gray-50/80">
          <h2 className="text-sm font-bold text-gray-800">
            Existing Admin Users
          </h2>
        </div>

        {isLoading ? (
          <div className="px-5 py-6 text-sm text-gray-500">
            Loading admins...
          </div>
        ) : admins.length === 0 ? (
          <div className="px-5 py-6 text-sm text-gray-500">
            No admin users found.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th className="px-5 py-3 font-semibold">Email</th>
                  <th className="px-5 py-3 font-semibold">Name</th>
                  <th className="px-5 py-3 font-semibold">Role</th>
                  <th className="px-5 py-3 font-semibold">
                    Linked Restaurants
                  </th>
                  <th className="px-5 py-3 font-semibold">
                    Link to Restaurant
                  </th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold">Created</th>
                </tr>
              </thead>
              <tbody>
                {admins.map((a) => (
                  <tr key={a.id} className="border-b last:border-b-0">
                    <td className="px-5 py-3">{a.email}</td>
                    <td className="px-5 py-3">
                      {[a.first_name, a.last_name].filter(Boolean).join(" ") ||
                        "-"}
                    </td>
                    <td className="px-5 py-3 capitalize">
                      {a.role.replace("_", " ")}
                    </td>
                    <td className="px-5 py-3">
                      {loadingAssignments ? (
                        <span className="text-gray-400">Loading...</span>
                      ) : (assignmentsByUser[a.id] ?? []).length === 0 ? (
                        <span className="text-gray-400">None</span>
                      ) : (
                        <div className="flex flex-wrap gap-1.5">
                          {(assignmentsByUser[a.id] ?? []).map((restaurant) => (
                            <span
                              key={`${a.id}-${restaurant.id}`}
                              className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-[#eff2f0] text-[#24422e]"
                            >
                              {restaurant.name}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex gap-2">
                        <select
                          value={selectedRestaurantByUser[a.id] ?? ""}
                          onChange={(e) =>
                            setSelectedRestaurantByUser((prev) => ({
                              ...prev,
                              [a.id]: e.target.value,
                            }))
                          }
                          className="border border-gray-200 rounded-lg px-2.5 py-1.5 text-xs min-w-48"
                        >
                          <option value="">Select restaurant</option>
                          {restaurants.map((r) => (
                            <option key={r.id} value={r.id}>
                              {r.name}
                            </option>
                          ))}
                        </select>
                        <button
                          onClick={() =>
                            linkRestaurant.mutate({
                              userId: a.id,
                              restaurantId: selectedRestaurantByUser[a.id],
                            })
                          }
                          disabled={
                            !selectedRestaurantByUser[a.id] ||
                            linkRestaurant.isPending
                          }
                          className="px-3 py-1.5 rounded-lg text-xs font-semibold text-white disabled:opacity-50"
                          style={{
                            background:
                              "linear-gradient(135deg, #24422e, #3a6b47)",
                          }}
                        >
                          Link
                        </button>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      {a.is_active ? (
                        <span className="text-emerald-700">Active</span>
                      ) : (
                        <span className="text-red-600">Disabled</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      {new Date(a.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
