# AWS에 올리기 (초보자용)

> 2026-10-24 정리. **실제로 서버를 만들지는 않았고**, 처음 해 보는 사람이 그대로 따라 할 수 있게 순서를 적어 둔 문서입니다.
> 요금은 이날 기준 대략값입니다. 결제 전에 [Lightsail 요금](https://aws.amazon.com/ko/lightsail/pricing/)에서 다시 확인하세요.

## 0. 먼저 알아 둘 것

**무엇을 쓰나**: AWS **Lightsail**입니다. 서버 한 대를 월 고정 요금으로 빌리는 서비스라, EC2보다 설정할 것이 훨씬 적고 요금이 예상한 대로 나옵니다.
그 서버 안에서 지금 로컬과 **똑같이 `docker compose up`** 을 합니다. 코드는 하나도 바꾸지 않습니다.

```
내 PC (지금)                         AWS Lightsail 서버 한 대
docker compose up   ──똑같이──▶     docker compose up
localhost:3000                      http://서버IP  →  (도메인을 붙이면) https://내도메인
```

**돈은 얼마나**

| 항목 | 비용 |
|---|---|
| Lightsail 4GB 서버 | 월 약 **$24** (약 3만 4천 원). 시간 단위로 계산 → 하루 켜 두면 약 $0.8 |
| 고정 IP | 서버에 붙어 있으면 무료 |
| 도메인 (선택) | 연 1~2만 원. 없어도 IP 주소로 열림 |
| Gemini API | 질문 수만큼. 지금 쓰는 키 그대로 |

- **왜 4GB인가**: 백엔드가 혼자 약 855MB를 씁니다(한국어 형태소 분석기 Kiwi만 약 500MB). DB와 화면까지 합치면 1.2GB쯤이고, 서버에서 이미지를 빌드할 때 더 씁니다. 2GB($12)도 되지만 멈출 수 있어 초보자에게는 4GB를 권합니다.
- **포트폴리오용으로 아끼는 법**: 면접·시연 때만 켜 두고, 끝나면 **스냅샷을 찍고 서버를 삭제**합니다. 다시 필요할 때 스냅샷으로 5분 만에 살립니다(9장). 일주일만 켜면 $6 안팎입니다.
- **주의**: Lightsail은 서버를 **"중지"해도 요금이 나갑니다.** 요금을 멈추려면 **삭제**해야 합니다.
- 새 계정에는 무료 크레딧이나 몇 달 무료 플랜이 붙는 경우가 있습니다. 가입할 때 안내를 확인하세요(조건이 자주 바뀜).

**전체 순서** (처음이면 1~2시간)

1. AWS 가입 → 2. 서버 만들기 → 3. 고정 IP·방화벽 → 4. 서버 접속 → 5. Docker 설치 → 6. 코드·키 넣기 → 7. 검색 자료 옮기기 → 8. 켜기 → (선택) 도메인·HTTPS

## 1. AWS 가입

1. [aws.amazon.com](https://aws.amazon.com/ko/)에서 계정 만들기. 카드 등록이 필요합니다(확인용 소액 결제 후 취소됨).
2. **꼭 해 둘 것: 요금 알림.** 콘솔 위 검색창에 `Budgets` → 예산 만들기 → 월 $30 → 80% 넘으면 메일. 실수로 비싼 걸 켜도 바로 알 수 있습니다.
3. 루트 계정에 **MFA(2단계 인증)** 를 켭니다(계정 이름 클릭 → 보안 자격 증명).

## 2. 서버 만들기

1. 콘솔 검색창에 `Lightsail` → **Create instance**.
2. 고를 것:
   - 위치: **Seoul (ap-northeast-2)**
   - 플랫폼: **Linux/Unix**
   - 블루프린트: **OS Only → Ubuntu 24.04 LTS**
   - 플랜: **$24 (4GB 메모리, 2 vCPU, 80GB SSD)**
   - 이름: `jeonyeok`
3. **Create instance**. 1~2분 뒤 상태가 Running이 됩니다.

## 3. 고정 IP와 방화벽

서버를 다시 켜면 IP가 바뀌므로 고정 IP를 붙입니다.

1. 인스턴스 클릭 → **Networking** 탭 → **Attach static IP** → 이름 아무거나 → 만들기. 이 IP를 적어 두세요(아래에서 `서버IP`).
2. 같은 탭의 **IPv4 Firewall**:
   - 이미 있는 것: SSH(22), HTTP(80)
   - **HTTPS(443) 추가** (도메인을 붙일 때 필요)
   - SSH(22)는 가능하면 "Restrict to IP address"로 내 IP만 허용
   - **5432(DB)·8000(api)·3000은 열지 않습니다.** 밖에서 DB에 바로 들어올 수 있게 되기 때문입니다.

## 4. 서버 접속

가장 쉬운 방법: 인스턴스 화면의 **Connect using SSH** 버튼. 브라우저에 검은 터미널 창이 열립니다. 아래 명령은 전부 여기에 붙여 넣습니다.

> 내 PC의 파일을 서버로 보낼 때(7장)는 PC의 터미널에서 접속해야 합니다.
> Lightsail 첫 화면 → 계정 → **SSH keys** → 서울 리전 기본 키 다운로드(`LightsailDefaultKey-ap-northeast-2.pem`).
> ```bash
> ssh -i LightsailDefaultKey-ap-northeast-2.pem ubuntu@서버IP
> ```

## 5. Docker 설치 (서버에서, 한 번만)

```bash
sudo apt update && sudo apt -y upgrade
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

창을 닫고 다시 접속한 뒤 확인합니다.

```bash
docker compose version     # 버전이 나오면 성공
```

혹시 메모리가 모자랄 때를 대비해 스왑(디스크를 메모리처럼 쓰기) 4GB를 켜 둡니다.

```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 6. 코드와 키 넣기

```bash
git clone https://github.com/snail5039-code/jeonyeok_helper.git
cd jeonyeok_helper
cp backend/.env.example backend/.env
nano backend/.env
```

`nano` 편집기가 열리면 로컬 `backend/.env`와 같은 값을 넣습니다.

| 키 | 값 |
|---|---|
| `GOOGLE_API_KEY`, `LAW_API_OC`, `DATA_GO_KR_SERVICE_KEY`, `YOUTHCENTER_API_KEY` | 로컬과 같은 값 |
| `ADMIN_TOKEN` | 새로 만든 긴 값 (`openssl rand -base64 24` 결과를 붙여 넣기) |
| `VAPID_*` | 로컬 값. `VAPID_SUBJECT`는 도메인이 생기면 `https://내도메인`으로 |

저장은 `Ctrl+O` → `Enter`, 나가기는 `Ctrl+X`. **이 파일은 Git에 올리지 않습니다.**

## 7. 검색 자료 옮기기

서버에서 법령·자료를 처음부터 다시 모으면 몇 시간과 임베딩 비용이 듭니다. **로컬 DB를 파일로 떠서 그대로 옮기는 것**이 빠릅니다(약 200MB).

**내 PC에서** (로컬 Docker가 켜진 상태, 레포 폴더에서)

```bash
docker exec jeonyeok_helper-db-1 pg_dump -U jeonyeok -Fc jeonyeok > jeonyeok.dump
scp -i LightsailDefaultKey-ap-northeast-2.pem jeonyeok.dump ubuntu@서버IP:~/
```

> PowerShell에서는 `>`가 파일을 망가뜨릴 수 있어서, 첫 줄은 **Git Bash**에서 실행하세요.

**서버에서**

```bash
cd ~/jeonyeok_helper
docker compose up -d db
docker compose exec -T db pg_restore -U jeonyeok -d jeonyeok --clean --if-exists < ~/jeonyeok.dump
```

경고가 몇 줄 나와도 마지막에 멈추지 않았다면 괜찮습니다.

## 8. 켜기

```bash
docker compose up -d --build      # 처음엔 이미지 빌드로 5~10분
docker compose ps                 # db, api, web이 healthy인지
curl -s localhost:8000/health     # {"status":"ok", ...}
```

지금 compose는 화면을 3000번 포트로 띄우므로, 서버 안에서 80번으로 넘겨 주는 설정을 하나 추가합니다(아래 "도메인·HTTPS"를 할 거면 건너뛰고 그쪽으로).

```bash
cat > docker-compose.override.yml <<'EOF'
services:
  web:
    ports: !override
      - "80:3000"
  db:
    ports: !reset []
EOF
docker compose up -d
```

브라우저에서 **`http://서버IP`** 가 열리면 끝입니다. 질문을 하나 해 보세요.

- `db`의 `ports`를 비운 이유: 서버 밖으로 DB 포트를 내보내지 않기 위해서입니다(방화벽으로도 막았지만 한 번 더).
- 휴대폰 알림·홈 화면 설치는 **HTTPS에서만** 됩니다. 이것까지 보여 주려면 아래 도메인을 붙이세요.

## (선택) 도메인·HTTPS

1. 도메인을 삽니다(가비아·Cloudflare·Route 53 등, 연 1~2만 원).
2. 도메인 관리 화면에서 **A 레코드: `내도메인` → `서버IP`** 를 추가합니다. 반영까지 몇 분~몇 시간.
3. 서버에서 Caddy(인증서를 자동으로 받아 주는 웹 서버)를 앞에 붙입니다.

```bash
cd ~/jeonyeok_helper
cat > Caddyfile <<'EOF'
내도메인.com {
    reverse_proxy web:3000
}
EOF
cat > docker-compose.override.yml <<'EOF'
services:
  caddy:
    image: caddy:2.8
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
    depends_on:
      - web
    restart: unless-stopped
  web:
    ports: !reset []
  db:
    ports: !reset []
volumes:
  caddy_data:
EOF
docker compose up -d
```

4. `https://내도메인`에 자물쇠가 보이면 성공입니다. `backend/.env`의 `VAPID_SUBJECT`를 `https://내도메인`으로 바꾸고 `docker compose up -d api`.

## 9. 끄기·다시 켜기 (돈 아끼기)

| 하고 싶은 것 | 방법 |
|---|---|
| 코드 바꾼 걸 반영 | `cd ~/jeonyeok_helper && git pull && docker compose up -d --build` |
| 로그 보기 | `docker compose logs -f --tail=100 api` |
| **요금 멈추기** | 인스턴스 → **Snapshots** 탭 → 스냅샷 만들기 → 끝나면 인스턴스 **Delete**. 고정 IP도 **Networking → 삭제**(붙어 있지 않은 고정 IP는 요금이 붙음) |
| 다시 살리기 | Snapshots → 스냅샷의 메뉴 → **Create new instance** → 고정 IP 다시 붙이기. 도메인을 쓰면 A 레코드도 새 IP로 |

- 스냅샷 보관료는 GB당 월 $0.05 정도라, 80GB 디스크라도 실제 쓴 만큼만 계산돼 월 $1 안팎입니다.
- 서버를 재부팅해도 `restart: unless-stopped` 덕분에 서비스가 자동으로 다시 뜹니다.

## 10. 막힐 때

| 증상 | 확인 |
|---|---|
| `http://서버IP`가 안 열림 | Lightsail 방화벽에 HTTP(80)가 있는지, `docker compose ps`에서 web이 Up인지 |
| 빌드 중 멈추거나 `Killed` | 메모리 부족. 5장의 스왑을 켰는지 `free -h`로 확인 |
| 답변이 "데모 모드" | `backend/.env`의 `GOOGLE_API_KEY`를 확인하고 `docker compose up -d api` |
| 질문하면 근거를 못 찾음 | 7장 복원이 됐는지: `docker compose exec db psql -U jeonyeok -c "select count(*) from langchain_pg_embedding;"` (1만 개 안팎이면 정상) |
| HTTPS 인증서가 안 붙음 | 도메인 A 레코드가 서버IP인지(`nslookup 내도메인`), 방화벽에 443이 있는지, `docker compose logs caddy` |

---

## 참고: 크게 키운다면 (지금은 필요 없음)

사용자가 많아지고 서버가 멈추면 안 되는 단계가 되면, 서버 한 대 대신 AWS 관리형 서비스로 나눕니다. **월 약 $90~120**으로 Lightsail의 4~5배라 지금은 하지 않습니다.

| 지금 compose | 키울 때 AWS | 이유 |
|---|---|---|
| `db` | RDS PostgreSQL 17 (pgvector) | 백업·장애 조치를 AWS가 함 |
| `api`, `web` | ECS Fargate (+ ECR 이미지 저장소) | 서버 관리(OS 패치·재시작)가 없음 |
| `refresh` (7일마다) | EventBridge Scheduler가 주 1회 실행 | 계속 켜 둘 필요가 없음 |
| 3000번 포트 | ALB + ACM 인증서 + Route 53 | HTTPS, 여러 대로 나눠 받기 |
| `backend/.env` | Secrets Manager | 키를 서버 파일에 두지 않음 |

이때 주의할 점: api는 **1대로 고정**해야 합니다. 기한 알림 루프와 같은 질문 답 저장이 서버 안에 있어서, 2대로 늘리면 알림이 두 번 가고 저장된 답이 서버마다 달라집니다. 늘리려면 이 둘을 먼저 밖으로 빼야 합니다.
