import * as NodeAssert from "node:assert/strict";
import * as NodeChildProcess from "node:child_process";
import * as NodeCrypto from "node:crypto";
import * as NodeFS from "node:fs";
import * as NodeOS from "node:os";
import * as NodePath from "node:path";
import * as NodeSqlite from "node:sqlite";
import * as NodeTest from "node:test";
import * as NodeURL from "node:url";

import {
  httpJevCall,
  JevError,
  parseRouteInput,
  requestDigest,
  route,
  type JevCall,
} from "../src/route.ts";
import { handle } from "../src/server.ts";
import { defaultDbPath, JevStore } from "../src/store.ts";

const input = {
  requestId: "req-1",
  taskSummary: "Rename a variable across one file.",
  policy: "Cheapest combination that will succeed.",
  candidates: [
    { model: "gpt-5.5", reasoningEffort: "low" },
    { model: "gpt-5.5", reasoningEffort: "high" },
  ],
};

const answer = (choice: string, probabilities: Record<string, number>) => ({
  model: "jev-2026-10",
  answers: { route: { type: "choice", choice, confidence: probabilities[choice], probabilities } },
});

const countingCall = (response: unknown) => {
  const calls: unknown[] = [];
  const call: JevCall = async (body) => {
    calls.push(body);
    return response;
  };
  return { call, calls };
};

const tempDb = () =>
  NodePath.join(
    NodeFS.mkdtempSync(NodePath.join(NodeOS.tmpdir(), "jev-mcp-")),
    "jev",
    "jev.sqlite",
  );

NodeTest.test("routes to the candidate Jev chose and stores it", async () => {
  const store = new JevStore(tempDb());
  const { call, calls } = countingCall(
    answer("c0", { c0: 0.8, c1: 0.1, insufficient_evidence: 0.1 }),
  );
  const result = await route(input, { store, call });
  NodeAssert.equal(result.model, "gpt-5.5");
  NodeAssert.equal(result.reasoningEffort, "low");
  NodeAssert.equal(result.confidence, 0.8);
  NodeAssert.equal(result.replayed, false);
  NodeAssert.equal(calls.length, 1);
  NodeAssert.deepEqual(Object.keys((calls[0] as any).questions.route.criteria), [
    "c0",
    "c1",
    "insufficient_evidence",
  ]);
});

NodeTest.test("replays a stored decision across restarts without calling Jev", async () => {
  const path = tempDb();
  const first = new JevStore(path);
  const decided = await route(input, {
    store: first,
    call: countingCall(answer("c1", { c0: 0.1, c1: 0.8, insufficient_evidence: 0.1 })).call,
  });
  first.close();
  const { call, calls } = countingCall(null);
  const replay = await route(input, { store: new JevStore(path), call });
  NodeAssert.equal(calls.length, 0);
  NodeAssert.equal(replay.replayed, true);
  NodeAssert.equal(replay.decisionId, decided.decisionId);
  NodeAssert.equal(replay.reasoningEffort, "high");
});

NodeTest.test("rejects a reused requestId with different input", async () => {
  const store = new JevStore(":memory:");
  await route(input, {
    store,
    call: countingCall(answer("c0", { c0: 0.8, c1: 0.1, insufficient_evidence: 0.1 })).call,
  });
  await NodeAssert.rejects(
    route({ ...input, policy: "Highest quality." }, { store, call: countingCall(null).call }),
    (error: unknown) => error instanceof JevError && error.code === "duplicate-request",
  );
});

NodeTest.test(
  "surfaces insufficient evidence and malformed answers as errors, storing no decision",
  async () => {
    const store = new JevStore(":memory:");
    await NodeAssert.rejects(
      route(input, {
        store,
        call: countingCall(
          answer("insufficient_evidence", { c0: 0.2, c1: 0.2, insufficient_evidence: 0.6 }),
        ).call,
      }),
      (error: unknown) => error instanceof JevError && error.code === "insufficient-evidence",
    );
    await NodeAssert.rejects(
      route(
        { ...input, requestId: "req-2" },
        {
          store,
          call: countingCall(answer("c0", { c0: 0.4, c1: 0.5, insufficient_evidence: 0.1 })).call,
        },
      ),
      (error: unknown) => error instanceof JevError && error.code === "invalid-response",
    );
    NodeAssert.equal(store.get("req-1")?.decision, null);
  },
);

NodeTest.test("rejects duplicate candidates and empty summaries before calling Jev", async () => {
  const { call, calls } = countingCall(null);
  const store = new JevStore(":memory:");
  for (const bad of [
    { ...input, candidates: [input.candidates[0], input.candidates[0]] },
    { ...input, taskSummary: " " },
  ]) {
    await NodeAssert.rejects(
      route(bad, { store, call }),
      (e: unknown) => e instanceof JevError && e.code === "invalid-input",
    );
  }
  NodeAssert.equal(calls.length, 0);
});

NodeTest.test("imports legacy jev_execution_requests rows once", () => {
  const store = new JevStore(":memory:");
  const rows = [{ command_id: "cmd-1", request_digest: "abc" }];
  NodeAssert.equal(store.importLegacy(rows), 1);
  NodeAssert.equal(store.importLegacy(rows), 0);
  NodeAssert.deepEqual(store.get("cmd-1"), {
    requestId: "cmd-1",
    requestDigest: "abc",
    decision: null,
  });
});

NodeTest.test("stores data under T3CODE_HOME/jev, not in T3's database", () => {
  NodeAssert.equal(
    defaultDbPath({ T3CODE_HOME: "D:\\t3home" }),
    NodePath.join("D:\\t3home", "jev", "jev.sqlite"),
  );
});

NodeTest.test("answers MCP initialize and tools/list", async () => {
  const deps = { store: new JevStore(":memory:"), call: countingCall(null).call };
  const init: any = await handle(
    { jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-06-18" } },
    deps,
  );
  NodeAssert.deepEqual(init.result.serverInfo, { name: "jev", version: "0.1.0" });
  const list: any = await handle({ jsonrpc: "2.0", id: 2, method: "tools/list" }, deps);
  NodeAssert.deepEqual(
    list.result.tools.map((t: { name: string }) => t.name),
    ["jev_route"],
  );
  NodeAssert.equal(
    await handle({ jsonrpc: "2.0", method: "notifications/initialized" }, deps),
    undefined,
  );
});

NodeTest.test("runs as a stdio MCP process and reports a missing key as a tool error", () => {
  const dir = NodeFS.mkdtempSync(NodePath.join(NodeOS.tmpdir(), "jev-mcp-proc-"));
  const main = NodeURL.fileURLToPath(new URL("../src/main.ts", import.meta.url));
  const lines = [
    { jsonrpc: "2.0", id: 1, method: "initialize", params: {} },
    { jsonrpc: "2.0", method: "notifications/initialized" },
    {
      jsonrpc: "2.0",
      id: 2,
      method: "tools/call",
      params: { name: "jev_route", arguments: input },
    },
  ];
  const run = NodeChildProcess.spawnSync(process.execPath, [main], {
    input: lines.map((l) => JSON.stringify(l)).join("\n") + "\n",
    env: { ...process.env, T3CODE_HOME: dir, TYPESAFE_API_KEY: "" },
    encoding: "utf8",
  });
  NodeAssert.equal(run.status, 0, run.stderr);
  const responses = run.stdout
    .trim()
    .split("\n")
    .map((l) => JSON.parse(l));
  NodeAssert.deepEqual(
    responses.map((r) => r.id),
    [1, 2],
  );
  NodeAssert.equal(responses[1].result.isError, true);
  NodeAssert.equal(JSON.parse(responses[1].result.content[0].text).code, "missing-key");
  NodeFS.writeFileSync(
    NodePath.join(dir, "legacy.json"),
    JSON.stringify([{ command_id: "cmd-9", request_digest: "d" }]),
  );
  const imported = NodeChildProcess.spawnSync(
    process.execPath,
    [main, "--import-legacy", NodePath.join(dir, "legacy.json")],
    {
      env: { ...process.env, T3CODE_HOME: dir },
      encoding: "utf8",
    },
  );
  NodeAssert.equal(JSON.parse(imported.stdout).imported, 1);
});

NodeTest.test("sends a trimmed API key", async () => {
  const headers: string[] = [];
  const fetcher = (async (_url: unknown, init: { headers: Record<string, string> }) => {
    headers.push(init.headers.Authorization!);
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  }) as unknown as typeof fetch;
  await httpJevCall(fetcher, () => "  secret-key\n")({}, new AbortController().signal);
  NodeAssert.deepEqual(headers, ["Bearer secret-key"]);
});

NodeTest.test("waits for another process's write instead of failing busy", async () => {
  const path = tempDb();
  const store = new JevStore(path);
  const holder = new NodeSqlite.DatabaseSync(path);
  holder.exec("BEGIN IMMEDIATE");
  const storeUrl = NodeURL.pathToFileURL(
    NodePath.resolve(import.meta.dirname, "../src/store.ts"),
  ).href;
  const script = `import { JevStore } from ${JSON.stringify(storeUrl)};
new JevStore(${JSON.stringify(path)}).claim("req-busy", "d", Date.now(), 1000);`;
  const worker = NodeChildProcess.spawn(process.execPath, ["--input-type=module", "-e", script], {
    stdio: ["ignore", "ignore", "pipe"],
  });
  let stderr = "";
  worker.stderr.on("data", (chunk) => (stderr += chunk));
  const exited = new Promise<number | null>((resolve) => worker.on("exit", resolve));
  await new Promise((resolve) => setTimeout(resolve, 500));
  NodeAssert.equal(store.get("req-busy"), undefined);
  holder.exec("COMMIT");
  NodeAssert.equal(await exited, 0, stderr);
  NodeAssert.equal(store.get("req-busy")?.requestDigest, "d");
  holder.close();
});

const slowCall = (response: unknown, ms = 200) => {
  const calls: unknown[] = [];
  const call: JevCall = async (body) => {
    calls.push(body);
    await new Promise((resolve) => setTimeout(resolve, ms));
    return response;
  };
  return { call, calls };
};

NodeTest.test(
  "coalesces concurrent calls for one requestId across stores on the same file",
  async () => {
    const path = tempDb();
    const { call, calls } = slowCall(
      answer("c0", { c0: 0.8, c1: 0.1, insufficient_evidence: 0.1 }),
    );
    const [a, b] = await Promise.all([
      route(input, { store: new JevStore(path), call }),
      route(input, { store: new JevStore(path), call }),
    ]);
    NodeAssert.equal(calls.length, 1);
    NodeAssert.equal(a.decisionId, b.decisionId);
    NodeAssert.deepEqual([a.replayed, b.replayed].sort(), [false, true]);
  },
);

NodeTest.test("a failed call releases the claim so the next caller asks again", async () => {
  const store = new JevStore(":memory:");
  const failing: JevCall = async () => {
    throw new JevError("transport");
  };
  await NodeAssert.rejects(
    route(input, { store, call: failing }),
    (e: unknown) => e instanceof JevError && e.code === "transport",
  );
  const { call, calls } = countingCall(
    answer("c1", { c0: 0.1, c1: 0.8, insufficient_evidence: 0.1 }),
  );
  const started = Date.now();
  const result = await route(input, { store, call });
  NodeAssert.equal(calls.length, 1);
  NodeAssert.equal(result.reasoningEffort, "high");
  NodeAssert.ok(Date.now() - started < 1_000);
});

NodeTest.test("answers non-object JSON with Invalid Request and keeps serving", () => {
  const main = NodeURL.fileURLToPath(new URL("../src/main.ts", import.meta.url));
  const dir = NodeFS.mkdtempSync(NodePath.join(NodeOS.tmpdir(), "jev-mcp-bad-"));
  const run = NodeChildProcess.spawnSync(process.execPath, [main], {
    input: ["null", "[1]", '"x"', '{"jsonrpc":"2.0","id":7,"method":"ping"}'].join("\n") + "\n",
    env: { ...process.env, T3CODE_HOME: dir },
    encoding: "utf8",
  });
  NodeAssert.equal(run.status, 0, run.stderr);
  const responses = run.stdout
    .trim()
    .split("\n")
    .map((l) => JSON.parse(l));
  NodeAssert.deepEqual(
    responses.map((r) => r.error?.code ?? r.id),
    [-32600, -32600, -32600, 7],
  );
});

NodeTest.test("a late release does not drop a claim another caller took over", () => {
  const store = new JevStore(":memory:");
  const first = store.claim("req-x", "d", 0, 10);
  const second = store.claim("req-x", "d", 100, 10_000);
  NodeAssert.equal(first.state, "claimed");
  NodeAssert.equal(second.state, "claimed");
  store.release("req-x", first.token!);
  NodeAssert.equal(store.claim("req-x", "d", 200, 10_000).state, "pending");
  store.release("req-x", second.token!);
  NodeAssert.equal(store.claim("req-x", "d", 300, 10_000).state, "claimed");
});

const isCode = (code: string) => (e: unknown) => e instanceof JevError && e.code === code;

const three = {
  ...input,
  requestId: "req-3",
  candidates: [
    { model: "gpt-5.5", reasoningEffort: "low" },
    { model: "gpt-5.5", reasoningEffort: "medium" },
    { model: "gpt-5.5", reasoningEffort: "high" },
  ],
};

NodeTest.test("rejects a choice below 1.5x a uniform pick and stores nothing", async () => {
  // Two candidates: the floor is max(0.5, 1.5 / 2) = 0.75.
  const store = new JevStore(":memory:");
  await NodeAssert.rejects(
    route(input, {
      store,
      call: countingCall(answer("c0", { c0: 0.7, c1: 0.2, insufficient_evidence: 0.1 })).call,
    }),
    isCode("low-confidence"),
  );
  NodeAssert.equal(store.get("req-1")?.decision, null);
  const { call, calls } = countingCall(
    answer("c1", { c0: 0.1, c1: 0.8, insufficient_evidence: 0.1 }),
  );
  NodeAssert.equal((await route(input, { store, call })).reasoningEffort, "high");
  NodeAssert.equal(calls.length, 1);
});

NodeTest.test("rejects a choice that barely leads the runner-up", async () => {
  // Three candidates: confidence floor 0.5 passes, but the lead of 0.1 is under 0.15.
  await NodeAssert.rejects(
    route(three, {
      store: new JevStore(":memory:"),
      call: countingCall(
        answer("c0", { c0: 0.5, c1: 0.4, c2: 0.05, insufficient_evidence: 0.05 }),
      ).call,
    }),
    isCode("low-confidence"),
  );
  const ok = await route(three, {
    store: new JevStore(":memory:"),
    call: countingCall(answer("c2", { c0: 0.3, c1: 0.1, c2: 0.55, insufficient_evidence: 0.05 }))
      .call,
  });
  NodeAssert.equal(ok.reasoningEffort, "high");
});

NodeTest.test("lets callers raise the floors but never lower them", async () => {
  const { call, calls } = countingCall(null);
  for (const bad of [
    { ...three, minConfidence: 0.3 },
    { ...three, minMargin: 0.05 },
    { ...three, minConfidence: 1.5 },
    { ...three, minMargin: "0.5" },
    { ...three, securitySensitive: "yes" },
  ]) {
    await NodeAssert.rejects(
      route(bad, { store: new JevStore(":memory:"), call }),
      isCode("invalid-input"),
    );
  }
  NodeAssert.equal(calls.length, 0);
  const strong = answer("c2", { c0: 0.1, c1: 0.1, c2: 0.75, insufficient_evidence: 0.05 });
  await NodeAssert.rejects(
    route(
      { ...three, minConfidence: 0.8 },
      { store: new JevStore(":memory:"), call: countingCall(strong).call },
    ),
    isCode("low-confidence"),
  );
  await NodeAssert.rejects(
    route(
      { ...three, minMargin: 0.7 },
      { store: new JevStore(":memory:"), call: countingCall(strong).call },
    ),
    isCode("low-confidence"),
  );
});

NodeTest.test("security-sensitive requests offer Jev only high, xhigh or max effort", async () => {
  const { call, calls } = countingCall(
    answer("c1", { c0: 0.1, c1: 0.85, insufficient_evidence: 0.05 }),
  );
  const result = await route(
    {
      ...input,
      requestId: "req-sec",
      securitySensitive: true,
      candidates: [
        { model: "gpt-5.4-mini", reasoningEffort: "low" },
        { model: "gpt-5.5", reasoningEffort: "high" },
        { model: "gpt-5.4-mini" },
        { model: "gpt-5.5", reasoningEffort: "XHigh" },
        { model: "gpt-5.5", reasoningEffort: "medium" },
      ],
    },
    { store: new JevStore(":memory:"), call },
  );
  const criteria = (calls[0] as any).questions.route.criteria;
  NodeAssert.deepEqual(Object.keys(criteria), ["c0", "c1", "insufficient_evidence"]);
  NodeAssert.deepEqual(JSON.parse(criteria.c0), { model: "gpt-5.5", reasoningEffort: "high" });
  NodeAssert.equal(result.reasoningEffort, "XHigh");
  NodeAssert.match(result.reason, /security-sensitive/);
});

NodeTest.test("security-sensitive requests without a high-effort candidate fail without calling Jev", async () => {
  const { call, calls } = countingCall(null);
  await NodeAssert.rejects(
    route(
      {
        ...input,
        securitySensitive: true,
        candidates: [{ model: "gpt-5.5", reasoningEffort: "medium" }, { model: "gpt-5.4-mini" }],
      },
      { store: new JevStore(":memory:"), call },
    ),
    (e: unknown) =>
      e instanceof JevError && e.code === "no-secure-candidate" && /strongest model/.test(e.message),
  );
  NodeAssert.equal(calls.length, 0);
});

NodeTest.test("default floors keep the original request digest; new options change it", () => {
  const legacy = NodeCrypto.createHash("sha256")
    .update(
      JSON.stringify({
        taskSummary: input.taskSummary,
        policy: input.policy,
        candidates: input.candidates,
      }),
    )
    .digest("hex");
  NodeAssert.equal(requestDigest(parseRouteInput(input)), legacy);
  NodeAssert.notEqual(
    requestDigest(parseRouteInput({ ...input, securitySensitive: true })),
    legacy,
  );
  NodeAssert.notEqual(requestDigest(parseRouteInput({ ...input, minConfidence: 0.9 })), legacy);
});

NodeTest.test("a stored decision below the floor is not replayed", async () => {
  const store = new JevStore(":memory:");
  const parsed = parseRouteInput({ ...input, requestId: "req-old" });
  store.claim("req-old", requestDigest(parsed), Date.now(), 1_000);
  store.complete("req-old", {
    decisionId: "d-old",
    model: "gpt-5.5",
    reasoningEffort: "low",
    reason: "stored before the floor",
    confidence: 0.28,
  });
  const { call, calls } = countingCall(null);
  await NodeAssert.rejects(
    route({ ...input, requestId: "req-old" }, { store, call }),
    isCode("low-confidence"),
  );
  NodeAssert.equal(calls.length, 0);
});

NodeTest.test("the tool schema exposes securitySensitive and says when it is required", async () => {
  const deps = { store: new JevStore(":memory:"), call: countingCall(null).call };
  const list: any = await handle({ jsonrpc: "2.0", id: 3, method: "tools/list" }, deps);
  const tool = list.result.tools[0];
  NodeAssert.equal(tool.inputSchema.properties.securitySensitive.type, "boolean");
  for (const word of ["security", "auth", "secrets", "deploy", "release", "merge", "push", "migration", "prod"])
    NodeAssert.match(tool.description, new RegExp(word));
});
