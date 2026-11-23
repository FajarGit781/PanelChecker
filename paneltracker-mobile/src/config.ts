// Server cloud (sama dengan aplikasi desktop). Publishable key boleh ada di aplikasi:
// tanpa login key ini tidak bisa membaca/menulis apa pun (dijaga Row Level Security di server).
export const DEFAULT_URL = "https://ewwtxklxgkyflhyazueg.supabase.co";
export const DEFAULT_KEY = "sb_publishable_5pqbo5TleB5PgtLdYthD_w_dKoNi2-D";
export const BUCKET = "panel-photos";
export const LOGIN_DOMAIN = "paneltracker.local";
export const PAGE = 1000;
export const BATCH = 200;
export const APP_VERSION = "1.2.1";

declare const __PT_TEST__: boolean;
export const IS_TEST = typeof __PT_TEST__ !== "undefined" && __PT_TEST__;

export const DEFAULT_CATEGORIES = [
  "Wiring", "Mekanikal", "Setting Relay", "Komunikasi / IEC 61850", "SCADA / HMI", "Interlock",
  "Power Supply", "Material", "Dokumen", "Label & Marking", "Lainnya",
];
export const SEVERITIES = ["Critical", "Major", "Minor"] as const;
export const SEV_SHORT: Record<string, string> = { Critical: "A", Major: "B", Minor: "C" };
export const DUE_DAYS: Record<string, number> = { Critical: 3, Major: 7, Minor: 14 };
export const ISSUE_STATUSES = ["Open", "In Progress", "Ready to Verify", "Closed"] as const;
