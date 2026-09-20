# evals-verification-log

* 시리즈명: `evals-verification-log`
* 성격: evals 검증 포트폴리오형 엔지니어링 로그. 잘된 것만이 아니라 실패, 조건, 수치를 함께 남긴다.
* 시작: 2026-09-09. GitHub 공개는 블로그 완성 이후로 보류. 당분간 요약 발행으로 로그 개념을 잡는다.
* 정본 저장소: `evals-archive/docs/evals-verification-log/`
* 원본 리포트: `../20-week-cycle-2026-09-07/reports/`, 주간 기록: `../20-week-cycle-2026-09-07/weeks/`
* 허브: `_personal/portfolio/docs/projects/evals/progress.md`

## 로그 작성 원칙

1. 측정하지 않은 수치를 만들지 않는다.
2. 질문, 범위, 데이터, 측정법, 결과, 실패분류, 판정, 한계를 매 편에 넣는다.
3. 원본 데이터와 실행 로그는 고치지 않고 링크로 연결한다.
4. 요약 로그는 짧게, 원본 리포트는 길게. 요약에서 원본으로 역추적 가능해야 한다.

## 글 목록

| # | 제목 | 원본 | 상태 |
|---|---|---|---|
| 00 | 시리즈 소개. 왜 검증 로그인가 | - | 본 파일 |
| 01 | 쏜다 입금 대조 엔진 기준선. 44건으로 재현한 34.1% | R1 `2026-09-07-r1-ssonda-baseline.md` | 요약 발행 |
| 02 | Spark vs Opus 5 High + 완전블라인드 20건 동점. R2+R3 합본으로 발행 | R2 `2026-09-08-r2-llm-compare.md`, R3 `2026-09-08-r3-blind2.md` | 요약 발행 2026-09-10 |
| 03 | 실패 5종 pass^3 양쪽 15/15. R4 기반 3편 | R4 `2026-09-10-r4-pass3.md` | 요약 발행 2026-09-11 |
| 04 | 채점 기준이 결과를 만든다. TypeSafe Choice 1000건 이중 채점 | R5 `2026-09-20-r5-typesafe-worktype.md` | 초안 작성 2026-09-20 |
| 05~ | Week 2 실제 농가 문장 10건 확보 후 순차 추가 | weeks/02.md 이후 | 예정 |

## 요약 vs 원본 역할

* 이 폴더 글: 5분 요약. 결론, 수치 1표, 실패 3줄, 한계 2줄.
* reports/: 전문. 재현 명령, SHA-256, 혼동행렬까지 포함.
* weeks/: 주간 작업일지. 그 주에 뭘 바꿨는지 기록.

## 다음에 할 일

* 01 요약글을 이 원칙에 맞춰 발행한다.
* 02, 03은 01 형식이 굳어진 뒤 같은 틀로 추가한다.
* GitHub 공개는 로그 5편 이상 쌓인 뒤에 검토한다.

## 발행 기록
- 01 네이버 발행 완료: 2026-09-09, justdoim 실측 리포트, logNo 224406449536
  https://blog.naver.com/PostView.naver?blogId=justdoim&logNo=224406449536&parentCategoryNo=&categoryNo=8&viewDate=&isShowPopularPosts=false&from=postView

## 개정 이력
- 2026-09-09: 1편 전면 리뉴얼. 줄바꿈 유실 수정(네이버 SE는 한 줄씩 Enter+대기 필요, 빠른 \n 타이핑은 씹힘), 실제 문항 3개(cm-01/af-01/ns-01) 공개, 9개 유형별 성적표, 혼동행렬 추가.

## 발행 기록 (추가)
- 2026-09-10: 02편 네이버 발행 완료. justdoim 실측 리포트, logNo 224407534486
  https://blog.naver.com/PostView.naver?blogId=justdoim&logNo=224407534486&parentCategoryNo=&categoryNo=8&viewDate=&isShowPopularPosts=false&from=postView

## R4·3편 준비 (2026-09-10)
- R4 리포트 작성: reports/2026-09-10-r4-pass3.md (8섹션, F1~F5 전부 3/3, Spark 15/15 vs Opus 15/15)
- 3편 초안 준비: evals-verification-log/03-naver-draft.md (발행 대기, 내일 발행 예정)

## 발행 기록 (추가2)
- 2026-09-11: 03편 네이버 발행 완료. justdoim 실측 리포트, logNo 224407992017
  https://blog.naver.com/PostView.naver?blogId=justdoim&logNo=224407992017&parentCategoryNo=&categoryNo=8&viewDate=&isShowPopularPosts=false&from=postView
