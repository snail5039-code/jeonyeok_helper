// localStorage는 사생활 보호 모드 등에서 막힐 수 있어 실패해도 조용히 넘어간다.

export function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* 저장할 수 없는 환경 */
  }
}

/** 브라우저마다 한 번 만든 익명 ID. 서버가 프로필을 기억하는 데 쓴다. */
export function getUserId(): string {
  const saved = readStorage("jeonyeok.userId");
  if (saved) return saved;
  const id = crypto.randomUUID();
  writeStorage("jeonyeok.userId", id);
  return id;
}
