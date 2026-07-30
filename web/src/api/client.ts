// Thin fetch wrapper over the Lighthouse API. No client-side caching beyond
// what React Query would add later; for a single local operator the API is
// fast enough that keeping this simple is the right call.

import type {
  AtsReport,
  CycleCount,
  DiscoverParams,
  LaneBucket,
  PostingDetail,
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

async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(BASE + path, { method: "POST", body: form });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
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
};

export { ApiError };
