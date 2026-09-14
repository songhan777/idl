import assert from "node:assert/strict";
import test from "node:test";
import { ApiError, AuthenticationError, ProtocolError, TransportError, createProjectClient } from "./client.ts";

const id = "6c1d9950-8fa5-4c0e-bb8f-d875fe4c4e7c";
const project = {
  id,
  displayName: "Example",
  description: null,
  createdAt: "2026-09-14T08:00:00Z",
  updatedAt: "2026-09-14T08:00:00Z",
  version: 1,
};
const json = (body: unknown, status = 200, headers: Record<string, string> = {}) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json", ETag: '"1"', ...headers },
});

test("GET obtains the current token and preserves quoted ETag", async () => {
  let tokenCalls = 0;
  const api = createProjectClient("https://api.example.com", () => `test-token-${++tokenCalls}`, {
    fetch: async (request) => {
      assert.equal(request.url, `https://api.example.com/v1/projects/${id}`);
      assert.equal(request.headers.get("Authorization"), `Bearer test-token-${tokenCalls}`);
      assert.equal(request.credentials, "omit");
      assert.equal(request.redirect, "error");
      return json(project);
    },
  });
  assert.deepEqual(await api.get(id), { data: project, etag: '"1"' });
  await api.get(id);
  assert.equal(tokenCalls, 2);
});

test("list serializes its cursor without interpreting it", async () => {
  const api = createProjectClient("https://api.example.com", () => "test-token", {
    fetch: async (request) => {
      const url = new URL(request.url);
      assert.equal(url.searchParams.get("cursor"), "opaque+/=cursor");
      assert.equal(url.searchParams.get("limit"), "20");
      return json({ items: [project], nextCursor: null });
    },
  });
  assert.equal((await api.list({ limit: 20, cursor: "opaque+/=cursor" })).data.items.length, 1);
});

test("POST reuses the caller-owned key across an explicit retry and never retries itself", async () => {
  const key = "7ce2f671-36d4-4756-863b-4e7c225d4a31";
  let attempts = 0;
  const api = createProjectClient("https://api.example.com", () => "test-token", {
    fetch: async (request) => {
      attempts++;
      assert.equal(request.headers.get("Idempotency-Key"), key);
      assert.equal(request.headers.get("Content-Type"), "application/json");
      assert.deepEqual(await request.json(), { displayName: "Example" });
      if (attempts === 1) throw new TypeError("Connection dropped after request transmission");
      return json(project, 201, { Location: `/v1/projects/${id}` });
    },
  });
  await assert.rejects(api.create({ displayName: "Example" }, key), (error: unknown) => error instanceof TransportError && error.kind === "network");
  assert.equal(attempts, 1);
  const created = await api.create({ displayName: "Example" }, key);
  assert.equal(created.location, `/v1/projects/${id}`);
  assert.equal(attempts, 2);
});

test("PATCH sends merge-patch media type, null, and unchanged If-Match", async () => {
  const api = createProjectClient("https://api.example.com", () => "test-token", {
    fetch: async (request) => {
      assert.equal(request.method, "PATCH");
      assert.equal(request.headers.get("Content-Type"), "application/merge-patch+json");
      assert.equal(request.headers.get("If-Match"), '"1"');
      assert.deepEqual(await request.json(), { description: null });
      return json({ ...project, version: 2 }, 200, { ETag: '"2"' });
    },
  });
  assert.equal((await api.update(id, { description: null }, '"1"')).etag, '"2"');
});

test("DELETE handles a bodyless 204 and retains precondition", async () => {
  const api = createProjectClient("https://api.example.com", () => "test-token", {
    fetch: async (request) => {
      assert.equal(request.method, "DELETE");
      assert.equal(request.headers.get("If-Match"), '"1"');
      return new Response(null, { status: 204 });
    },
  });
  assert.equal(await api.remove(id, '"1"'), undefined);
});

test("problem+json retains real HTTP status and Retry-After", async () => {
  const api = createProjectClient("https://api.example.com", () => "test-token", {
    fetch: async () => json({ type: "about:blank", title: "Too many requests", status: 500, code: "RATE_LIMITED" }, 429, {
      "Content-Type": "application/problem+json; charset=utf-8", "Retry-After": "3", "X-Request-Id": "4bf92f3577b34da6a3ce929d0e0e4736",
    }),
  });
  await assert.rejects(api.get(id), (error: unknown) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 429); // Never trust a contradictory body.status.
    assert.equal(error.problem?.["code"], "RATE_LIMITED");
    assert.equal(error.requestId, "4bf92f3577b34da6a3ce929d0e0e4736");
    assert.equal(error.retryAfter, "3");
    return true;
  });
});

test("HTML and invalid JSON error bodies still become ApiError", async () => {
  for (const [body, type] of [["<html>gateway error</html>", "text/html"], ["{broken", "application/problem+json"]]) {
    const api = createProjectClient("https://api.example.com", () => "test-token", {
      fetch: async () => new Response(body, { status: 502, headers: { "Content-Type": type ?? "text/plain" } }),
    });
    await assert.rejects(api.get(id), (error: unknown) => error instanceof ApiError && error.status === 502 && error.problem === undefined);
  }
});

test("empty, malformed and wrong-media successful responses become ProtocolError", async () => {
  for (const [body, type] of [["", "application/json"], ["{broken", "application/json"], ["<html>login</html>", "text/html"]]) {
    const api = createProjectClient("https://api.example.com", () => "test-token", {
      fetch: async () => new Response(body, { status: 200, headers: { "Content-Type": type ?? "text/plain", ETag: '"1"' } }),
    });
    await assert.rejects(api.get(id), ProtocolError);
  }
});

test("missing or weak ETag and missing Location do not look like a valid write result", async () => {
  for (const etag of ["", 'W/"1"']) {
    const api = createProjectClient("https://api.example.com", () => "test-token", { fetch: async () => json(project, 200, { ETag: etag }) });
    await assert.rejects(api.get(id), ProtocolError);
  }
  const api = createProjectClient("https://api.example.com", () => "test-token", { fetch: async () => json(project, 201) });
  await assert.rejects(api.create({ displayName: "Example" }, "7ce2f671-36d4-4756-863b-4e7c225d4a31"), ProtocolError);
});

test("412 is returned once without silently refreshing If-Match", async () => {
  let attempts = 0;
  const api = createProjectClient("https://api.example.com", () => "test-token", {
    fetch: async () => { attempts++; return json({ code: "PRECONDITION_FAILED" }, 412, { "Content-Type": "application/problem+json" }); },
  });
  await assert.rejects(api.update(id, { displayName: "Changed" }, '"1"'), (error: unknown) => error instanceof ApiError && error.status === 412);
  assert.equal(attempts, 1);
});

test("abort and timeout remain distinguishable, including during token acquisition", async () => {
  const api = createProjectClient("https://api.example.com", () => "test-token", {
    fetch: async (request) => { request.signal.throwIfAborted(); return json(project); },
  });
  await assert.rejects(api.get(id, { signal: AbortSignal.abort() }), (error: unknown) => error instanceof TransportError && error.kind === "aborted");
  await assert.rejects(api.get(id, { signal: AbortSignal.abort(new DOMException("Deadline exceeded", "TimeoutError")) }),
    (error: unknown) => error instanceof TransportError && error.kind === "timeout");
  const controller = new AbortController();
  const waiting = createProjectClient("https://api.example.com", () => new Promise<string>(() => {}));
  const pending = waiting.get(id, { signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, (error: unknown) => error instanceof TransportError && error.kind === "aborted");
});

test("token failure is distinguishable from a network failure", async () => {
  const api = createProjectClient("https://api.example.com", () => { throw new Error("Login required"); });
  await assert.rejects(api.get(id), AuthenticationError);
});

test("body stream failures are reported as transport failures", async () => {
  const api = createProjectClient("https://api.example.com", () => "test-token", {
    fetch: async () => new Response(new ReadableStream({ start(controller) { controller.error(new Error("Stream interrupted")); } }), {
      headers: { "Content-Type": "application/json" },
    }),
  });
  await assert.rejects(api.get(id), (error: unknown) => error instanceof TransportError && error.kind === "network");
});
