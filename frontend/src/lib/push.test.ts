import { describe, expect, it } from "vitest";

import { keyToBytes, pushSupport } from "./push";

const chrome = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/141.0 Mobile Safari/537.36";
const iphone = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1";
const env = { standalone: false, hasServiceWorker: true, hasPushManager: true };

describe("알림을 켤 수 있는지", () => {
  it("안드로이드·PC 브라우저는 바로 된다", () => {
    expect(pushSupport({ ...env, userAgent: chrome })).toBe("ready");
  });

  it("아이폰은 홈 화면에 추가한 앱에서만 된다", () => {
    expect(pushSupport({ ...env, userAgent: iphone })).toBe("ios-install");
    expect(pushSupport({ ...env, userAgent: iphone, standalone: true })).toBe("ready");
  });

  it("푸시를 모르는 브라우저", () => {
    expect(pushSupport({ ...env, userAgent: chrome, hasPushManager: false })).toBe("unsupported");
  });
});

describe("서버 공개키", () => {
  it("base64url을 바이트로 바꾼다", () => {
    // "BAEC" = 0x04 0x01 0x02 (비압축 공개키는 0x04로 시작)
    expect([...keyToBytes("BAEC")]).toEqual([4, 1, 2]);
    expect([...keyToBytes("-_8")]).toEqual([251, 255]);
  });
});
