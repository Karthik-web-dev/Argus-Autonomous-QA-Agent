export const tasks = [
  ["01", "Sign-up", "Create account", "Completed", 96], ["02", "Login", "Verify session", "Completed", 84],
  ["03", "Checkout", "Validate totals", "Running", 62], ["04", "Pagination", "Check boundaries", "Completed", 100],
  ["05", "Forms", "Fuzz inputs", "Running", 48], ["06", "Search", "Reflected XSS probe", "Completed", 100],
  ["07", "Keyboard", "Tab traversal", "Completed", 78], ["08", "Editor", "State round-trip", "Running", 54],
  ["09", "Comments", "Double-submit check", "Completed", 100], ["10", "Profile", "IDOR check", "Running", 33],
] as const;

export const benchmarkApps = ["RealWorld", "OWASP Juice Shop", "AcademyBugs", "The Internet", "Practice Software Testing"];
export const sidebarItems = ["Explore", "Journeys", "Edge cases", "Findings", "Exports"];
export const runMessages = [
  { initials: "EX", name: "Explorer", time: "11:42:08", body: "Hovering row 3 to check for hidden actions…", tint: "mint" },
  { initials: "TE", name: "Tester", time: "11:42:11", body: "Running sign-up edge case 4 of 12", tint: "violet" },
  { initials: "RP", name: "Reporter", time: "11:42:14", body: "Filed [P1] Sign-up with valid credentials returns 500 — Reproduced 5/5", tint: "gold" },
];

export const trustRows = [["◉", "Chromium", "Confirmed"], ["◉", "WebKit", "Confirmed"], ["▣", "Mobile 375 × 667", "Confirmed"], ["◌", "Fresh session", "Verifying…"]] as const;
export const roleCases = [
  ["Sign up with valid credentials", "Auth", "P1", "Failed"], ["Create article", "Editor", "P2", "Passed"],
  ["Paginate feed", "Feed", "P2", "Passed"], ["Tab through form", "A11y", "P3", "Passed"],
] as const;
export const workers = [
  ["tester-01", "Sign-up edge cases", 84], ["tester-02", "Checkout totals", 66], ["tester-03", "Pagination", 100], ["tester-04", "XSS probes", 48],
  ["explorer-01", "Hover probe", 74], ["explorer-02", "State graph", 92], ["vision-01", "Canvas check", 35], ["redteam-01", "WebKit replay", 63],
  ["redteam-02", "Mobile replay", 51], ["reporter-01", "Deduplication", 89], ["tester-05", "Form validation", 72], ["explorer-03", "Keyboard path", 58],
  ["reporter-02", "Evidence bundle", 94],
] as const;
export const useCases = ["Exploratory Testing", "Public URL Scan", "Release Checks", "Regression Suites", "PR Review", "Coding-Agent Verification", "Accessibility Audit"];
export const footerColumns = [
  { title: "Product", links: ["Product", "Benchmark", "Docs", "Changelog"] },
  { title: "Use Cases", links: ["Exploratory Testing", "Public URL Scan", "Release Checks", "Regression Suites", "PR Review"] },
  { title: "Resources", links: ["Docs", "Bug Manifest", "Blog", "GitHub"] },
  { title: "Company", links: ["About", "Roadmap", "Security", "Trust Center"] },
  { title: "Connect", links: ["Contact", "X", "LinkedIn", "GitHub"] },
];

export const landingCopy = {
  nav: { home: "Argus home", signIn: "Sign in", getStarted: "Get Started" },
  hero: {
    title: "Test your web app the way a careful human would.",
    description: "Argus is an autonomous QA agent. It explores your app, runs real browser tests, and files bug reports with proof. Every passing journey becomes a Playwright test you keep.",
    scan: "Run a scan", benchmark: "View benchmark", windowTitle: "Argus - Focus Mode - conduit-demo",
    workspace: "Conduit Demo", agentsLabel: "AGENTS", liveChannel: "# live-run", findingCount: "12 findings",
    scoreboard: "Scoreboard: found 19/25 planted bugs - 2 false positives - 8 Playwright tests exported", cursorLabel: "Argus Agent",
    sampleData: "Sample data", agentNames: ["Explorer", "Tester", "Red Team"],
  },
  benchmark: { title: "Benchmarked on" },
  tasks: { title: "Any journey. Any flow. Infinite tests." },
  trust: {
    title: "Findings that", titleLineTwo: "earn trust",
    description: "Every bug passes an Evidence Gate and an independent Red Team before it is reported. No claim without a receipt.",
    evidenceLabel: "Argus Evidence Gate - replayed in fresh browser contexts", replayTitle: "Replay results",
    reproduced: "Reproduced 5/5 in fresh contexts", evidenceAction: "View evidence", deterministic: "Deterministic, no LLM in this path",
    redTeamLabel: "Argus Red Team - different model, never sees the Explorer's reasoning", verificationRun: "VERIFICATION RUN",
    sampleBug: "[P1] Sign-up returns 500", confirmed: "CONFIRMED", passwordLabel: "Password", password: "••••••••••••", verifyAction: "Verify finding",
    captions: [
      { title: "Evidence Gate", description: "Replays each finding in fresh browser contexts and rejects anything it cannot reproduce." },
      { title: "Red Team", description: "A separate model tries to disprove each finding before it reaches you." },
      { title: "Every receipt", description: "Network trace, console log, screenshots, and a Playwright repro for each report." },
    ],
    passwordField: "••••••••••••", traceStatus: "500", traceRequest: "POST /api/users", traceLabel: "NETWORK TRACE",
    vaultRows: ["Enrollment API", "Updated profile", "Payment flow", "Login session"], sampleData: "Sample data",
  },
  roles: {
    title: "A QA team that", titleLineTwo: "works like people do",
    description: "Six roles, with LLM reasoning only where judgment is needed. They explore, test, verify, and report, then hand you tests you can run without us.",
    tabs: ["Explorer", "Tester", "Evidence Gate", "Reporter"], columns: ["TEST", "JOURNEY", "SEVERITY", "STATUS"],
    captions: [
      { title: "Six roles, one pipeline", description: "Explorer, Tester, Vision, Evidence Gate, Red Team, Reporter. LLMs only where judgment is required." },
      { title: "One browser or many", description: "Isolated browser contexts and per-test data run in parallel without colliding." },
    ],
  },
  useCases: {
    title: "Built for teams", titleLineTwo: "without a QA hire", phoneKicker: "ARGUS FINDING", phoneTitle: "Bug report", sampleData: "Sample data",
    bugTitle: "[P1] Sign-up returns 500", reproduced: "Reproduced 5/5", expected: "EXPECTED", expectedBody: "Account created; open dashboard",
    actual: "ACTUAL", actualBody: "HTTP 500; sign-up fails", openRepro: "Open repro", roadmap: "Roadmap",
  },
  console: {
    title: "Watch every run.", titleLineTwo: "Replay every step.",
    description: "The Argus console shows the live browser, the findings feed, and the scoreboard. Open any report and replay it step by step.",
    link: "Explore the product", browserAddress: "console.argus.dev", home: "Home", runs: "RUNS", reports: "REPORTS",
    findings: "Findings", exports: "Exports", search: "Search reports…", runTitle: "RUN #14 - CONDUIT DEMO",
    runSubtitle: "Explore, test, verify, report", runScan: "Run Scan", runJourney: "Run Journey", statLabels: ["FOUND", "FALSE POSITIVES", "REPRODUCED"],
    statValues: ["19/25", "2", "5/5"], recentRuns: ["Conduit Demo", "Juice Shop", "AcademyBugs"],
    runStatus: ["Completed", "Completed", "Running"],
    sampleData: "Sample data", tableHead: ["STATUS", "TASK", "RESULT"], runRows: [
      ["Completed", "Sign-up journey", "P1 · 5/5"], ["Completed", "Pagination edges", "Passed"], ["Running", "Keyboard traversal", "In progress"],
    ],
  },
  mcp: {
    title: "Plug QA into your", titleLineTwo: "coding agent", description: "The Argus MCP server lets Claude Code, Cursor, and Codex pull evidence-backed bugs, read the repro, and verify the fix.",
    roadmap: "Roadmap", link: "Explore the MCP server", fileTitle: "get-bugs.mcp", callComment: "// MCP tool call", responseComment: "// Response",
    call: "argus.get_bugs", repoUrl: "github.com/acme/conduit", findingId: "f_7a3b", severity: "P1",
    bugTitle: "Sign-up with valid credentials returns 500", reproPath: "tests/repro/f_7a3b.spec.ts",
  },
  cta: { title: "Give Your App", titleLineTwo: "a QA Engineer", description: "Paste a URL and get an evidence-backed report in minutes." },
  footer: {
    askArgus: "How could I use Argus", askClaude: "Ask Claude", askChatGPT: "Ask ChatGPT", build: "Hackathon build - IM-02",
    english: "English", privacy: "Privacy", terms: "Terms", copyright: "© 2026 Argus. All rights reserved.",
  },
} as const;

export const navigationLinks = [["Product", "#product"], ["Benchmark", "#benchmark"], ["Use Cases", "#use-cases"], ["Roadmap", "#roadmap"], ["Docs", "#mcp"]] as const;
