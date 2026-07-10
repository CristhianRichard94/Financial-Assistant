import { describe, it, expect, vi, afterEach } from "vitest";

vi.mock("@/lib/supabase/server", () => ({
  createClient: vi.fn(),
}));

import { createClient } from "@/lib/supabase/server";
import { requireUser } from "@/lib/auth/requireUser";

function makeSupabaseClient(user: unknown) {
  return {
    auth: {
      getUser: vi.fn().mockResolvedValue({ data: { user } }),
    },
  };
}

describe("requireUser", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns the user when a session is present", async () => {
    const user = { id: "user-1", email: "user@example.com" };
    vi.mocked(createClient).mockResolvedValue(makeSupabaseClient(user) as never);

    const result = await requireUser();

    expect(result.response).toBeUndefined();
    expect(result.user).toEqual(user);
  });

  it("returns a 401 JSON response when there is no session", async () => {
    vi.mocked(createClient).mockResolvedValue(makeSupabaseClient(null) as never);

    const result = await requireUser();

    expect(result.user).toBeUndefined();
    expect(result.response).toBeDefined();
    expect(result.response!.status).toBe(401);
    const body = await result.response!.json();
    expect(body).toEqual({ error: "Unauthorized" });
  });

  it("calls getUser() (revalidated), not getSession(), to decide authorization", async () => {
    const user = { id: "user-1" };
    const client = makeSupabaseClient(user);
    vi.mocked(createClient).mockResolvedValue(client as never);

    await requireUser();

    expect(client.auth.getUser).toHaveBeenCalledTimes(1);
  });
});
