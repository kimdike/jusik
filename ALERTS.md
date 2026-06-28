# 🔔 알림 설정 가이드

신호 변화 / 목표가 / 손절가를 **텔레그램으로** 받는 기능입니다.

## 무엇을 알려주나
- **신호 변화**: 종목의 종합 신호 밴드가 바뀔 때 (예: 중립 → 상승 우세, 상승 우세 → 강한 상승 우세)
- **목표가 도달** 🎯: 현재가가 내가 정한 목표가 이상으로 올라올 때
- **손절가 이탈** 🛑: 현재가가 내가 정한 손절가 이하로 내려갈 때

> 직전 점검 대비 "바뀐 순간"에만 1회 보냅니다(도배 방지). 처음 보는 종목은 조용히 기준만 기록.

## 1) 알림 대상/가격 설정
대시보드 → **알림 설정** 메뉴에서 종목별 목표가·손절가·신호알림을 켜고 저장.
(워치리스트/보유종목이 자동으로 목록에 뜸)

## 2) 텔레그램 연결
별도 설정 없이, 이미 쓰는 텔레그램 봇으로 전송됩니다
(`~/.claude/channels/telegram/.env` 의 토큰을 자동으로 읽음).
직접 지정하려면 `config/notify.json` 생성:
```json
{ "telegram_token": "본인_봇토큰", "chat_id": "본인_chat_id(텔레그램)" }
```
대시보드 "알림 설정 → 테스트 메시지 보내기"로 연결 확인.

## 3) 자동 실행 (둘 중 택1)

### 방법 A — 켜둔 동안 반복 (간단)
PowerShell에서 프로젝트 폴더에서:
```powershell
.venv\Scripts\python alerts_run.py --loop 15
```
15분마다 점검. 창 닫으면 멈춤.

### 방법 B — 작업 스케줄러 (완전 자동, 창 없이)
PowerShell에서 (한 줄):
```powershell
schtasks /Create /SC MINUTE /MO 15 /TN "주식알림" /TR "'C:\Users\KDH\Desktop\jusik\.venv\Scripts\pythonw.exe' 'C:\Users\KDH\Desktop\jusik\alerts_run.py'" /ST 09:00
```
- 15분마다 자동 실행 (장중에만 받고 싶으면 시간 조건은 스케줄러 GUI에서 조정)
- 삭제: `schtasks /Delete /TN "주식알림" /F`
- `pythonw.exe`라 검은 창이 안 뜸

> PC를 자주 끈다면 **클라우드 배포**가 낫습니다. 클라우드에선 별도 스케줄 작업으로 `alerts_run.py`를 돌리면 됩니다 (배포 시 같이 안내).

## 수동 점검
대시보드 "알림 설정 → 지금 한 번 점검", 또는:
```powershell
.venv\Scripts\python alerts_run.py          # 1회
.venv\Scripts\python alerts_run.py --test   # 테스트 메시지
```
