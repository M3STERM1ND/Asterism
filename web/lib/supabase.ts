import { createClient } from "@supabase/supabase-js";

// The anon (publishable) key is safe in the browser: Supabase's row-level security decides what each
// signed-in person can read. Never put the service_role key here.
const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

// False until both are set (in .env.local, or in Vercel > Settings > Environment Variables). The site still
// builds without them; the portal then says what's missing instead of crashing.
export const configured = Boolean(url && key);
export const supabase = createClient(url || "https://not-configured.supabase.co", key || "not-configured");

export type Profile = {
  id: string;
  username: string;
  display_name: string;
  role: "patient" | "coach";
  bio: string;
  specialty: string;
  status: "open" | "closed";
};

export type Session = {
  id: string;
  run_id: string;
  played_at: string;
  mode: string;
  constellation: string;
  result: string;
  row: Record<string, string>;
  video_path: string | null;
};

export type Feedback = {
  id: string;
  coach_id: string;
  patient_id: string;
  text: string;
  created_at: string;
  read_at: string | null;
};
