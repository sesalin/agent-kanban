import assert from "node:assert/strict";
import test from "node:test";
import worker from "./worker.mjs";

test("factory workers can access their queue and cannot dispatch tasks", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json([]));
  for (const agent of ["BRIO", "CODEX", "INSTINCT", "BACHA", "NOD", "DOT"]) {
    const env = { [`${agent}_KANBAN_TOKEN`]: "test-worker",
      [`${agent}_CF_ACCESS_CLIENT_ID`]: "test-id", [`${agent}_CF_ACCESS_CLIENT_SECRET`]: "test-secret" };
    const request = (path, method = "GET") => new Request("https://kanban-api.okehc.com" + path,
      { method, headers: { Authorization: "Bearer test-worker" } });
    assert.equal((await worker.fetch(request("/api/tasks/available"), env)).status, 200);
    assert.equal((await worker.fetch(request("/api/tasks/1/claim", "POST"), env)).status, 200);
    if (agent !== "BACHA") {
      assert.equal((await worker.fetch(request("/api/tasks/dispatch", "POST"), env)).status, 404);
    }
  }
});

test("allows n8n to dispatch, read an individual task and review over REST", async (t) => {
  const env = {
    N8N_RADARES_KANBAN_TOKEN: "test-n8n",
    N8N_RADARES_CF_ACCESS_CLIENT_ID: "n8n-id",
    N8N_RADARES_CF_ACCESS_CLIENT_SECRET: "n8n-secret",
  };
  const request = (path, method = "POST") => new Request("https://kanban-api.okehc.com" + path, {
    method,
    headers: { Authorization: "Bearer test-n8n", "Content-Type": "application/json" },
    body: method === "POST" ? '{"project_id":1,"title":"Radar"}' : undefined,
  });
  const upstream = t.mock.method(globalThis, "fetch", async () => Response.json({ id: 42 }, { status: 201 }));

  assert.equal((await worker.fetch(request("/mcp/"), env)).status, 404);
  assert.equal((await worker.fetch(request("/api/tasks", "GET"), env)).status, 404);
  assert.equal((await worker.fetch(request("/api/tasks/42/reassign"), env)).status, 404);
  assert.equal(upstream.mock.callCount(), 0);

  const response = await worker.fetch(request("/api/tasks/dispatch"), env);
  assert.equal(response.status, 201);
  assert.deepEqual(await response.json(), { id: 42 });
  const [url, options] = upstream.mock.calls[0].arguments;
  assert.equal(url, "https://kk.okehc.com/api/tasks/dispatch");
  assert.equal(options.headers.get("Authorization"), "Bearer test-n8n");
  assert.equal(options.headers.get("CF-Access-Client-Id"), "n8n-id");
  assert.equal(options.headers.get("CF-Access-Client-Secret"), "n8n-secret");

  await worker.fetch(request("/api/tasks/42", "GET"), env);
  await worker.fetch(request("/api/tasks/42/review"), env);
  assert.deepEqual(upstream.mock.calls.slice(1).map(({ arguments: [url, options] }) => [url, options.method]), [
    ["https://kk.okehc.com/api/tasks/42", "GET"],
    ["https://kk.okehc.com/api/tasks/42/review", "POST"],
  ]);
});

test("restricts upstream access to Bacha and refuses Access redirects", async (t) => {
  const env = {
    BACHA_KANBAN_TOKEN: "test-bacha",
    BACHA_CF_ACCESS_CLIENT_ID: "test-id",
    BACHA_CF_ACCESS_CLIENT_SECRET: "test-secret",
  };
  const request = (path, token = env.BACHA_KANBAN_TOKEN) => new Request(
    "https://kanban-api.okehc.com" + path,
    { headers: { Authorization: `Bearer ${token}`, "CF-Access-Client-Secret": "spoofed", Cookie: "ignored" } },
  );
  const upstream = t.mock.method(globalThis, "fetch", async () => Response.json([]));

  assert.equal((await worker.fetch(request("/api/tasks", "other-agent"), env)).status, 401);
  assert.equal((await worker.fetch(request("/api/tokens"), env)).status, 404);
  assert.equal((await worker.fetch(request("/mcp/", "other-agent"), env)).status, 401);
  assert.equal((await worker.fetch(request("/mcp/other"), env)).status, 404);
  assert.equal(upstream.mock.callCount(), 0);

  const response = await worker.fetch(request("/api/tasks?project_id=1"), env);
  assert.deepEqual(await response.json(), []);
  const [url, options] = upstream.mock.calls[0].arguments;
  assert.equal(url, "https://kk.okehc.com/api/tasks?project_id=1");
  assert.equal(options.redirect, "manual");
  assert.equal(options.headers.get("Authorization"), "Bearer test-bacha");
  assert.equal(options.headers.get("CF-Access-Client-Secret"), "test-secret");
  assert.equal(options.headers.get("Cookie"), null);

  upstream.mock.mockImplementation(async () => Response.redirect("https://login.example.test/"));
  const blocked = await worker.fetch(request("/api/tasks"), env);
  assert.equal(blocked.status, 502);
  assert.equal(blocked.headers.get("Location"), null);
});

test("forwards MCP headers, event streams and empty notification replies", async (t) => {
  const env = {
    BACHA_KANBAN_TOKEN: "test-bacha",
    BACHA_CF_ACCESS_CLIENT_ID: "test-id",
    BACHA_CF_ACCESS_CLIENT_SECRET: "test-secret",
  };
  const request = () => new Request("https://kanban-api.okehc.com/mcp", {
    method: "POST",
    body: "{}",
    headers: {
      Authorization: "Bearer test-bacha",
      Accept: "application/json, text/event-stream",
      "Content-Type": "application/json",
      "MCP-Protocol-Version": "2025-11-25",
      "Mcp-Session-Id": "test-session",
    },
  });
  const event = "event: message\ndata: {}\n\n";
  const upstream = t.mock.method(globalThis, "fetch", async () => new Response(event, {
    headers: { "Content-Type": "text/event-stream", "Mcp-Session-Id": "test-session" },
  }));
  const response = await worker.fetch(request(), env);
  assert.equal(response.headers.get("Content-Type"), "text/event-stream");
  assert.equal(response.headers.get("Mcp-Session-Id"), "test-session");
  assert.equal(await response.text(), event);
  const [url, options] = upstream.mock.calls[0].arguments;
  assert.equal(url, "https://kk.okehc.com/mcp/");
  assert.equal(options.headers.get("Accept"), "application/json, text/event-stream");
  assert.equal(options.headers.get("MCP-Protocol-Version"), "2025-11-25");
  assert.equal(options.headers.get("Mcp-Session-Id"), "test-session");

  upstream.mock.mockImplementation(async () => new Response(null, { status: 202 }));
  const notification = await worker.fetch(request(), env);
  assert.equal(notification.status, 202);
  assert.equal(await notification.text(), "");
});


test("only n8n may invoke bounded factory file operations", async (t) => {
  const env = {};
  for (const agent of ["N8N_RADARES", "NOD", "BACHA", "BRIO", "DOT"]) {
    env[`${agent}_KANBAN_TOKEN`] = agent;
    env[`${agent}_CF_ACCESS_CLIENT_ID`] = "id";
    env[`${agent}_CF_ACCESS_CLIENT_SECRET`] = "secret";
  }
  const upstream = t.mock.method(globalThis, "fetch", async () => Response.json({ event_id: "example" }));
  for (const agent of ["NOD", "BACHA", "BRIO", "DOT"]) {
    const request = new Request("https://kanban-api.okehc.com/api/factory/files/input", {
      method: "POST", headers: { Authorization: `Bearer ${agent}` }, body: "{}",
    });
    assert.equal((await worker.fetch(request, env)).status, 404);
  }
  assert.equal(upstream.mock.callCount(), 0);
  for (const operation of ["input", "verify", "specs", "wakeup", "release", "unknown"]) {
    const request = new Request(`https://kanban-api.okehc.com/api/factory/files/${operation}`, {
      method: "POST", headers: { Authorization: "Bearer N8N_RADARES" }, body: "{}",
    });
    assert.equal((await worker.fetch(request, env)).status, operation === "unknown" ? 404 : 200);
  }
  assert.equal(upstream.mock.callCount(), 5);
});


test("coordinator and report acknowledgements are exclusive to n8n", async (t) => {
  const env = {N8N_RADARES_CF_ACCESS_CLIENT_ID: "id", N8N_RADARES_CF_ACCESS_CLIENT_SECRET: "secret"};
  const mock = t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "https://kk.okehc.com/api/factory/leads");
    assert.equal(options.headers.Authorization, undefined);
    return Response.json({ok:true}, {status:201});
  });
  const endpoint = "https://kanban-api.okehc.com/api/factory/leads";
  assert.equal((await worker.fetch(new Request(endpoint, {method:"OPTIONS"}), env)).status, 204);
  assert.equal((await worker.fetch(new Request(endpoint, {method:"POST",body:"{}"}), env)).status, 201);
  assert.equal((await worker.fetch(new Request(endpoint, {method:"POST",body:"x".repeat(16385)}), env)).status, 413);
  assert.equal((await worker.fetch(new Request(endpoint), env)).status, 401);
  mock.mock.restore();
  t.mock.method(globalThis, "fetch", async () => Response.json({status:"ok"}));
  for (const agent of ["N8N_RADARES","BACHA","BRIO","NOD"]) {
    const env = { [`${agent}_KANBAN_TOKEN`]: agent, [`${agent}_CF_ACCESS_CLIENT_ID`]: "id", [`${agent}_CF_ACCESS_CLIENT_SECRET`]: "secret" };
    for (const path of ["/api/factory/reconcile", "/api/factory/admit", "/api/factory/reports/daily", "/api/factory/error", "/api/factory/reports/2026-11-18/sent"]) {
      const r=new Request("https://kanban-api.okehc.com"+path,{method:"POST",headers:{Authorization:`Bearer ${agent}`},body:"{}"});
      assert.equal((await worker.fetch(r,env)).status, agent === "N8N_RADARES" ? 200 : 404);
    }
  }
});
