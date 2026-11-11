# DatabricksAppsTest

Databricks Apps를 이해하기 위한 학습용 프로젝트입니다. 실제로 배포되는 예제 앱과, 그 앱을 기준으로 설명하는 가이드 문서로 이루어져 있습니다.

## 구성

| 경로 | 내용 |
|---|---|
| `app.py` | Streamlit 예제 앱. 환경변수, 사용자 헤더, 두 가지 신원, Genie 리소스, 모델 서빙 호출을 화면에서 확인합니다. |
| `app.yaml` | 앱 실행 명령과 환경변수 설정 |
| `requirements.txt` | 추가 Python 패키지 |
| `docs/index.html` | Databricks Apps 가이드 (스크린샷 포함) |

## 가이드 보기

저장소를 받은 뒤 `docs/index.html`을 브라우저로 엽니다.

## 로컬 실행

```bash
export DATABRICKS_CONFIG_PROFILE=<CLI 프로필>
export GENIE_SPACE_ID=<Genie space ID>
streamlit run app.py
```

## 배포

앱에 이 저장소가 Git 소스로 등록돼 있습니다. push한 뒤 배포 명령을 실행해야 앱에 반영됩니다.

```bash
git push origin main
databricks apps deploy databricksappstestt --git-branch main -p <CLI 프로필>
```
