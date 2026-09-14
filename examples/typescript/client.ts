import createClient from "openapi-fetch";
import type { paths } from "./schema.d.ts";

type Collection = paths["/v1/projects"];
type Item = paths["/v1/projects/{projectId}"];
export type CreateProject = Collection["post"]["requestBody"]["content"]["application/json"];
export type PatchProject = Item["patch"]["requestBody"]["content"]["application/merge-patch+json"];
export type Project = Item["get"]["responses"][200]["content"]["application/json"];
export type ProjectPage = Collection["get"]["responses"][200]["content"]["application/json"];
export type ListQuery = NonNullable<Collection["get"]["parameters"]["query"]>;

export interface CallOptions {
  signal?: AbortSignal;
}

/** Untrusted RFC 9457 fields. Check field types before displaying/branching. */
export type ProblemDetails = Record<string, unknown>;

export class ApiError extends Error {
  readonly status: number;
  readonly requestId: string | null;
  readonly retryAfter: string | null;
  readonly problem: ProblemDetails | undefined;

  constructor(response: Response, body: unknown) {
    super(`HTTP ${response.status}`);
    this.name = "ApiError";
    this.status = response.status;
    this.requestId = response.headers.get("X-Request-Id");
    this.retryAfter = response.headers.get("Retry-After");
    this.problem = mediaType(response) === "application/problem+json" && isRecord(body) ? body : undefined;
  }
}

export class ProtocolError extends Error {
  readonly status: number;
  readonly requestId: string | null;

  constructor(message: string, response: Response, cause?: unknown) {
    super(message, { cause });
    this.name = "ProtocolError";
    this.status = response.status;
    this.requestId = response.headers.get("X-Request-Id");
  }
}

export class TransportError extends Error {
  readonly kind: "network" | "aborted" | "timeout";

  constructor(cause: unknown, signal: AbortSignal) {
    const reason = signal.aborted ? signal.reason : cause;
    const name = reason instanceof Error ? reason.name : undefined;
    const kind = name === "TimeoutError" ? "timeout" : signal.aborted || name === "AbortError" ? "aborted" : "network";
    super(`Request ${kind}; the server-side outcome may be unknown`, { cause });
    this.name = "TransportError";
    this.kind = kind;
  }
}

export class AuthenticationError extends Error {
  constructor(cause?: unknown) {
    super("An access token could not be obtained", { cause });
    this.name = "AuthenticationError";
  }
}

interface TextResult {
  data?: string | undefined;
  error?: unknown;
  response: Response;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function mediaType(response: Response): string {
  return response.headers.get("Content-Type")?.split(";", 1)[0]?.trim().toLowerCase() ?? "";
}

function requireSuccess(result: TextResult, expectedStatus: number): void {
  // Use the actual HTTP status even when a gateway returns HTML or invalid JSON.
  if (!result.response.ok) throw new ApiError(result.response, result.error);
  if (result.response.status !== expectedStatus) {
    throw new ProtocolError(`Expected HTTP ${expectedStatus}, received ${result.response.status}`, result.response);
  }
}

function readJson<T>(result: TextResult, expectedStatus: number): T {
  requireSuccess(result, expectedStatus);
  if (mediaType(result.response) !== "application/json" || !result.data) {
    throw new ProtocolError("Expected a non-empty application/json success response", result.response);
  }
  try {
    // A deliberate trust boundary: checks JSON syntax only, NOT JSON Schema.
    // Add a compatible runtime validator here when consuming an untrusted service.
    return JSON.parse(result.data) as T;
  } catch (cause) {
    throw new ProtocolError("The success response contains invalid JSON", result.response, cause);
  }
}

function requireEtag(response: Response): string {
  const etag = response.headers.get("ETag");
  // This contract requires one strong entity tag, including its quote marks.
  if (!etag || !/^"[1-9][0-9]*"$/.test(etag)) {
    throw new ProtocolError("Expected a readable strong ETag response header", response);
  }
  return etag;
}

function requireIfMatch(etag: string): void {
  if (!/^"[1-9][0-9]*"$/.test(etag)) {
    throw new TypeError("ifMatch must be the unchanged strong ETag from a prior read");
  }
}

function requireLocation(response: Response): string {
  const location = response.headers.get("Location");
  if (!location || !/^\/v1\/projects\/[0-9a-f-]{36}$/.test(location)) {
    throw new ProtocolError("Expected the new resource's relative Location header", response);
  }
  return location;
}

function obtainToken(getAccessToken: () => string | Promise<string>, signal: AbortSignal): Promise<string> {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const onAbort = () => reject(signal.reason);
    signal.addEventListener("abort", onAbort, { once: true });
    Promise.resolve().then(getAccessToken).then(
      (token) => { signal.removeEventListener("abort", onAbort); resolve(token); },
      (cause: unknown) => { signal.removeEventListener("abort", onAbort); reject(cause); },
    );
  });
}

/**
 * One request per call; no automatic retries or token refresh.
 * Modern Fetch, AbortController, AbortSignal.any and AbortSignal.timeout are required.
 * baseUrl is the API origin/optional gateway prefix; the paths already include /v1.
 */
export function createProjectClient(
  baseUrl: string,
  getAccessToken: () => string | Promise<string>,
  dependencies: { fetch?: (request: Request) => Promise<Response> } = {},
) {
  const parsedBase = new URL(baseUrl);
  if (!["https:", "http:"].includes(parsedBase.protocol) || parsedBase.search || parsedBase.hash || parsedBase.username || parsedBase.password) {
    throw new TypeError("baseUrl must be an absolute HTTP(S) URL without credentials, query or fragment");
  }
  if (parsedBase.protocol === "http:" && !["localhost", "127.0.0.1", "[::1]"].includes(parsedBase.hostname)) {
    throw new TypeError("HTTPS is required outside loopback development environments");
  }
  const api = createClient<paths>({
    baseUrl: baseUrl.replace(/\/$/, ""),
    headers: { Accept: "application/json, application/problem+json" },
    credentials: "omit",
    redirect: "error",
    ...(dependencies.fetch ? { fetch: dependencies.fetch } : {}),
  });
  api.use({
    async onRequest({ request }) {
      try {
        const token = await obtainToken(getAccessToken, request.signal);
        if (!token) throw new Error("Token is empty");
        request.headers.set("Authorization", `Bearer ${token}`);
      } catch (cause) {
        if (request.signal.aborted) throw cause;
        throw new AuthenticationError(cause);
      }
      return request;
    },
  });

  async function execute(run: (signal: AbortSignal) => Promise<TextResult>, options: CallOptions): Promise<TextResult> {
    const deadline = AbortSignal.timeout(10_000);
    const signal = options.signal ? AbortSignal.any([options.signal, deadline]) : deadline;
    try {
      // Includes failures while reading the response body, not only fetch().
      return await run(signal);
    } catch (cause) {
      if (cause instanceof AuthenticationError) throw cause;
      throw new TransportError(cause, signal);
    }
  }

  return {
    async list(query: ListQuery = {}, options: CallOptions = {}) {
      const result = await execute((signal) => api.GET("/v1/projects", {
        params: { query }, parseAs: "text", signal,
      }), options);
      return { data: readJson<ProjectPage>(result, 200), requestId: result.response.headers.get("X-Request-Id") };
    },

    async get(projectId: string, options: CallOptions = {}) {
      const result = await execute((signal) => api.GET("/v1/projects/{projectId}", {
        params: { path: { projectId } }, parseAs: "text", signal,
      }), options);
      return { data: readJson<Project>(result, 200), etag: requireEtag(result.response) };
    },

    async create(body: CreateProject, idempotencyKey: string, options: CallOptions = {}) {
      if (!/^[A-Za-z0-9_-]{16,128}$/.test(idempotencyKey)) {
        throw new TypeError("Use the persisted 16–128 character Idempotency-Key for this logical submission");
      }
      const result = await execute((signal) => api.POST("/v1/projects", {
        params: { header: { "Idempotency-Key": idempotencyKey } },
        body, parseAs: "text", signal,
      }), options);
      return {
        data: readJson<Project>(result, 201),
        etag: requireEtag(result.response),
        location: requireLocation(result.response),
      };
    },

    async update(projectId: string, body: PatchProject, ifMatch: string, options: CallOptions = {}) {
      requireIfMatch(ifMatch);
      const result = await execute((signal) => api.PATCH("/v1/projects/{projectId}", {
        params: { path: { projectId }, header: { "If-Match": ifMatch } },
        headers: { "Content-Type": "application/merge-patch+json" },
        body, parseAs: "text", signal,
      }), options);
      return { data: readJson<Project>(result, 200), etag: requireEtag(result.response) };
    },

    async remove(projectId: string, ifMatch: string, options: CallOptions = {}): Promise<void> {
      requireIfMatch(ifMatch);
      const result = await execute((signal) => api.DELETE("/v1/projects/{projectId}", {
        params: { path: { projectId }, header: { "If-Match": ifMatch } },
        parseAs: "text", signal,
      }), options);
      requireSuccess(result, 204);
    },
  };
}
