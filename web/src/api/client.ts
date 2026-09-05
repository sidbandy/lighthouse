// Thin fetch wrapper over the Lighthouse API. No client-side caching beyond
// what React Query would add later; for a single local operator the API is
// fast enough that keeping this simple is the right call.

import type {
  AnswerFeedback,
  Application,
  ApplicationEvent,
  AtsReport,
  AttemptOutcome,
  Board,
  CompanySuggestion,
  Constraints,
  Contact,
  ContactInput,
  Corpus,
  Coverage,
  CycleCount,
  DiscoverParams,
  Draft,
  Extraction,
  Fact,
  FactInput,
  InteractionKind,
  LaneBucket,
  MajorOptions,
  NetworkOverview,
  Onboarding,
  ParsedContact,
  PracticeQuestion,
  PostingDetail,
  TriageGroup,
  PracticeCapability,
  ReferralReport,
  StoryMatch,
  StudyHome,
  WeeklyBrief,
  StudyProblem,
  RefreshStatus,
  ResumeVersion,
  RoleFamily,
  SourceHealth,
  Story,
  StoryBank,
  StoryInput,
  StudentProfile,
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

  // --- Corpus: stories ---
  stories: () => get<StoryBank>("/api/corpus/stories"),
  createStory: (story: StoryInput) => send<Story>("POST", "/api/corpus/stories", story),
  updateStory: (id: string, story: StoryInput) =>
    send<Story>("PATCH", `/api/corpus/stories/${id}`, story),
  deleteStory: (id: string) => send<void>("DELETE", `/api/corpus/stories/${id}`),

  // --- Onboarding ---
  onboarding: () => get<Onboarding>("/api/onboarding"),
  saveConstraints: (constraints: Constraints) =>
    send<Onboarding>("PUT", "/api/onboarding/constraints", constraints),
  saveTargets: (names: string[]) => send<Onboarding>("PUT", "/api/onboarding/targets", names),
  majorOptions: () => get<MajorOptions>("/api/onboarding/majors"),
  roleFamiliesFor: (major: string) =>
    get<string[]>("/api/onboarding/role-families", { major }),
  saveStudentProfile: (profile: Partial<StudentProfile>) =>
    send<Onboarding>("PUT", "/api/onboarding/student", profile),
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
  /** Notes and which résumé went out are corrections to a record, not dated
   *  events, so they are a patch rather than a log entry. */
  patchApplication: (
    applicationId: string,
    patch: { notes?: string; resume_version_id?: string; clear_resume_version?: boolean },
  ) => send<Application>("PATCH", `/api/applications/${applicationId}`, patch),

  // --- Track: résumé versions ---
  resumeVersions: () => get<ResumeVersion[]>("/api/resume/versions"),
  saveResumeVersion: (version: { label: string; extracted_text?: string; notes?: string }) =>
    send<ResumeVersion>("POST", "/api/resume/versions", version),
  deleteResumeVersion: (id: string) => send<void>("DELETE", `/api/resume/versions/${id}`),

  // --- Network: contacts, cadence, drafts ---
  contacts: () => get<Contact[]>("/api/network/contacts"),
  networkOverview: (horizonDays = 7) =>
    get<NetworkOverview>("/api/network/overview", { horizon_days: horizonDays }),
  createContact: (contact: ContactInput) =>
    send<Contact>("POST", "/api/network/contacts", contact),
  updateContact: (id: string, contact: ContactInput) =>
    send<Contact>("PATCH", `/api/network/contacts/${id}`, contact),
  deleteContact: (id: string) => send<void>("DELETE", `/api/network/contacts/${id}`),
  /** Reads a pasted block into candidates. Saves nothing. */
  parseContacts: (text: string) =>
    send<ParsedContact[]>("POST", "/api/network/parse", { text }),
  createContacts: (contacts: ContactInput[]) =>
    send<Contact[]>("POST", "/api/network/contacts/bulk", contacts),
  logInteraction: (
    contactId: string,
    interaction: {
      kind: InteractionKind;
      summary?: string;
      channel?: string;
      direction?: string;
      occurred_at?: string;
      application_id?: string;
    },
  ) => send<Contact>("POST", `/api/network/contacts/${contactId}/interactions`, interaction),
  /** Two drafts to choose between. Nothing is sent and nothing is stored. */
  draftMessages: (contactId: string, kind = "cold_outreach") =>
    send<Draft[]>("POST", `/api/network/contacts/${contactId}/drafts?kind=${kind}`),
  referralSplit: () => get<ReferralReport>("/api/network/referrals"),

  // --- Study ---
  study: () => get<StudyHome>("/api/study"),
  logAttempt: (attempt: {
    problem_slug: string;
    outcome: AttemptOutcome;
    time_taken_sec?: number;
    attempted_at?: string;
    notes?: string;
  }) => send<StudyHome>("POST", "/api/study/attempts", attempt),
  patternProblems: (slug: string) => get<StudyProblem[]>(`/api/study/patterns/${slug}/problems`),

  // --- Practice ---
  practiceQuestion: (competency?: string, exclude?: string[]) =>
    get<PracticeQuestion>("/api/practice/question", {
      competency,
      exclude: exclude?.length ? exclude.join("|") : undefined,
    }),
  /** Analyse one spoken answer. Nothing is stored, and no audio ever leaves the browser. */
  reviewAnswer: (answer: {
    transcript: string;
    duration_sec: number;
    question?: string;
    competency?: string;
    // Typed answers are recorded but never enter a delivery trend — there is no
    // duration for typed text, so its pace is not the same measurement.
    answer_mode?: "spoken" | "typed";
    words?: { text: string; start: number; end: number }[];
  }) => send<AnswerFeedback>("POST", "/api/practice/answer", answer),
  practiceCapabilities: () =>
    get<PracticeCapability>("/api/practice/capabilities"),

  // Multipart rather than JSON: this is 16 kHz mono WAV, and base64 in a JSON
  // body would inflate it by a third for no benefit. The audio goes to the
  // local API, is measured, and is never stored.
  reviewRecordedAnswer: async (
    wav: Blob,
    meta: { question?: string; competency?: string },
  ) => {
    const form = new FormData();
    form.append("audio", wav, "answer.wav");
    const query = new URLSearchParams();
    if (meta.question) query.set("question", meta.question);
    if (meta.competency) query.set("competency", meta.competency);
    return postForm<AnswerFeedback>(`/api/practice/answer/audio?${query}`, form);
  },

  weeklyBrief: () => get<WeeklyBrief>("/api/briefing/weekly"),
  triage: () => get<TriageGroup[]>("/api/briefing/triage"),

  storiesFor: (competency: string) =>
    get<StoryMatch[]>("/api/practice/question/stories", { competency }),

  // --- Ingest ---
  startRefresh: () => send<RefreshStatus>("POST", "/api/ingest/refresh?max_tier=3"),
  refreshStatus: () => get<RefreshStatus>("/api/ingest/refresh"),
};

export { ApiError };
