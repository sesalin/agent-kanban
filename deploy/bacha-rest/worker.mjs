import { createHash, timingSafeEqual } from "node:crypto";

const publicHost = "kanban-api.okehc.com";
const origin = "https://kk.okehc.com";
const agents = ["BACHA", "BRIO", "N8N_RADARES", "CODEX", "INSTINCT", "NOD"];

function digest(value) {
  return createHash("sha256").update(value).digest();
}

function allowed(method, path, agent) {
  if (agent === "N8N_RADARES") {
    if (method === "GET") return /^\/api\/tasks\/[0-9]+$/.test(path);
    return method === "POST" && (path === "/api/tasks/dispatch" || ["/api/factory/reconcile", "/api/factory/error"].includes(path) || /^\/api\/factory\/reports\/\d{4}-\d{2}-\d{2}\/sent$/.test(path) || /^\/api\/factory\/files\/(?:input|specs|verify|wakeup|release)$/.test(path) || /^\/api\/tasks\/[0-9]+\/review$/.test(path));
  }
  if (["BRIO", "CODEX", "INSTINCT"].includes(agent)) {
    if (method === "GET") {
      return path === "/api/tasks/available" ||
        /^\/api\/tasks\/[0-9]+(?:\/(?:comments|progress|package\/input))?$/.test(path);
    }
    if (method === "PUT") return /^\/api\/tasks\/[0-9]+\/package\/result$/.test(path);
    return method === "POST" && /^\/api\/tasks\/[0-9]+\/(?:claim|heartbeat|submit|comments)$/.test(path);
  }
  if (agent === "NOD") {
    if (method === "GET") {
      return path === "/api/tasks/available" ||
        /^\/api\/tasks\/[0-9]+(?:\/(?:progress|comments|package\/(?:input|result)))?$/.test(path);
    }
    if (method === "PUT") return /^\/api\/tasks\/[0-9]+\/package\/result$/.test(path);
    return method === "POST" && /^\/api\/tasks\/[0-9]+\/(?:claim|heartbeat|submit|comments)$/.test(path);
  }
  if (method === "GET") {
    return path === "/api/tasks" || path === "/api/tasks/available" ||
      /^\/api\/tasks\/[0-9]+(?:\/(?:progress|comments|package\/(?:input|result)))?$/.test(path);
  }
  if (method === "PUT") return /^\/api\/tasks\/[0-9]+\/package\/result$/.test(path);
  return method === "POST" && (
    path === "/api/tasks/dispatch" || /^\/api\/tasks\/[0-9]+\/(?:claim|heartbeat|submit|comments|review|reassign)$/.test(path)
  );
}

const mcpRequestHeaders = ["Accept", "MCP-Protocol-Version", "Mcp-Session-Id", "Last-Event-ID", "Origin"];
const mcpResponseHeaders = ["Mcp-Session-Id", "Allow"];

function failure(status, detail) {
  return Response.json({ detail }, { status, headers: { "Cache-Control": "no-store" } });
}

export default {
  async fetch(request, env) {
    const { hostname, pathname, protocol, search } = new URL(request.url);
    const mcp = pathname === "/mcp" || pathname === "/mcp/";
    const allowedRoute = mcp ? ["GET", "POST", "DELETE"].includes(request.method) :
      agents.some((agent) => allowed(request.method, pathname, agent));
    if (protocol !== "https:" || hostname !== publicHost || !allowedRoute) {
      return failure(404, "Route not available");
    }
    const authorization = request.headers.get("Authorization") ?? "";
    const bearer = /^Bearer ([A-Za-z0-9_-]+)$/i.exec(authorization)?.[1];
    const agent = bearer && agents.find((name) =>
      env[`${name}_KANBAN_TOKEN`] && timingSafeEqual(digest(bearer), digest(env[`${name}_KANBAN_TOKEN`])));
    if (!agent) {
      return failure(401, "Invalid Kanban Bearer");
    }
    if (mcp ? agent === "N8N_RADARES" : !allowed(request.method, pathname, agent)) {
      return failure(404, "Route not available");
    }
    const accessId = env[`${agent}_CF_ACCESS_CLIENT_ID`];
    const accessSecret = env[`${agent}_CF_ACCESS_CLIENT_SECRET`];
    if (!accessId || !accessSecret) return failure(503, "Gateway is not configured");

    const packageDownload = request.method === "GET" && /\/package\/(input|result)$/.test(pathname);
    const headers = new Headers({
      Authorization: `Bearer ${bearer}`,
      "CF-Access-Client-Id": accessId,
      "CF-Access-Client-Secret": accessSecret,
      "User-Agent": "Bacha-Kanban-Gateway/1.0",
      Accept: packageDownload ? "application/zip, application/json" : "application/json",
    });
    if (mcp) {
      for (const name of mcpRequestHeaders) {
        const value = request.headers.get(name);
        if (value !== null) headers.set(name, value);
      }
    }
    const contentType = request.headers.get("Content-Type");
    if (contentType) headers.set("Content-Type", contentType);

    // Redirects must never carry the service credentials to another origin.
    let upstream;
    try {
      upstream = await fetch(origin + (mcp ? "/mcp/" : pathname) + search, {
        method: request.method,
        headers,
        body: request.body,
        redirect: "manual",
      });
    } catch {
      return failure(502, "Kanban upstream unavailable");
    }
    const responseType = upstream.headers.get("Content-Type");
    const mediaType = responseType?.split(";")[0].trim().toLowerCase();
    const mcpResponse = mcp && (mediaType === "text/event-stream" ||
      (!mediaType && [202, 204].includes(upstream.status)));
    if ((mediaType !== "application/json" && !mcpResponse &&
        !(packageDownload && mediaType === "application/zip")) ||
        (upstream.status >= 300 && upstream.status < 400)) {
      console.warn("Unexpected Kanban upstream", { agent, status: upstream.status, mediaType });
      return failure(502, "Unexpected response from Kanban upstream");
    }
    const responseHeaders = new Headers({ "Cache-Control": "no-store" });
    if (responseType) responseHeaders.set("Content-Type", responseType);
    if (packageDownload && mediaType === "application/zip") {
      const disposition = upstream.headers.get("Content-Disposition");
      if (disposition) responseHeaders.set("Content-Disposition", disposition);
    }
    if (mcp) {
      for (const name of mcpResponseHeaders) {
        const value = upstream.headers.get(name);
        if (value !== null) responseHeaders.set(name, value);
      }
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  },
};
