import { GoogleAuth } from "google-auth-library";
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

const localController = "http://127.0.0.1:8095";

function controllerUrl(): URL {
  const configured = process.env.CARGO_RELEASE_CONTROLLER_URL ?? localController;
  const url = new URL(configured);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("CARGO_RELEASE_CONTROLLER_URL must use HTTP or HTTPS");
  }
  return url;
}

function isLocal(url: URL): boolean {
  return url.hostname === "127.0.0.1" || url.hostname === "localhost";
}

function controllerAudience(controller: URL): string {
  const configured = process.env.CARGO_RELEASE_CONTROLLER_AUDIENCE;
  if (!configured) return controller.origin;

  const audience = new URL(configured);
  if (audience.protocol !== "https:") {
    throw new Error("CARGO_RELEASE_CONTROLLER_AUDIENCE must use HTTPS");
  }
  return audience.href;
}

function safeIdentityClaims(authorization: string): { aud?: unknown; email?: unknown } {
  try {
    const token = authorization.replace(/^Bearer\s+/i, "");
    const payload = token.split(".")[1];
    if (!payload) return {};
    const claims = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as {
      aud?: unknown;
      email?: unknown;
    };
    return { aud: claims.aud, email: claims.email };
  } catch {
    return {};
  }
}

async function relay(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  if (!path.length || path.some((segment) => segment === "." || segment === "..")) {
    return Response.json({ detail: "Invalid controller path" }, { status: 400 });
  }

  const controller = controllerUrl();
  const target = new URL(path.map(encodeURIComponent).join("/"), `${controller.href.replace(/\/$/, "")}/`);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  if (!isLocal(controller)) {
    const auth = new GoogleAuth();
    const audience = controllerAudience(controller);
    const client = await auth.getIdTokenClient(audience);
    const identityHeaders = await client.getRequestHeaders(audience);
    const authorization = identityHeaders.get("authorization");
    if (!authorization) {
      throw new Error("Google identity client returned no authorization header");
    }
    headers.set("x-serverless-authorization", authorization);
    console.info(
      JSON.stringify({
        event: "cargo_release_relay_attempt",
        target: target.toString(),
        requested_audience: audience,
        token: safeIdentityClaims(authorization),
      }),
    );
  }

  const method = request.method.toUpperCase();
  const upstream = await fetch(target, {
    method,
    headers,
    body: method === "GET" || method === "HEAD" ? undefined : await request.text(),
    cache: "no-store",
    redirect: "manual",
  });

  console.info(
    JSON.stringify({
      event: "cargo_release_relay_response",
      target: target.toString(),
      status: upstream.status,
      trace: upstream.headers.get("x-cloud-trace-context"),
    }),
  );

  const responseHeaders = new Headers();
  const upstreamContentType = upstream.headers.get("content-type");
  if (upstreamContentType) responseHeaders.set("content-type", upstreamContentType);
  responseHeaders.set("cache-control", "no-store");
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = relay;
export const POST = relay;
