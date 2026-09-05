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
  /** Where this posting already sits on your board. Null when untracked. */
  tracked: TrackedState | null;
}

/** A stage change that can honestly be logged from where a row is now. Served
 *  by the API so the board and the posting window never disagree. */
export interface Transition {
  event_type: ApplicationEvent;
  label: string;
  is_setback: boolean;
}

export interface TrackedState {
  application_id: string;
  stage: Stage;
  stage_label: string;
  is_live: boolean;
  is_terminal: boolean;
  applied_at: string | null;
  days_silent: number | null;
  silence_note: string | null;
  next_events: Transition[];
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
  /** Facts in the corpus at scoring time. Zero means the score is an absence of
   *  data rather than a judgement, and the UI has to say so. */
  corpus_size: number;
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
  /** How many are being returned. */
  count: number;
  /** How many this lane holds in the slice that was scored. */
  scored_in_lane: number;
  /** The lane holds more than it is showing. Without this the list just stops,
   *  and a cap is indistinguishable from the end of the market. */
  has_more: boolean;
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

/** One fact lifted from the description, with the sentence it came from. */
export interface BriefFact {
  kind: string;
  label: string;
  value: string;
  evidence: string;
}

export interface PostingBrief {
  /** Pay, working pattern, length, deadline, GPA — whichever the posting states. */
  logistics: BriefFact[];
  process: BriefFact[];
  responsibilities: string[];
  /** The description named nothing concrete. That absence is itself a signal. */
  is_thin: boolean;
}

/** Whether your graduation term clears this posting's stated window.
 *  `not_stated` is the honest and most common answer and is never dressed up
 *  as either of the other two. */
export interface Eligibility {
  verdict: "eligible" | "not_eligible" | "not_stated";
  headline: string;
  detail: string;
  evidence: string | null;
  is_blocking: boolean;
}

export interface PostingDetail extends PostingSummary {
  description: string | null;
  brief: PostingBrief | null;
  eligibility: Eligibility | null;
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

// --- Corpus: the operator's own facts, and what they are worth ---

export type FactType = "project" | "experience" | "skill" | "achievement" | "education";

export interface Fact {
  id: string;
  fact_type: FactType;
  title: string;
  body: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface FactInput {
  fact_type: FactType;
  title: string;
  body?: string;
  metadata?: Record<string, unknown>;
}

/** A candidate fact from a resume. No id, because nothing has been saved. */
export interface DraftFact {
  fact_type: FactType;
  title: string;
  body: string;
}

export interface Extraction {
  drafts: DraftFact[];
  page_count: number;
  char_count: number;
  likely_image_based: boolean;
  note: string;
}

export interface CorpusSummary {
  fact_count: number;
  facts_by_type: Record<string, number>;
  story_count: number;
  unverified_story_count: number;
  is_usable_for_matching: boolean;
  readiness_note: string;
}

export interface Corpus {
  facts: Fact[];
  summary: CorpusSummary;
}

// --- Corpus: stories ---

export interface StoryInput {
  title: string;
  situation?: string;
  task?: string;
  action?: string;
  result?: string;
  /** What makes a story verifiable. Empty means unverified, not invalid. */
  source_fact_ids?: string[];
  competency_tags?: string[];
}

export interface Story extends Required<StoryInput> {
  id: string;
  is_grounded: boolean;
  created_at: string;
  updated_at: string;
}

export interface Competency {
  slug: string;
  /** What this competency actually asks for, in plain words. */
  prompt: string;
}

export interface CompetencyCoverage extends Competency {
  story_count: number;
  story_titles: string[];
}

/** One fact carrying an outsized share of the story bank. */
export interface SourceReliance {
  fact_id: string;
  fact_title: string;
  story_count: number;
}

export interface StoryBank {
  stories: Story[];
  story_count: number;
  verified_count: number;
  note: string;
  competencies: CompetencyCoverage[];
  reliance: SourceReliance[];
}

/** Observed demand for one term across the sampled postings. Counts, not scores. */
export interface TermDemand {
  term: string;
  posting_count: number;
  core_count: number;
  is_technical: boolean;
}

export interface FactContribution {
  fact_id: string;
  fact_type: FactType;
  title: string;
  terms: TermDemand[];
  /** Sampled postings mentioning at least one of this fact's terms. */
  reach: number;
  /** Of those, the ones no other fact reaches. */
  unique_reach: number;
  unmatched_term_count: number;
}

export interface Coverage {
  sample_size: number;
  is_meaningful: boolean;
  /** The sample, stated plainly. Always render this beside the numbers. */
  basis: string;
  fact_count: number;
  reached: number;
  unreached: number;
  contributions: FactContribution[];
  gaps: TermDemand[];
}

// --- Onboarding ---

export type SponsorshipStance = "needs_sponsorship" | "us_authorized" | "us_citizen";

export interface Constraints {
  preferred_locations: string[];
  open_to_remote: boolean;
  sponsorship: SponsorshipStance;
  weekly_study_hours: number;
  target_cycles: string[];
}

export interface TargetCompany {
  id: string;
  name: string;
  canonical_name: string;
  tier: string | null;
  /** 1-4, higher is more selective. Never affected by marking a target. */
  selectivity: number;
}

export type OnboardingStep =
  | "upload_resume"
  | "add_projects"
  | "pick_targets"
  | "set_constraints"
  | "complete";

export type DegreeLevel = "associate" | "bachelors" | "masters" | "phd";

/** Who the operator is academically. Internship counts, not years of experience. */
export interface StudentProfile {
  school: string | null;
  major: string | null;
  degree_level: DegreeLevel | null;
  graduation_season: Season | null;
  graduation_year: number | null;
  internships_completed: number;
  /** Seeded from the major when left empty. */
  target_role_families: RoleFamily[];
}

export interface MajorOptions {
  majors: string[];
  degree_levels: { value: string; label: string }[];
}

export interface Onboarding {
  next_step: OnboardingStep;
  is_complete: boolean;
  corpus: CorpusSummary;
  target_company_count: number;
  constraints_set: boolean;
  constraints: Constraints | null;
  /** Present only before the operator has set constraints. A starting point for
   *  the form, never a claim that they chose it -- `constraints` stays null
   *  until they actually answer. */
  suggested_constraints: Constraints | null;
  student: StudentProfile | null;
  targets: TargetCompany[];
}

export interface CompanySuggestion {
  name: string;
  canonical_name: string;
  posting_count: number;
  is_target: boolean;
}

export interface DiscoverParams {
  season?: Season[];
  employment_type?: EmploymentType[];
  role_family?: RoleFamily[];
  sponsorship?: Sponsorship[];
  state?: string[];
  search?: string;
  remote_only?: boolean;
  posted_within_days?: number;
  with_description_only?: boolean;
  per_lane?: number;
}

// --- Track: the application board ---

export type Stage =
  | "SAVED"
  | "APPLIED"
  | "ASSESSMENT"
  | "INTERVIEW"
  | "FINAL"
  | "OFFER"
  | "REJECTED"
  | "WITHDRAWN"
  | "ACCEPTED";

/** The event vocabulary the backend accepts. Mirrors EVENT_STAGES. */
export type ApplicationEvent =
  | "saved"
  | "applied"
  | "assessment_received"
  | "assessment_completed"
  | "interview_scheduled"
  | "interview_completed"
  | "final_round"
  | "offer"
  | "rejected"
  | "withdrawn"
  | "accepted"
  | "note";

export interface StageEntry {
  event_type: string;
  stage: Stage;
  label: string;
  occurred_at: string;
  note: string;
}

export interface Application {
  id: string;
  posting_id: string;
  posting_title: string;
  company_name: string;
  posting_url: string;
  term_label: string | null;
  location: string | null;
  stage: Stage;
  stage_label: string;
  is_live: boolean;
  is_terminal: boolean;
  timeline: StageEntry[];
  notes: string | null;
  /** Which résumé went out. Null until set — the funnel cannot compare versions without it. */
  resume_version_id: string | null;
  /** Days since the last employer signal. A real subtraction, not a ghosting probability. */
  days_silent: number | null;
  silence_note: string | null;
  next_events: Transition[];
}

export interface StageCount {
  stage: Stage;
  label: string;
  reached: number;
  current: number;
}

export interface Conversion {
  from_label: string;
  to_label: string;
  reached_from: number;
  reached_to: number;
  has_enough_data: boolean;
  /** Pre-rendered with both numbers always shown. Render as-is. */
  statement: string;
}

export interface WaitTime {
  from_label: string;
  to_label: string;
  sample_size: number;
  median_days: number | null;
  statement: string;
}

export interface Funnel {
  total: number;
  has_enough_data: boolean;
  basis: string;
  stages: StageCount[];
  conversions: Conversion[];
  waits: WaitTime[];
}

/** A résumé the operator wrote. Lighthouse tracks and scores; it never
 *  generates one. */
export interface ResumeVersion {
  id: string;
  label: string;
  notes: string | null;
  created_at: string;
}

/** What happened to the applications that used one version. Counts only — a
 *  response rate over four applications is noise wearing a percent sign. */
export interface VersionOutcome {
  version_id: string;
  label: string;
  applied: number;
  responded: number;
  statement: string;
}

export interface Board {
  applications: Application[];
  funnel: Funnel;
  resume_versions: ResumeVersion[];
  version_outcomes: VersionOutcome[];
}

// --- Network: contacts, cadence, drafts ---

export type RelationshipType = "cold" | "warm_intro" | "alumni" | "met_at_event" | "referred_by";

export type InteractionKind =
  | "outreach"
  | "reply"
  | "conversation"
  | "referral_asked"
  | "referral_confirmed"
  | "thank_you"
  | "note";

export type ContactStage =
  | "not_contacted"
  | "awaiting_reply"
  | "in_conversation"
  | "referred"
  | "closed";

export interface Interaction {
  id: string;
  kind: InteractionKind;
  label: string;
  direction: "inbound" | "outbound";
  summary: string;
  channel: string | null;
  application_id: string | null;
  occurred_at: string;
}

/** One thing worth doing, on a real date rather than a priority score. */
export interface NextStep {
  action: string;
  due_on: string;
  reason: string;
  draft_kind: string;
  /** "today", "in 4 days", "3 days late". Pre-rendered — show as-is. */
  status: string;
  is_due: boolean;
}

export interface ContactInput {
  name: string;
  company_name?: string | null;
  role_title?: string | null;
  relationship_type?: RelationshipType;
  school?: string | null;
  grad_year?: number | null;
  strength?: number | null;
  email?: string | null;
  profile_url?: string | null;
  notes?: string | null;
}

export interface Contact extends ContactInput {
  id: string;
  name: string;
  company_id: string | null;
  relationship_type: RelationshipType;
  is_alumni: boolean;
  stage: ContactStage;
  stage_label: string;
  days_since_outbound: number | null;
  silence_note: string | null;
  unanswered_outreach: number;
  referral_asked: boolean;
  referral_confirmed: boolean;
  timeline: Interaction[];
  next_step: NextStep | null;
  /** Set when the sequence is finished — why there is nothing more to do. */
  cadence_note: string;
}

/** A candidate from a pasted block. No id: nothing has been saved. */
export interface ParsedContact {
  name: string;
  role_title: string | null;
  company_name: string | null;
}

export interface CompanyCoverage {
  company_id: string | null;
  company_name: string;
  contact_count: number;
  alumni_count: number;
  open_postings: number;
  is_target: boolean;
  note: string;
}

export interface QueueItem {
  contact_id: string;
  name: string;
  company_name: string | null;
  step: NextStep;
}

export interface NetworkOverview {
  school: string | null;
  total_contacts: number;
  alumni_contacts: number;
  note: string;
  coverage: CompanyCoverage[];
  queue: QueueItem[];
}

export interface Draft {
  variant: string;
  subject: string;
  body: string;
  word_count: number;
  source_fact_ids: string[];
  provider: string;
  /** A template rather than a model. Different things; the operator should know. */
  is_fallback: boolean;
  grounding_note: string;
  warnings: string[];
}

export interface RouteOutcome {
  route: string;
  applied: number;
  responded: number;
  statement: string;
}

export interface ReferralReport {
  referred: RouteOutcome;
  cold: RouteOutcome;
  is_comparable: boolean;
  note: string;
}

// --- Study ---

export interface StudyResource {
  label: string;
  url: string;
  kind: "practice" | "reading" | "reference" | "course";
  note: string;
  is_free: boolean;
}

export interface PatternRecord {
  slug: string;
  name: string;
  blurb: string;
  total: number;
  clean: number;
  /** Below the sample floor a pattern is not weak, it is unmeasured. */
  has_enough: boolean;
  is_weak: boolean;
  is_untouched: boolean;
  days_since: number | null;
  statement: string;
  resources: StudyResource[];
}

export interface StudyProblem {
  slug: string;
  title: string;
  difficulty: "easy" | "medium" | "hard";
  url: string;
  patterns: string[];
  is_core: boolean;
}

export interface Suggestion {
  problem: StudyProblem;
  pattern_slug: string;
  pattern_name: string;
  reason: string;
}

export interface Review {
  problem_slug: string;
  title: string;
  url: string;
  step: number;
  due_on: string;
  days_overdue: number;
  statement: string;
}

export interface ReviewQueue {
  due: Review[];
  upcoming: Review[];
  total_due: number;
  was_capped: boolean;
  note: string;
}

export interface TopicNeed {
  slug: string;
  name: string;
  blurb: string;
  application_count: number;
  total_applications: number;
  matched_terms: string[];
  companies: string[];
  partially_covered: boolean;
  statement: string;
  hours_low: number;
  hours_high: number;
  resources: StudyResource[];
}

export interface Curriculum {
  total_applications: number;
  note: string;
  needs: TopicNeed[];
  /** Terms your applications emphasise that the catalogue does not cover. */
  uncatalogued: [string, number][];
}

export interface StudyHome {
  patterns: PatternRecord[];
  suggestions: Suggestion[];
  reviews: ReviewQueue;
  curriculum: Curriculum;
  prerequisite_gaps: string[];
}

export type AttemptOutcome =
  | "solved_clean"
  | "solved_with_hint"
  | "solved_over_time"
  | "failed";

// --- Practice ---

export interface PracticeQuestion {
  text: string;
  competency: string;
  /** Asked after every answer — the probe people are least ready for. */
  follow_up: string;
}

export interface DeliveryMetric {
  key: string;
  label: string;
  value: number;
  unit: string;
  ideal: string;
  verdict: "good" | "watch" | "off";
  detail: string;
}

export interface DeliveryReport {
  duration_sec: number;
  word_count: number;
  is_measurable: boolean;
  summary: string;
  metrics: DeliveryMetric[];
  filler_examples: string[];
}

export interface StructureFinding {
  part: string;
  label: string;
  present: boolean;
  advice: string;
}

/** A figure said aloud that the corpus does not support. */
export interface DriftFinding {
  claim: string;
  detail: string;
}

/** One delivery metric across the operator's own past sessions. Direction is
 *  reported, never judged: falling filler density is an improvement, falling
 *  pace is not necessarily one, and only the reader knows which they wanted. */
export interface DeliveryTrend {
  key: string;
  label: string;
  first: number;
  latest: number;
  sessions: number;
  change: number;
  statement: string;
}

/** What the local voice pipeline can measure on this machine, resolved before
 *  the operator records rather than after. */
export interface PracticeCapability {
  mode: "acoustic" | "transcript";
  voice_detector: boolean;
  transcriber: boolean;
  measures_filled_pauses: boolean;
  note: string;
}

/** Voiced time the transcriber wrote no word for — where the "um" was.
 *  A span rather than a count, so it can be played back and disagreed with. */
export interface VoicedGap {
  start: number;
  end: number;
  duration: number;
  is_probable_filler: boolean;
  statement: string;
}

export interface AnswerFeedback {
  delivery: DeliveryReport;
  structure: StructureFinding[];
  drift: DriftFinding[];
  notes: string;
  summary: string;
  provider: string;
  is_fallback: boolean;
  trends: DeliveryTrend[];
  voiced_gaps: VoicedGap[];
  mode: "acoustic" | "transcript";
}

export interface StoryMatch {
  story_id: string;
  title: string;
  competency_tags: string[];
  is_grounded: boolean;
}

/** Background ingest state, polled by the refresh control. */
export interface RefreshStatus {
  is_running: boolean;
  started_at: string | null;
  finished_at: string | null;
  summary: string | null;
  error: string | null;
  created: number;
  updated: number;
  sources_ok: number;
  sources_failed: number;
  /** False when a refresh was asked for while one was already running. */
  accepted: boolean;
}

// ---------------------------------------------------------------------------
// Briefing — the week in one place
// ---------------------------------------------------------------------------

export interface BriefItem {
  kind: string;
  title: string;
  /** The fact that produced this item, in words. Never a score. */
  detail: string;
  link: string;
  due_on: string | null;
  is_late: boolean;
}

export interface BriefSection {
  key: string;
  title: string;
  items: BriefItem[];
  count: number;
  /** Shown instead of the items. An empty section is information, but only if
   *  it says which kind of empty it is. */
  empty_note: string;
}

export interface WeeklyBrief {
  generated_for: string;
  headline: string;
  total_items: number;
  late_items: number;
  sections: BriefSection[];
  funnel_note: string;
  baseline_note: string;
}

export interface TriageApplication {
  application_id: string;
  posting_title: string;
  company_name: string;
  band: string;
  band_blurb: string;
  reason: string;
  stage_label: string;
}

export interface TriageGroup {
  band: string;
  blurb: string;
  applications: TriageApplication[];
  count: number;
}
