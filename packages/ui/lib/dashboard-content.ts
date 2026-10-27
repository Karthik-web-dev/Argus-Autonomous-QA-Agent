export type Finding = {
  id: string;
  severity: "P0" | "P1" | "P2" | "P3";
  title: string;
  status: "verified" | "pending" | "rejected";
  time: string;
  detail: string;
  steps: string[];
  expected: string;
  actual: string;
  network: { method: string; path: string; status: string; duration: string };
  console: string;
  /** Real Evidence Gate replay result, e.g. "Reproduced 3/3 in fresh contexts". */
  repro?: string;
  /** "none" until the Red Team independently confirms the finding. */
  verifiedBy?: "red_team" | "none";
};

export const demoFindings: Finding[] = [
  { id: "f-01", severity: "P1", title: "Login returns 500", status: "verified", time: "14:32:08", detail: "Login returns 500 on an invalid email address.", steps: ["Navigate to /login", "Enter \"user@test\" in Email", "Enter a valid password", "Click Sign in"], expected: "A helpful validation message appears and the user stays on the login page.", actual: "The page shows an error after the login request returns HTTP 500.", network: { method: "POST", path: "/api/users/login", status: "500", duration: "1.2s" }, console: "TypeError: Cannot read properties of undefined" },
  { id: "f-02", severity: "P2", title: "Favorite counter increases twice", status: "verified", time: "14:31:44", detail: "Favoriting one article increments its displayed count by two.", steps: ["Open /feed", "Record the article's favorite count", "Click the favorite control once"], expected: "The count increases by one.", actual: "The count increases by two after a single click.", network: { method: "POST", path: "/api/articles/5/favorite", status: "200", duration: "184ms" }, console: "No console errors detected." },
  { id: "f-03", severity: "P3", title: "Pagination repeats the last item", status: "pending", time: "14:31:02", detail: "The final article on one page appears again on the next page.", steps: ["Open /feed", "Move to page two", "Compare the first item with the prior page"], expected: "Each page starts with the next unique article.", actual: "The final article from page one appears at the start of page two.", network: { method: "GET", path: "/api/articles?offset=10", status: "200", duration: "246ms" }, console: "Replay in progress. Awaiting a fresh browser context." },
  { id: "f-04", severity: "P2", title: "Comment count does not update", status: "rejected", time: "14:30:51", detail: "The comment counter appeared stale during the first check.", steps: ["Open an article", "Submit a comment", "Wait for the response"], expected: "The count updates after the comment is saved.", actual: "A fresh replay updated the count correctly; this report was rejected.", network: { method: "POST", path: "/api/articles/5/comments", status: "201", duration: "206ms" }, console: "No console errors detected on replay." },
  { id: "f-05", severity: "P2", title: "Editing an article drops its last tag", status: "verified", time: "14:30:20", detail: "Saving an edited article removes the last tag from the article.", steps: ["Open an existing article", "Edit the article body", "Save and reopen the article"], expected: "All existing tags remain attached.", actual: "The last tag is missing after the edit is saved.", network: { method: "PUT", path: "/api/articles/5", status: "200", duration: "311ms" }, console: "No console errors detected." },
  { id: "f-06", severity: "P3", title: "Whitespace email is accepted", status: "rejected", time: "14:29:12", detail: "Whitespace-only email was accepted by the first exploratory pass.", steps: ["Open account settings", "Replace email with spaces", "Save changes"], expected: "The form asks for a valid email address.", actual: "A fresh replay trimmed the value and showed the expected validation.", network: { method: "PATCH", path: "/api/user", status: "422", duration: "142ms" }, console: "No console errors detected on replay." },
];

export const runs = [
  { id: "conduit", name: "Conduit", score: "19/25", time: "2h ago", status: "complete", coverage: "72%", url: "https://demo.realworld.io" },
  { id: "staging", name: "Staging", score: "14/25", time: "yesterday", status: "complete", coverage: "64%", url: "https://staging.example.test" },
  { id: "prod", name: "Prod", score: "08/25", time: "3d ago", status: "complete", coverage: "51%", url: "https://app.example.test" },
] as const;

export const activityRoles = ["Explorer", "Tester", "Evidence Gate", "Red Team", "Reporter"];

export const evidenceFiles = ["login-500.png", "network-trace.json", "console-log.txt", "login-500.spec.ts"];
