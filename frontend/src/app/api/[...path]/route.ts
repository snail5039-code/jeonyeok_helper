// 브라우저 → Next.js /api/* → FastAPI 프록시.
// 실행할 때 API_URL을 읽으므로 이미지 하나로 어느 환경에든 배포할 수 있고,
// /chat 의 SSE 스트림도 버퍼링 없이 그대로 넘긴다.
import type { NextRequest } from "next/server";

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

// 열어 둘 FastAPI 경로만 허용한다 (임의 주소로 넘기는 열린 프록시가 되지 않게).
const ALLOWED = [
  /^health$/,
  /^chat$/,
  /^feedback$/,
  /^profile\/[\w-]{1,64}$/,
  /^journey\/[\w-]{1,64}$/,
  /^journey\/[\w-]{1,64}\/generate$/,
  /^journey\/[\w-]{1,64}\/items$/,
  /^journey\/[\w-]{1,64}\/items\/[\w-]{1,64}$/,
  /^backup\/[\w-]{1,64}$/,
  /^resume-code\/[\w-]{1,64}$/,
  /^resume$/,
  /^push\/key$/,
  /^push\/[\w-]{1,64}$/,
  /^push\/[\w-]{1,64}\/(unsubscribe|test)$/,
  /^applications$/,
  /^applications\/[a-z_]{1,40}$/,
  /^admin\/summary$/,
];
const NO_BODY = new Set(["GET", "DELETE"]);

async function proxy(req: NextRequest, ctx: RouteContext<"/api/[...path]">) {
  const path = (await ctx.params).path.join("/");
  if (!ALLOWED.some((re) => re.test(path))) {
    return Response.json({ detail: "없는 주소예요." }, { status: 404 });
  }

  let upstream: Response;
  try {
    // 물음표 뒤(예: ?user_id=)도 그대로 넘긴다
    upstream = await fetch(`${API_URL}/${path}${req.nextUrl.search}`, {
      method: req.method,
      headers: {
        "Content-Type": req.headers.get("content-type") ?? "application/json",
        // 운영 대시보드의 관리자 열쇠만 넘긴다 (다른 머리글은 넘기지 않음)
        ...(req.headers.get("x-admin-token") ? { "X-Admin-Token": req.headers.get("x-admin-token")! } : {}),
      },
      body: NO_BODY.has(req.method) ? undefined : await req.text(),
      cache: "no-store",
    });
  } catch {
    return Response.json(
      { detail: "상담 서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요." },
      { status: 502 },
    );
  }

  // 204는 본문을 가질 수 없다
  return new Response(upstream.status === 204 ? null : upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
    },
  });
}

export { proxy as DELETE, proxy as GET, proxy as PATCH, proxy as POST, proxy as PUT };
