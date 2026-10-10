export type User = { id: string; username: string; name: string };
export type Enrollment = {
  id: string;
  career: { code: string; name: string };
  period: { code: string; name: string; startsOn: string; endsOn: string };
  semester: number;
  status: string;
  statusLabel: string;
};
export type DevelopmentRecord = {
  id: string; type: "project" | "skill"; status: string; statusLabel: string;
  createdAt: string; updatedAt: string; reviewNote: string; validatedBy: string | null;
  validatedAt: string | null; canEdit: boolean; title?: string; name?: string;
  description: string; role?: string; startedOn?: string | null; completedOn?: string | null;
  proficiencyLabel?: string;
};
export type Profile = {
  enrollment: Enrollment; student: { name: string; studentNumber: string }; isOwner: boolean;
  canDeclare: boolean; grades: Array<{ id: string; course: string; courseCode: string; group: string;
    period: string; value: string; scale: string; threshold: string; passed: boolean; source: string;
    verifiedBy: string; verifiedAt: string | null; correctsValue: string | null }>;
  average: string | null; courses: Array<{ code: string; name: string; group: string }>;
  projects: DevelopmentRecord[]; skills: DevelopmentRecord[];
  counts: { validatedProjects: number; validatedSkills: number };
};
export type HomeData = { user: User; enrollments: Enrollment[]; canRegisterVerifiedActivity?: boolean; groups: Array<{
  id: string; course: { code: string; name: string; career: string }; period: string; group: string; studentCount: number;
}> };

let csrfToken = "";

async function readCsrf(): Promise<string> {
  if (csrfToken) return csrfToken;
  const response = await fetch("/api/v1/csrf/", { credentials: "same-origin" });
  const data = await response.json();
  csrfToken = data.csrfToken;
  return csrfToken;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRFToken", await readCsrf());
  const response = await fetch(path, { ...options, method, headers, credentials: "same-origin" });
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 403 && data.detail?.includes("CSRF")) csrfToken = "";
    const fieldErrors = data.errors
      ? Object.values(data.errors).flatMap((entries) => (entries as Array<{ message: string }>).map((entry) => entry.message))
      : [];
    const detail = Array.isArray(data.detail) ? data.detail.join(" ") : data.detail;
    throw new Error(fieldErrors.join(" ") || detail || "No se pudo completar la solicitud.");
  }
  return data as T;
}

export async function signIn(username: string, password: string): Promise<User> {
  const token = await readCsrf();
  const response = await fetch("/api/v1/auth/login/", {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRFToken": token },
    body: JSON.stringify({ username, password }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "No se pudo iniciar sesión.");
  csrfToken = data.csrfToken;
  return data.user as User;
}

export function signOut() {
  return api<void>("/api/v1/auth/logout/", { method: "POST" });
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Ocurrió un error inesperado.";
}

export function dateLabel(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("es-BO", { day: "2-digit", month: "short", year: "numeric", timeZone: "America/La_Paz" }).format(new Date(value));
}
