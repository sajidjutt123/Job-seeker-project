"use client";

import { useState, type FormEvent } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Checkbox, Input, Select, Textarea } from "@/components/ui/Input";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { FilterOptions, Profile } from "@/lib/types";

const EDUCATION_LEVELS = [
  { value: "matric", label: "Matric" },
  { value: "intermediate", label: "Intermediate / FSc" },
  { value: "diploma", label: "Diploma / DAE" },
  { value: "bachelors", label: "Bachelors" },
  { value: "masters", label: "Masters / MPhil" },
  { value: "phd", label: "PhD" },
];

const EXPERIENCE_LEVELS = [
  { value: "fresh_graduate", label: "Fresh graduate" },
  { value: "entry", label: "Entry level (0–1 years)" },
  { value: "mid", label: "Mid level (2–4 years)" },
  { value: "senior", label: "Senior (5–8 years)" },
  { value: "lead", label: "Lead / Manager" },
  { value: "executive", label: "Executive" },
];

const REMOTE_PREFERENCES = [
  { value: "any", label: "No preference" },
  { value: "remote", label: "Remote only" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "On-site" },
];

const JOB_TYPES = [
  { value: "full_time", label: "Full time" },
  { value: "part_time", label: "Part time" },
  { value: "contract", label: "Contract" },
  { value: "internship", label: "Internship" },
  { value: "freelance", label: "Freelance" },
];

export function ProfileClient({
  initialProfile, options,
}: {
  initialProfile: Profile | null;
  options: FilterOptions | null;
}) {
  const toast = useToast();
  const { setProfile } = useAuth();
  const [profile, setLocalProfile] = useState<Profile | null>(initialProfile);
  const [form, setForm] = useState(() => toForm(initialProfile));
  const [skillInput, setSkillInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const completion = profile?.profile_completion ?? 0;

  const set = <K extends keyof ReturnType<typeof toForm>>(key: K, value: ReturnType<typeof toForm>[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const addSkill = () => {
    const value = skillInput.trim();
    if (!value) return;
    if (form.skills.length >= 30) {
      toast.toast("You can list up to 30 skills.");
      return;
    }
    if (!form.skills.some((s) => s.toLowerCase() === value.toLowerCase())) {
      set("skills", [...form.skills, value]);
    }
    setSkillInput("");
  };

  const toggleInList = (key: "preferred_categories" | "preferred_job_types" | "preferred_locations", value: string) => {
    const list = form[key];
    set(key, list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setFieldErrors({});
    try {
      const updated = await api.put<Profile>("/profile", {
        full_name: form.full_name || null,
        headline: form.headline || null,
        phone: form.phone || null,
        city: form.city || null,
        education_level: form.education_level || null,
        degree: form.degree || null,
        institution: form.institution || null,
        graduation_year: form.graduation_year ? Number(form.graduation_year) : null,
        years_of_experience: form.years_of_experience ? Number(form.years_of_experience) : null,
        experience_level: form.experience_level || null,
        summary: form.summary || null,
        skills: form.skills,
        preferred_locations: form.preferred_locations,
        preferred_categories: form.preferred_categories,
        preferred_job_types: form.preferred_job_types,
        expected_salary_min: form.expected_salary_min ? Number(form.expected_salary_min) : null,
        expected_salary_max: form.expected_salary_max ? Number(form.expected_salary_max) : null,
        remote_preference: form.remote_preference || null,
        open_to_relocation: form.open_to_relocation,
      });
      setLocalProfile(updated);
      setProfile(updated);
      toast.success("Profile saved.");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFieldErrors(err.fieldErrors);
      } else {
        setError("Could not save your profile. Please try again.");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      <header>
        <h1 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">Your profile</h1>
        <p className="mt-1 text-sm text-ink-500">
          The more complete this is, the better your job recommendations become.
        </p>
      </header>

      <div className="rounded-xl border border-ink-200 bg-white p-4">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-ink-800">Profile completion</span>
          <span className="font-semibold text-brand-700">{completion}%</span>
        </div>
        <div
          className="mt-2 h-2 overflow-hidden rounded-full bg-ink-200"
          role="progressbar" aria-valuenow={completion} aria-valuemin={0} aria-valuemax={100}
        >
          <div
            className={cn("h-full rounded-full transition-all", completion >= 80 ? "bg-emerald-600" : "bg-brand-600")}
            style={{ width: `${completion}%` }}
          />
        </div>
        {profile?.next_steps && profile.next_steps.length > 0 && (
          <p className="mt-2.5 text-xs text-ink-500">Next: {profile.next_steps.join(" · ")}</p>
        )}
      </div>

      {error && (
        <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {error}
        </p>
      )}

      <Section title="About you">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Full name" value={form.full_name} error={fieldErrors.full_name}
                 onChange={(e) => set("full_name", e.target.value)} />
          <Input label="Professional headline" placeholder="e.g. Backend Engineer"
                 value={form.headline} onChange={(e) => set("headline", e.target.value)} />
          <Input label="Phone" type="tel" placeholder="03xx-xxxxxxx"
                 value={form.phone} onChange={(e) => set("phone", e.target.value)} />
          <Select label="City" placeholder="Select your city"
                  options={options?.cities.map((c) => ({ value: c.label, label: c.label })) ?? []}
                  value={form.city} onChange={(e) => set("city", e.target.value)} />
        </div>
        <Textarea label="Short summary" maxLength={4000} placeholder="A couple of lines about your experience and what you are looking for."
                  value={form.summary} onChange={(e) => set("summary", e.target.value)} className="mt-4" />
      </Section>

      <Section title="Education">
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Highest education" placeholder="Select level" options={EDUCATION_LEVELS}
                  value={form.education_level} onChange={(e) => set("education_level", e.target.value)} />
          <Input label="Degree" placeholder="e.g. BS Computer Science"
                 value={form.degree} onChange={(e) => set("degree", e.target.value)} />
          <Input label="Institution" placeholder="e.g. FAST NUCES"
                 value={form.institution} onChange={(e) => set("institution", e.target.value)} />
          <Input label="Graduation year" type="number" min={1950} max={2100} placeholder="e.g. 2024"
                 value={form.graduation_year} onChange={(e) => set("graduation_year", e.target.value)} />
        </div>
      </Section>

      <Section title="Experience">
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Experience level" placeholder="Select level" options={EXPERIENCE_LEVELS}
                  value={form.experience_level} onChange={(e) => set("experience_level", e.target.value)} />
          <Input label="Years of experience" type="number" min={0} max={60}
                 value={form.years_of_experience} onChange={(e) => set("years_of_experience", e.target.value)} />
        </div>
      </Section>

      <Section title="Skills" hint="Add the skills you want to be matched on.">
        <div className="flex gap-2">
          <Input
            placeholder="e.g. Python"
            value={skillInput}
            onChange={(e) => setSkillInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addSkill();
              }
            }}
            wrapperClassName="flex-1"
            aria-label="Add a skill"
          />
          <Button type="button" variant="outline" onClick={addSkill}>Add</Button>
        </div>
        {form.skills.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-1.5">
            {form.skills.map((skill) => (
              <li key={skill}>
                <button
                  type="button"
                  onClick={() => set("skills", form.skills.filter((s) => s !== skill))}
                  className="inline-flex items-center gap-1.5 rounded-md bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-800 ring-1 ring-inset ring-brand-200 transition-colors hover:bg-brand-100"
                  aria-label={`Remove ${skill}`}
                >
                  {skill}
                  <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                  </svg>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Job preferences" hint="Used to rank recommendations and alerts.">
        <div className="space-y-4">
          <Fieldset legend="Preferred categories">
            <div className="flex flex-wrap gap-1.5">
              {(options?.categories ?? []).map((category) => (
                <Chip
                  key={category.value}
                  active={form.preferred_categories.includes(category.value)}
                  onClick={() => toggleInList("preferred_categories", category.value)}
                >
                  {category.label}
                </Chip>
              ))}
            </div>
          </Fieldset>

          <Fieldset legend="Preferred locations">
            <div className="flex flex-wrap gap-1.5">
              {(options?.cities ?? []).slice(0, 14).map((city) => (
                <Chip
                  key={city.value}
                  active={form.preferred_locations.includes(city.label)}
                  onClick={() => toggleInList("preferred_locations", city.label)}
                >
                  {city.label}
                </Chip>
              ))}
            </div>
          </Fieldset>

          <Fieldset legend="Preferred job types">
            <div className="flex flex-wrap gap-1.5">
              {JOB_TYPES.map((type) => (
                <Chip
                  key={type.value}
                  active={form.preferred_job_types.includes(type.value)}
                  onClick={() => toggleInList("preferred_job_types", type.value)}
                >
                  {type.label}
                </Chip>
              ))}
            </div>
          </Fieldset>

          <div className="grid gap-4 sm:grid-cols-3">
            <Input label="Expected salary (min, PKR/month)" type="number" min={0} step={5000}
                   value={form.expected_salary_min} onChange={(e) => set("expected_salary_min", e.target.value)} />
            <Input label="Expected salary (max)" type="number" min={0} step={5000}
                   value={form.expected_salary_max} onChange={(e) => set("expected_salary_max", e.target.value)} />
            <Select label="Work mode preference" options={REMOTE_PREFERENCES}
                    value={form.remote_preference} onChange={(e) => set("remote_preference", e.target.value)} />
          </div>

          <Checkbox
            label="I am open to relocating for the right role"
            checked={form.open_to_relocation}
            onChange={(e) => set("open_to_relocation", e.target.checked)}
          />
        </div>
      </Section>

      <div className="sticky bottom-0 -mx-4 border-t border-ink-200 bg-white/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-xl sm:border sm:px-4">
        <Button type="submit" loading={saving} fullWidth className="sm:w-auto">
          Save profile
        </Button>
      </div>
    </form>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-ink-200 bg-white p-5">
      <h2 className="text-sm font-bold text-ink-900">{title}</h2>
      {hint && <p className="mt-0.5 mb-3 text-xs text-ink-500">{hint}</p>}
      <div className={hint ? "" : "mt-4"}>{children}</div>
    </section>
  );
}

function Fieldset({ legend, children }: { legend: string; children: React.ReactNode }) {
  return (
    <fieldset>
      <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">{legend}</legend>
      {children}
    </fieldset>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
        active
          ? "border-brand-600 bg-brand-700 text-white"
          : "border-ink-200 bg-white text-ink-700 hover:border-brand-300 hover:bg-brand-50",
      )}
    >
      {children}
    </button>
  );
}

function toForm(profile: Profile | null) {
  return {
    full_name: profile?.full_name ?? "",
    headline: profile?.headline ?? "",
    phone: profile?.phone ?? "",
    city: profile?.city ?? "",
    education_level: profile?.education_level ?? "",
    degree: profile?.degree ?? "",
    institution: profile?.institution ?? "",
    graduation_year: profile?.graduation_year ? String(profile.graduation_year) : "",
    years_of_experience: profile?.years_of_experience !== null && profile?.years_of_experience !== undefined
      ? String(profile.years_of_experience) : "",
    experience_level: profile?.experience_level ?? "",
    summary: profile?.summary ?? "",
    skills: profile?.skills ?? [],
    preferred_locations: profile?.preferred_locations ?? [],
    preferred_categories: profile?.preferred_categories ?? [],
    preferred_job_types: profile?.preferred_job_types ?? [],
    expected_salary_min: profile?.expected_salary_min ? String(profile.expected_salary_min) : "",
    expected_salary_max: profile?.expected_salary_max ? String(profile.expected_salary_max) : "",
    remote_preference: profile?.remote_preference ?? "",
    open_to_relocation: profile?.open_to_relocation ?? false,
  };
}
