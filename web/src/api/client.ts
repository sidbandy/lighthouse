// Thin fetch wrapper over the Lighthouse API. No client-side caching beyond
// what React Query would add later; for a single local operator the API is
// fast enough that keeping this simple is the right call.

import type {
  Application,
  ApplicationEvent,
  AtsReport,
  Board,
  CompanySuggestion,
  Constraints,
  Corpus,
  Coverage,
  CycleCount,
  DiscoverParams,
  Extraction,
  Fact,
  FactInput,
  LaneBucket,
  Onboarding,
  PostingDetail,
  RefreshStatus,
  RoleFamily,
  SourceHealth,
  TailorReport,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8077";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function get<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const url = new URL(BASE + path);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value == null) continue;
      for (const v of Array.isArray(value) ? value : [value]) {
        url.searchParams.append(key, String(v));
      }
    }
  }
  const res = await fetch(url);
  if (!res.ok) {
    throw new ApiError(res.status, `${res.status} ${res.statusText} for ${path}`);
  }
  return res.json() as Promise<T>;
}

async function detail(res: Response): Promise<string> {
  let message = `${res.status} ${res.statusText}`;
  try {
    const body = await res.json();
    // FastAPI validation errors arrive as a list of per-field objects; the
    // operator only needs the message, not the pydantic location path.
    if (Array.isArray(body.detail)) {
      message = body.detail.map((d: { msg?: string }) => d.msg ?? String(d)).join("; ");
    } else if (body.detail) {
      message = body.detail;
    }
  } catch {
    /* body was not JSON */
  }
  return message;
}

async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(BASE + path, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json() as Promise<T>;
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  discover: (params: DiscoverParams) =>
    get<LaneBucket[]>("/api/discover", params as Record<string, unknown>),
  posting: (id: string) => get<PostingDetail>(`/api/postings/${id}`),
  cycles: () => get<CycleCount[]>("/api/cycles"),
  sourceHealth: () => get<SourceHealth[]>("/api/sources/health"),
  sourceBreakdown: () => get<Record<string, number>>("/api/sources/breakdown"),

  checkResume: (file: File, employmentType = "internship") => {
    const form = new FormData();
    form.append("file", file);
    form.append("employment_type_hint", employmentType);
    return postForm<AtsReport>("/api/resume/check", form);
  },
  tailor: (postingId: string, resumeText?: string) => {
    const form = new FormData();
    if (resumeText) form.append("resume_text", resumeText);
    return postForm<TailorReport>(`/api/postings/${postingId}/tailor`, form);
  },

  // --- Corpus ---
  corpus: () => get<Corpus>("/api/corpus"),
  createFact: (fact: FactInput) => send<Fact>("POST", "/api/corpus/facts", fact),
  updateFact: (id: string, fact: FactInput) =>
    send<Fact>("PATCH", `/api/corpus/facts/${id}`, fact),
  deleteFact: (id: string) => send<void>("DELETE", `/api/corpus/facts/${id}`),
  createFacts: (facts: FactInput[]) => send<Fact[]>("POST", "/api/corpus/facts/bulk", facts),
  extractResume: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return postForm<Extraction>("/api/corpus/extract", form);
  },
  coverage: (roleFamilies?: RoleFamily[]) =>
    get<Coverage>("/api/corpus/coverage", { role_family: roleFamilies }),

  // --- Onboarding ---
  onboarding: () => get<Onboarding>("/api/onboarding"),
  saveConstraints: (constraints: Constraints) =>
    send<Onboarding>("PUT", "/api/onboarding/constraints", constraints),
  saveTargets: (names: string[]) => send<Onboarding>("PUT", "/api/onboarding/targets", names),
  searchCompanies: (q: string, limit = 20) =>
    get<CompanySuggestion[]>("/api/companies/search", { q, limit }),

  // --- Track: the application board ---
  board: () => get<Board>("/api/applications"),
  /** Save a posting to the board, optionally logging a stage in the same call. */
  trackPosting: (postingId: string, event?: { event_type: ApplicationEvent; occurred_at?: string; note?: string }) =>
    send<Application>("POST", `/api/postings/${postingId}/apply`, event ?? null),
  logEvent: (
    applicationId: string,
    event: { event_type: ApplicationEvent; occurred_at?: string; note?: string },
  ) => send<Application>("POST", `/api/applications/${applicationId}/events`, event),
  untrack: (applicationId: string) => send<void>("DELETE", `/api/applications/${applicationId}`),

  // --- Ingest ---
  startRefresh: () => send<RefreshStatus>("POST", "/api/ingest/refresh?max_tier=3"),
  refreshStatus: () => get<RefreshStatus>("/api/ingest/refresh"),
};

export { ApiError };
