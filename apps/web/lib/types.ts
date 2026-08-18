/**
 * API domain types. Mirrors the Pydantic schemas in apps/api/app/schemas.
 * Kept hand-written and minimal so the frontend never depends on generated churn.
 */

export type JobStatus =
  | "active" | "expired" | "closed" | "removed" | "pending_review" | "unknown";

export type WorkMode = "onsite" | "hybrid" | "remote" | "unknown";

export type EmploymentType =
  | "full_time" | "part_time" | "contract" | "temporary"
  | "internship" | "freelance" | "volunteer" | "unknown";

export type ExperienceLevel =
  | "intern" | "fresh_graduate" | "entry" | "mid"
  | "senior" | "lead" | "executive" | "unknown";

export type SortOption = "newest" | "relevance" | "deadline" | "salary" | "quality";

export interface SourceBadge {
  id?: string | null;
  name: string;
  slug?: string | null;
  label?: string | null;
  website_url?: string | null;
  type?: string | null;
}

export interface CompanySummary {
  id: string;
  name: string;
  slug: string;
  logo_url?: string | null;
  website?: string | null;
  industry?: string | null;
  verified: boolean;
}

export interface SalaryRange {
  min?: string | number | null;
  max?: string | number | null;
  currency?: string | null;
  period?: string | null;
}

export interface JobListItem {
  id: string;
  slug: string;
  title: string;
  company_name?: string | null;
  company?: CompanySummary | null;
  location?: string | null;
  city?: string | null;
  province?: string | null;
  country: string;
  is_remote: boolean;
  work_mode: WorkMode;
  employment_type: EmploymentType;
  experience_level: ExperienceLevel;
  category: string;
  category_label?: string | null;
  is_internship: boolean;
  is_government: boolean;
  is_fresh_graduate_friendly: boolean;
  is_featured: boolean;
  salary?: SalaryRange | null;
  posted_at?: string | null;
  deadline?: string | null;
  status: JobStatus;
  source?: SourceBadge | null;
  apply_url: string;
  skills: string[];
  match_score?: number | null;
  match_reasons: string[];
  is_saved?: boolean | null;
}

export interface JobDetail extends JobListItem {
  description: string;
  responsibilities: string[];
  requirements: string[];
  benefits: string[];
  education_requirement?: string | null;
  source_url?: string | null;
  origin: string;
  view_count: number;
  duplicate_count: number;
  other_sources: SourceBadge[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Facet {
  value: string;
  count: number;
  label?: string | null;
}

export interface JobSearchResponse {
  items: JobListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  took_ms: number;
  facets: Record<string, Facet[]>;
}

export interface JobFacets {
  totals: {
    active: number;
    remote: number;
    government: number;
    internships: number;
    fresh_graduate: number;
    posted_today: number;
  };
  categories: { slug: string; label: string; count: number }[];
  cities: { name: string; slug: string; province: string; count: number }[];
}

export interface User {
  id: string;
  email: string;
  role: "user" | "admin" | "employer";
  status: string;
  email_verified: boolean;
  created_at?: string | null;
  last_login_at?: string | null;
}

export interface Profile {
  id: string;
  full_name?: string | null;
  headline?: string | null;
  phone?: string | null;
  city?: string | null;
  province?: string | null;
  education_level?: string | null;
  degree?: string | null;
  institution?: string | null;
  graduation_year?: number | null;
  years_of_experience?: number | null;
  experience_level?: string | null;
  summary?: string | null;
  skills: string[];
  preferred_locations: string[];
  preferred_categories: string[];
  preferred_job_types: string[];
  expected_salary_min?: string | number | null;
  expected_salary_max?: string | number | null;
  salary_currency: string;
  remote_preference?: string | null;
  open_to_relocation: boolean;
  profile_completion: number;
  next_steps: string[];
}

export interface MeResponse {
  user: User;
  profile?: Profile | null;
  stats: { saved_jobs?: number; active_alerts?: number };
}

export interface SavedJobItem {
  id: string;
  job: JobListItem;
  note?: string | null;
  folder?: string | null;
  created_at: string;
}

export interface JobAlert {
  id: string;
  name: string;
  keywords?: string | null;
  cities: string[];
  provinces: string[];
  categories: string[];
  employment_types: string[];
  experience_levels: string[];
  remote_only: boolean;
  government_only: boolean;
  internship_only: boolean;
  salary_min?: string | number | null;
  frequency: "instant" | "daily" | "weekly";
  is_active: boolean;
  match_count: number;
  last_matched_at?: string | null;
  last_notified_at?: string | null;
  created_at?: string | null;
}

export interface NotificationItem {
  id: string;
  type: string;
  subject: string;
  body?: string | null;
  status: string;
  payload: Record<string, unknown>;
  read_at?: string | null;
  created_at: string;
}

export interface FilterOptions {
  categories: { value: string; label: string }[];
  employment_types: { value: string; label: string }[];
  experience_levels: { value: string; label: string }[];
  provinces: { value: string; label: string }[];
  cities: { value: string; label: string; province: string }[];
  education_levels: { value: string; label: string }[];
  date_posted: { value: number; label: string }[];
  sort_options: { value: string; label: string }[];
}

export interface PublicSource {
  name: string;
  slug: string;
  type: string;
  website_url?: string | null;
  label: string;
  active_jobs: number;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string;
  };
}
