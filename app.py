"""Databricks Apps 학습용 예제 앱 (Streamlit).

플랫폼이 앱에 주입하는 것(환경변수, HTTP 헤더, 두 종류의 신원, 리소스)을
화면에서 직접 확인하기 위한 앱이다. 설명은 docs/index.html 가이드를 참고한다.
"""

import os

import pandas as pd
import streamlit as st
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    ChatMessage,
    ChatMessageRole,
    EndpointStateReady,
)

# 플랫폼이 자동 주입하는 환경변수 (비밀 값은 화면에 출력하지 않는다)
AUTO_ENV_NAMES = [
    "DATABRICKS_APP_NAME",
    "DATABRICKS_APP_PORT",
    "DATABRICKS_HOST",
    "DATABRICKS_WORKSPACE_ID",
    "DATABRICKS_CLIENT_ID",
    "DATABRICKS_CLIENT_SECRET",
]
SECRET_ENV_NAMES = {"DATABRICKS_CLIENT_SECRET"}

# 플랫폼의 리버스 프록시가 요청마다 붙여 주는 헤더
IDENTITY_HEADERS = [
    "X-Forwarded-Email",
    "X-Forwarded-Preferred-Username",
    "X-Forwarded-User",
    "X-Real-Ip",
    "X-Request-Id",
]
USER_TOKEN_HEADER = "X-Forwarded-Access-Token"

# app.yaml 의 valueFrom: genie-space 로 주입되는 값
GENIE_SPACE_ID = os.getenv("GENIE_SPACE_ID", "")
GENIE_RESULT_ROW_LIMIT = 100

# 서빙 엔드포인트를 리소스로 추가하고 valueFrom 으로 연결했을 때 들어오는 이름 (선택)
SERVING_ENDPOINT = os.getenv("SERVING_ENDPOINT", "")
CHAT_TASK = "llm/v1/chat"
MODEL_MAX_TOKENS = 300

# 플랫폼 위에서 실행 중인지 여부 (로컬 실행에는 이 변수가 없다)
RUNNING_ON_PLATFORM = bool(os.getenv("DATABRICKS_APP_NAME"))


def app_client() -> WorkspaceClient:
    """앱 전용 서비스 프린시펄 권한으로 동작하는 클라이언트."""
    return WorkspaceClient()


def user_client(user_token: str) -> WorkspaceClient:
    """접속한 사용자 권한(사용자 대리 인증)으로 동작하는 클라이언트."""
    # SP 자격증명 환경변수가 함께 있으므로 인증 방식을 명시해야 한다.
    return WorkspaceClient(
        host=os.getenv("DATABRICKS_HOST"), token=user_token, auth_type="pat"
    )


def acting_user_client(required_scope: str) -> WorkspaceClient | None:
    """데이터·모델 호출에 쓸 클라이언트. 접속한 사용자 권한으로만 동작한다.

    앱 권한으로 호출하면 앱 사용 권한만 있는 사람이 서비스 프린시펄의
    권한을 빌려 쓰게 되므로, 플랫폼 위에서는 사용자 토큰이 없으면 호출하지 않는다.
    """
    user_token = st.context.headers.get(USER_TOKEN_HEADER)
    if user_token:
        return user_client(user_token)
    if RUNNING_ON_PLATFORM:
        st.warning(
            f"사용자 토큰이 없습니다. 앱의 사용자 권한 scope 에 {required_scope} 를 "
            "추가해야 합니다."
        )
        return None
    # 로컬 실행: 개발자 본인의 CLI 프로필 권한으로 동작한다.
    return app_client()


def render_environment() -> None:
    st.subheader("플랫폼이 주입한 환경변수")
    rows = []
    for name in AUTO_ENV_NAMES:
        value = os.getenv(name)
        if value is None:
            shown = "(없음 - 로컬 실행으로 보입니다)"
        elif name in SECRET_ENV_NAMES:
            shown = "(설정됨 - 값은 표시하지 않음)"
        else:
            shown = value
        rows.append({"환경변수": name, "값": shown})
    st.table(pd.DataFrame(rows))

    st.subheader("app.yaml 에서 직접 정의한 환경변수")
    st.table(
        pd.DataFrame(
            [{"환경변수": "GENIE_SPACE_ID", "값": GENIE_SPACE_ID or "(없음)"}]
        )
    )
    st.caption("GENIE_SPACE_ID 는 app.yaml 의 valueFrom: genie-space 로 들어온 값입니다.")


def render_headers() -> None:
    headers = st.context.headers
    st.subheader("요청에 붙어 온 사용자 정보 헤더")
    rows = [
        {"헤더": name, "값": headers.get(name) or "(없음)"} for name in IDENTITY_HEADERS
    ]
    has_token = bool(headers.get(USER_TOKEN_HEADER))
    rows.append(
        {
            "헤더": USER_TOKEN_HEADER,
            "값": "(전달됨 - 값은 표시하지 않음)" if has_token else "(없음)",
        }
    )
    st.table(pd.DataFrame(rows))
    if not has_token:
        st.info(
            "사용자 토큰이 없습니다. 로컬 실행이거나 앱에 사용자 권한 scope 가 "
            "설정되지 않은 경우입니다."
        )


def render_identities() -> None:
    st.subheader("같은 API 를 두 신원으로 호출하기")
    st.write("`current_user.me()` 를 앱 권한과 사용자 권한으로 각각 호출합니다.")
    if not st.button("신원 비교 실행"):
        return

    left, right = st.columns(2)
    with left:
        st.markdown("**앱 권한 (서비스 프린시펄)**")
        try:
            me = app_client().current_user.me()
            st.success(me.display_name or me.user_name)
            st.caption(f"user_name: {me.user_name}")
        except Exception as exc:
            st.error(f"호출 실패: {exc}")
    with right:
        st.markdown("**사용자 권한 (사용자 대리 인증)**")
        user_token = st.context.headers.get(USER_TOKEN_HEADER)
        if not user_token:
            st.warning("사용자 토큰이 없어 호출할 수 없습니다.")
            return
        try:
            me = user_client(user_token).current_user.me()
            st.success(me.display_name or me.user_name)
            st.caption(f"user_name: {me.user_name}")
        except Exception as exc:
            st.error(f"호출 실패: {exc}")


def query_result_frame(client: WorkspaceClient, message, attachment) -> pd.DataFrame:
    """Genie 가 실행한 SQL 의 결과를 표로 바꾼다."""
    response = client.genie.get_message_attachment_query_result(
        message.space_id,
        message.conversation_id,
        message.message_id,
        attachment.attachment_id,
    )
    statement = response.statement_response
    columns = [column.name for column in statement.manifest.schema.columns]
    data = (statement.result.data_array or [])[:GENIE_RESULT_ROW_LIMIT]
    return pd.DataFrame(data, columns=columns)


def render_genie() -> None:
    st.subheader("Genie space 에 질문하기")
    if not GENIE_SPACE_ID:
        st.warning(
            "GENIE_SPACE_ID 가 없습니다. 앱에 Genie space 리소스를 추가하고 "
            "app.yaml 에서 valueFrom 으로 연결해야 합니다."
        )
        return

    st.caption("질문은 접속한 사용자의 권한으로 실행됩니다.")
    question = st.text_input("질문", placeholder="예: 가장 많이 팔린 제품 5개는?")
    if not st.button("질문 보내기") or not question.strip():
        return

    client = acting_user_client("genie")
    if client is None:
        return

    try:
        with st.spinner("Genie 가 답을 만드는 중입니다..."):
            message = client.genie.start_conversation_and_wait(
                GENIE_SPACE_ID, question.strip()
            )
        for attachment in message.attachments or []:
            if attachment.text and attachment.text.content:
                st.write(attachment.text.content)
            if attachment.query:
                if attachment.query.description:
                    st.write(attachment.query.description)
                st.code(attachment.query.query, language="sql")
                st.dataframe(query_result_frame(client, message, attachment))
    except Exception as exc:
        st.error(f"Genie 호출 실패: {exc}")


def chat_endpoint_names(client: WorkspaceClient) -> list[str]:
    """채팅 형식으로 호출할 수 있고 준비가 끝난 서빙 엔드포인트 이름."""
    return sorted(
        endpoint.name
        for endpoint in client.serving_endpoints.list()
        if endpoint.task == CHAT_TASK
        and endpoint.state
        and endpoint.state.ready == EndpointStateReady.READY
    )


def message_text(content) -> str:
    """응답 본문을 문자열로 바꾼다. 모델에 따라 문자열 또는 조각 목록으로 온다."""
    if isinstance(content, str):
        return content
    parts = [part.get("text", "") for part in content or [] if isinstance(part, dict)]
    return "\n".join(part for part in parts if part)


def render_model_serving() -> None:
    st.subheader("서빙된 모델 호출하기")
    st.caption("모델 호출은 접속한 사용자의 권한으로 실행됩니다.")

    client = acting_user_client("model-serving")
    if client is None:
        return

    try:
        names = chat_endpoint_names(client)
    except Exception as exc:
        st.error(f"엔드포인트 목록 조회 실패: {exc}")
        return
    if not names:
        st.info("호출할 수 있는 채팅 모델 엔드포인트가 없습니다.")
        return

    # app.yaml 의 valueFrom 으로 엔드포인트를 지정했으면 그것을 기본값으로 쓴다.
    default_index = names.index(SERVING_ENDPOINT) if SERVING_ENDPOINT in names else 0
    endpoint_name = st.selectbox("엔드포인트", names, index=default_index)
    prompt = st.text_area("프롬프트", placeholder="예: Databricks Apps 를 한 문장으로 설명해줘")
    if not st.button("모델에 보내기") or not prompt.strip():
        return

    try:
        with st.spinner("모델이 답을 만드는 중입니다..."):
            response = client.serving_endpoints.query(
                name=endpoint_name,
                messages=[
                    ChatMessage(role=ChatMessageRole.USER, content=prompt.strip())
                ],
                max_tokens=MODEL_MAX_TOKENS,
            )
        st.write(message_text(response.choices[0].message.content))
        if response.usage:
            st.caption(
                f"입력 {response.usage.prompt_tokens} 토큰, "
                f"출력 {response.usage.completion_tokens} 토큰"
            )
    except Exception as exc:
        st.error(f"모델 호출 실패: {exc}")


def main() -> None:
    st.set_page_config(page_title="Databricks Apps 학습 앱", layout="wide")
    st.title("Databricks Apps 학습 앱")
    st.caption("플랫폼이 앱에 무엇을 주입하는지 직접 확인하는 예제입니다.")

    env_tab, header_tab, identity_tab, genie_tab, model_tab = st.tabs(
        ["실행 환경", "접속 사용자", "두 가지 신원", "Genie 리소스", "모델 서빙"]
    )
    with env_tab:
        render_environment()
    with header_tab:
        render_headers()
    with identity_tab:
        render_identities()
    with genie_tab:
        render_genie()
    with model_tab:
        render_model_serving()


main()
