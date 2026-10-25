import { AuditEvent, RolloutInfo } from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_CONTROL_API_URL || "http://localhost:8080";

export async function checkApiHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/health/live`, {
      method: "GET",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function getActiveRollout(): Promise<RolloutInfo | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/rollouts/active`, {
      method: "GET",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) {
      return null;
    }
    return await res.json();
  } catch {
    return null;
  }
}

export async function advanceRollout(): Promise<{ success: boolean; message: string }> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/rollouts/advance`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      return { success: true, message: data.message || "Rollout advanced successfully" };
    }
    const err = await res.text().catch(() => "Unknown error");
    return { success: false, message: `Failed to advance: ${err}` };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error";
    return { success: false, message };
  }
}

export async function rollbackRollout(reason = "Manual operator intervention"): Promise<{ success: boolean; message: string }> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/rollouts/rollback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    });
    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      return { success: true, message: data.message || "Rollback initiated successfully" };
    }
    const err = await res.text().catch(() => "Unknown error");
    return { success: false, message: `Failed to rollback: ${err}` };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error";
    return { success: false, message };
  }
}

export async function getAuditEvents(): Promise<AuditEvent[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/audit`, {
      method: "GET",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) {
      return [];
    }
    const data = await res.json();
    return Array.isArray(data) ? data : data.events || [];
  } catch {
    return [];
  }
}
