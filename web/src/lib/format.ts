// Small presentation helpers. Deliberately dumb: no business logic lives in the
// frontend, it only formats what the API already decided.

export function relativeAge(days: number | null): string {
  if (days == null) return "no date";
  if (days === 0) return "today";
  if (days === 1) return "1 day ago";
  if (days < 30) return `${days} days ago`;
  const months = Math.round(days / 30);
  return months === 1 ? "1 month ago" : `${months} months ago`;
}

const ROLE_LABELS: Record<string, string> = {
  swe: "SWE",
  ai_ml: "AI / ML",
  data: "Data",
  hardware: "Hardware",
  quant: "Quant",
  product: "Product",
  security: "Security",
  other: "Other",
};

export const roleLabel = (r: string): string => ROLE_LABELS[r] ?? r;

const SPONSORSHIP_LABELS: Record<string, string> = {
  does_not_offer: "No sponsorship",
  citizenship_required: "US citizen only",
  offers: "Sponsors",
  unknown: "",
};

export const sponsorshipLabel = (s: string): string => SPONSORSHIP_LABELS[s] ?? "";

// The rule that resolved a posting's term, in plain words. The point is to
// show the operator *how* we know, never a confidence number.
const TERM_RULE_LABELS: Record<string, string> = {
  explicit_field: "stated by source",
  title_token: "from title",
  description_dates: "from description dates",
  eligibility_phrase: "from grad requirement",
  company_history: "from company's history",
  unknown: "term unknown",
};

export const termRuleLabel = (rule: string): string => TERM_RULE_LABELS[rule] ?? rule;

export function scoreColor(score: number): string {
  if (score >= 45) return "text-target";
  if (score >= 20) return "text-beacon-400";
  return "text-mist-400";
}

// Source ids like "ats_greenhouse_janestreet" -> "Jane Street board"; list
// repos keep a short readable form.
export function sourceLabel(id: string): string {
  if (id.startsWith("ats_")) {
    const parts = id.split("_");
    const vendor = parts[1];
    const slug = parts.slice(2).join("_");
    return `${slug} (${vendor})`;
  }
  return id.replace(/_/g, " ");
}
