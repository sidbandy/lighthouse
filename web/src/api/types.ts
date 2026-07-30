// Types mirroring the FastAPI schemas in backend/lighthouse/discover/schemas.py.
// Kept hand-written and small rather than generated: the surface is narrow and
// the field meanings matter enough to document here.

export type Season = "spring" | "summer" | "fall" | "winter";
export type EmploymentType = "internship" | "new_grad" | "other";
export type RoleFamily =
  | "swe"
  | "ai_ml"
  | "data"
  | "hardware"
  | "quant"
  | "product"
  | "security"
  | "design"
  | "finance"
  | "consulting"
  | "business"
  | "marketing"
  | "mechanical"
  | "science"
  | "other";
export type Sponsorship =
  | "unknown"
  | "offers"
  | "does_not_offer"
  | "citizenship_required";

export interface PostingSummary {
  id: string;
  company_name: string;
  title: string;
  url: string;
  season: Season | null;
  term_year: number | null;
  term_label: string | null;
  term_rule: string;
  term_evidence: string | null;
  employment_type: EmploymentType;
  role_family: RoleFamily;
  sponsorship: Sponsorship;
  location_labels: string[];
  is_remote: boolean;
  is_active: boolean;
  description_available: boolean;
  posted_at: string | null;
  age_days: number | null;
  source_ids: string[];
  source_count: number;
}

export interface TermMatch {
  term: string;
  posting_count: number;
  corpus_count: number;
  is_technical: boolean;
  emphasis: "core" | "important" | "mentioned";
  component_evidence: string[];
}

export interface Match {
  score: number;
  evidence_basis: string;
  thin_evidence: boolean;
  summary: string;
  matched: TermMatch[];
  reword: TermMatch[];
  gaps: TermMatch[];
}

export interface Lane {
  lane: "reach" | "target" | "safety";
  selectivity: number;
  reason: string;
}

export interface ScoredPosting extends PostingSummary {
  match: Match;
  lane: Lane;
}

export interface LaneBucket {
  lane: "reach" | "target" | "safety";
  weekly_quota: number;
  count: number;
  postings: ScoredPosting[];
}

export interface GhostSignal {
  name: string;
  verdict: "good" | "neutral" | "concern" | "unknown";
  detail: string;
}

export interface GhostAssessment {
  label: string;
  summary: string;
  signals: GhostSignal[];
}

export interface SourceSighting {
  source_id: string;
  source_url: string;
  seen_at: string;
}

export interface PostingDetail extends PostingSummary {
  description: string | null;
  match: Match | null;
  ghost: GhostAssessment | null;
  ats_vendor: string | null;
  ats_job_id: string | null;
  sources: SourceSighting[];
  first_seen_at: string | null;
  last_seen_at: string | null;
}

export interface CycleCount {
  term_label: string;
  season: Season;
  term_year: number;
  count: number;
}

export interface SourceHealth {
  source_id: string;
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_row_count: number | null;
  previous_row_count: number | null;
  consecutive_failures: number;
  last_error: string | null;
  is_quarantined: boolean;
}

// --- Track: ATS check + tailoring ---

export interface AtsFinding {
  severity: "CRITICAL" | "WARNING" | "MINOR";
  category: string;
  title: string;
  detail: string;
  fix: string;
  evidence: string | null;
}

export interface ParsePreview {
  visual_text: string;
  ats_text: string;
  scrambled: boolean;
  column_count: number;
}

export interface AtsReport {
  will_parse_cleanly: boolean;
  verdict: string;
  page_count: number;
  char_count: number;
  word_count: number;
  fonts: string[];
  findings: AtsFinding[];
  preview: ParsePreview | null;
}

export interface Requirement {
  term: string;
  tier: "REQUIRED" | "PREFERRED" | "RESPONSIBILITY" | "GENERAL";
  posting_count: number;
  emphasis: "core" | "important" | "mentioned";
  is_technical: boolean;
  evidenced: boolean;
  is_reword: boolean;
  in_resume: boolean;
  component_evidence: string[];
  advice: string;
}

export interface HardRequirement {
  kind: string;
  label: string;
  detail: string;
}

export interface TailorReport {
  posting_title: string;
  company_name: string | null;
  summary: string;
  coverage: number;
  potential_coverage: number;
  resume_available: boolean;
  hard_requirements: HardRequirement[];
  required_gaps: Requirement[];
  missing_from_resume: Requirement[];
  rewords: Requirement[];
  evidenced: Requirement[];
  other_gaps: Requirement[];
}

export interface DiscoverParams {
  season?: Season[];
  role_family?: RoleFamily[];
  sponsorship?: Sponsorship[];
  state?: string[];
  with_description_only?: boolean;
  per_lane?: number;
}
