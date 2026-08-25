import { GoogleAuth } from "google-auth-library";
import type { NextRequest } from "next/server";

import {
  authorizeRelayRequest,
  RelayPolicyError,
} from "@/lib/relay-policy";

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
  const controller = controllerUrl();
  const method = request.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? "" : await request.text();
  const operatorActor =
    process.env.CARGO_RELEASE_WEB_OPERATOR_ACTOR ??
    (isLocal(controller) ? "demo-operator-via:cargo-web.local" : undefined);
  let decision;
  try {
    decision = authorizeRelayRequest({
      method,
      path,
      search: request.nextUrl.search,
      body,
      operatorActor,
    });
  } catch (error) {
    if (error instanceof RelayPolicyError) {
      return Response.json(
        { detail: error.message, code: error.code },
        {
          status: error.status,
          headers: {
            "cache-control": "no-store",
            "x-content-type-options": "nosniff",
          },
        },
      );
    }
    throw error;
  }

  const target = new URL(
    decision.upstreamPath.split("/").map(encodeURIComponent).join("/"),
    `${controller.href.replace(/\/$/, "")}/`,
  );

  const headers = new Headers();
  if (decision.upstreamBody !== undefined) {
    headers.set("content-type", "application/json");
  }

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
        action: decision.action,
        target: target.toString(),
        requested_audience: audience,
        token: safeIdentityClaims(authorization),
      }),
    );
  }

  const upstream = await fetch(target, {
    method,
    headers,
    body: decision.upstreamBody,
    cache: "no-store",
    redirect: "manual",
  });

  console.info(
    JSON.stringify({
      event: "cargo_release_relay_response",
      action: decision.action,
      target: target.toString(),
      status: upstream.status,
      trace: upstream.headers.get("x-cloud-trace-context"),
    }),
  );

  const responseHeaders = new Headers();
  const upstreamContentType = upstream.headers.get("content-type");
  if (upstreamContentType) responseHeaders.set("content-type", upstreamContentType);
  responseHeaders.set("cache-control", "no-store");
  responseHeaders.set("x-content-type-options", "nosniff");
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = relay;
export const POST = relay;
