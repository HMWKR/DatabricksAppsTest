"""Databricks Apps 학습용 예제 앱 (Streamlit).

플랫폼이 앱에 주입하는 것(환경변수, HTTP 헤더, 두 종류의 신원, 리소스)을
화면에서 직접 확인하기 위한 앱이다. 설명은 docs/index.html 가이드를 참고한다.
"""

import os

import pandas as pd
import streamlit as st
from databricks.sdk import WorkspaceClient

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


def app_client() -> WorkspaceClient:
    """앱 전용 서비스 프린시펄 권한으로 동작하는 클라이언트."""
    return WorkspaceClient()


def user_client(user_token: str) -> WorkspaceClient:
    """접속한 사용자 권한(사용자 대리 인증)으로 동작하는 클라이언트."""
    # SP 자격증명 환경변수가 함께 있으므로 인증 방식을 명시해야 한다.
    return WorkspaceClient(
        host=os.getenv("DATABRICKS_HOST"), token=user_token, auth_type="pat"
    )


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

    identity = st.radio(
        "어느 권한으로 질문할까요?",
        ["앱 권한 (서비스 프린시펄)", "사용자 권한 (사용자 대리 인증)"],
        horizontal=True,
    )
    question = st.text_input("질문", placeholder="예: 가장 많이 팔린 제품 5개는?")
    if not st.button("질문 보내기") or not question.strip():
        return

    if identity.startswith("사용자"):
        user_token = st.context.headers.get(USER_TOKEN_HEADER)
        if not user_token:
            st.warning("사용자 토큰이 없어 사용자 권한으로 질문할 수 없습니다.")
            return
        client = user_client(user_token)
    else:
        client = app_client()

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


def main() -> None:
    st.set_page_config(page_title="Databricks Apps 학습 앱", layout="wide")
    st.title("Databricks Apps 학습 앱")
    st.caption("플랫폼이 앱에 무엇을 주입하는지 직접 확인하는 예제입니다.")

    env_tab, header_tab, identity_tab, genie_tab = st.tabs(
        ["1. 실행 환경", "2. 접속 사용자", "3. 두 가지 신원", "4. Genie 리소스"]
    )
    with env_tab:
        render_environment()
    with header_tab:
        render_headers()
    with identity_tab:
        render_identities()
    with genie_tab:
        render_genie()


main()
