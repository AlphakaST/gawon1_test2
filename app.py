# app.py — 3문항 확장 (배포·로컬 호환 / dat2·pr 스키마 / 풀링 안정화)
# -*- coding: utf-8 -*-
from __future__ import annotations
import os, json
from typing import Dict, Any, List, Tuple

import streamlit as st
import mysql.connector
from mysql.connector import Error as MySQLError
from mysql.connector import pooling
from openai import OpenAI
from PIL import Image, UnidentifiedImageError

# ─────────────────────────────────────────────────────
# 페이지/상수
# ─────────────────────────────────────────────────────
st.set_page_config(page_title="서술형 평가 — 상태 변화와 열에너지 (3문항)", page_icon="🧪", layout="wide")
ID_REGEX = r"^\d{5}$"
IMAGE_FILENAMES = ["image1.png", "image2.png", "image3.png"]

# ── 문항 텍스트 (UI 표기용) ──
QUESTION_TEXTS = [
    # Q1
    (
        "추운 겨울 농부들은 오렌지 농장의 오렌지가 어는 것을 막기 위해서 오렌지 나무에 물을 뿌려준다.\n\n"
        "이렇게 하는 이유를 <조건>에 맞게 서술하시오.\n\n"
        "<조건>\n\n"
        "• 물의 상태 변화를 포함하여 서술할 것\n\n"
        "• 에너지 출입을 포함하여 서술할 것\n"
    ),
    # Q2
    (
        "요즈음에는 더운 여름철에도 각종 냉동식품이 녹지 않은 상태로 배송되고, 육류나 생선 등도 신선하게 배송된다.\n\n"
        "이는 단열이 잘 되는 스타이로폼 박스에 드라이아이스 또는 물을 담아 얼린 아이스팩을 함께 포장하기 때문이다.\n\n"
        "드라이아이스는 이산화 탄소를 압축하고 냉각하여 만든 고체이다. 드라이아이스는 1기압에서 –78.5℃에 승화하므로 드라이아이스를 공기 중에 두면 부피가 점점 작아지는 것처럼 보인다.\n\n"
        "스타이로폼 박스에 드라이아이스와 물을 얼린 아이스팩을 각각 넣고 포장하였을 때 공통점과 차이점을 <조건>에 맞게 서술하시오.\n\n"
        "<조건>\n\n"
        "∙ 공통점은 상태 변화 시 열에너지 출입 및 주위의 온도 변화와 관련지어 설명하시오.\n\n"
        "∙ 차이점은 상태 변화와 관련지어 설명하시오.\n"
    ),
    # Q3
    (
        "불에 타기 쉬운 종이로 만든 냄비가 캠핑족들에게 인기를 끌고 있다. 종이로 만든 냄비가 왜 불에 타지 않을까? "
        "물을 담은 종이 냄비를 가열 장치 위에 올려두고 가열하면 물의 온도가 서서히 올라가다가 물의 끓는점에 이르면 온도가 일정해지면서 물이 끓는다. 그러나 이때 종이 냄비는 불에 타지 않는다. 그 이유는 무엇일까?\n"
        "어떤 물질이 산소와 결합하여 빛과 열을 내는 현상을 연소라고 한다. 연소가 일어나기 위해서는 탈 물질, 산소, 발화점 이상의 온도의 3가지 조건이 갖추어져야 한다. "
        "이때 발화점이란 공기 중에서 물질을 마찰시키거나 가열할 때 불이 붙어 타기 시작하는 가장 낮은 온도를 말한다. 물질의 종류에 따라 발화점은 달라지는데, 종이의 발화점은 약 450℃이다.\n\n"
        "종이 냄비에 물을 넣고 가열할 때                                            ㉠                                         때문에 종이 냄비의 온도가 발화점 이상으로 올라가지 않는다. 따라서 종이 냄비를 이용하여 간단한 요리를 할 수 있다. "
        "종이 냄비에 물을 넣지 않고 가열하면                                    ㉡                                 때문에 주의한다.\n\n"
        "㉠과 ㉡에 들어갈 알맞은 말을 <조건>에 맞추어 서술하시오.\n\n"
        "<조건>\n\n"
        "∙ ㉠에 들어갈 알맞은 말을 상태 변화와 열에너지와 관련지어 설명하시오.\n\n"
        "∙ ㉡에 들어갈 알맞은 말을 발화점과 관련지어 설명하시오.\n"
    ),
]

# ── 예시 답안(프롬프트 보조용) ──
EXAMPLES = [
    (
        "- 오렌지 나무에 물을 뿌리면 물이 얼면서(응고) 주위로 응고열을 방출하여 주변 온도가 올라가 오렌지가 어는 것을 막는다.\n"
        "- 물이 얼 때 에너지를 방출(열 방출)하므로 주변이 따뜻해지는 효과가 있다.\n"
    ),
    (
        "공통점: 드라이아이스와 아이스팩의 얼음 모두 상태 변화 과정에서 주위의 열에너지를 흡수해 박스 내부 온도를 낮춘다.\n"
        "차이점: 드라이아이스는 고체→기체로 승화, 얼음은 고체→액체로 융해된다.\n"
    ),
    (
        "㉠: 외부에서 공급된 열에너지가 물의 끓음/기화(상태 변화)에 사용(잠열)되기 때문\n"
        "㉡: 물이 없으면 종이가 발화점(≈450℃)에 도달해 연소 위험이 있기 때문\n"
    ),
]

# ── 채점 규칙(간단 키워드 감지 + 모델 자가표시) ──
SCORING_RULES: List[Dict[str, Any]] = [
    {  # Q1: 상태 변화(응고/얼다) + 열 방출 언급
        "max_score": 7,
        "must_include": {
            "freezing": ["응고", "얼", "얼음", "빙결"],
            "heat_release": ["열을 방출", "열 방출", "응고열", "에너지 방출", "주위의 온도 올라", "따뜻"],
        },
        "partial_score": 2,
    },
    {  # Q2: 공통(열 흡수/온도 하강) + 차이(승화 vs 융해)
        "max_score": 7,
        "must_include": {
            "heat_absorb_common": ["열을 흡수", "열에너지 흡수", "주위의 열", "온도 낮", "냉각", "차갑"],
            "sublimation": ["승화", "고체에서 기체", "고→기"],
            "fusion": ["융해", "녹", "고체에서 액체", "고→액"],
        },
        "partial_score": 2,
    },
    {  # Q3: ㉠ 상태 변화에 열 사용(잠열) + ㉡ 발화점 위험
        "max_score": 7,
        "must_include": {
            "phase_change_energy": ["상태 변화", "끓", "기화", "증발", "잠열", "열에너지 사용", "열을 사용"],
            "ignition_point": ["발화점", "450", "불이 붙", "연소", "화재", "타기 시작"],
        },
        "partial_score": 2,
    },
]

# ─────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────
def validate_student_id(s: str) -> bool:
    import re
    return bool(s and re.match(ID_REGEX, s))

def get_model_name() -> str:
    return st.secrets.get("OPENAI_MODEL", "gpt-5")

# ─────────────────────────────────────────────────────
# DB (mysql-connector) — 커넥션 풀 사용
# ─────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_mysql_pool():
    cfg = st.secrets.get("connections", {}).get("mysql", {})
    return pooling.MySQLConnectionPool(
        pool_name="app_pool",
        pool_size=5,
        host=cfg.get("host"),
        port=cfg.get("port", 3306),
        database=cfg.get("database"),
        user=cfg.get("user"),
        password=cfg.get("password"),
        autocommit=True,
    )

def get_conn():
    return get_mysql_pool().get_connection()


def init_tables() -> None:
    """DAT2 테이블 보장 및 필요한 컬럼 확장."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        # 최신 스키마 생성
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS DAT2 (
              id         VARCHAR(16) NOT NULL,
              answer1    MEDIUMTEXT,
              feedback1  MEDIUMTEXT,
              answer2    MEDIUMTEXT,
              feedback2  MEDIUMTEXT,
              answer3    MEDIUMTEXT,
              feedback3  MEDIUMTEXT,
              opinion1   MEDIUMTEXT,
              time       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              PRIMARY KEY (id)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """
        )
        # 구버전 대비 누락 컬럼 보강 (MySQL 8.0+)
        for col in [
            ("answer2", "MEDIUMTEXT"), ("feedback2", "MEDIUMTEXT"),
            ("answer3", "MEDIUMTEXT"), ("feedback3", "MEDIUMTEXT"),
        ]:
            try:
                cur.execute(f"ALTER TABLE DAT2 ADD COLUMN IF NOT EXISTS {col[0]} {col[1]}")
            except MySQLError:
                pass
        cur.close(); conn.close()
    except MySQLError as e:
        st.error(f"[DB] 테이블 초기화 실패: {e}")


def upsert_dat2_multi(student_id: str, payloads: List[Tuple[str, str]], opinion1: str | None) -> None:
    """3문항 일괄 UPSERT. opinion1=None이면 기존 의견 보존.
    payloads 형식: [(answer_str, feedback_json_str)] * 3
    """
    try:
        conn = get_conn(); cur = conn.cursor()
        ans = [None, None, None]; fb = [None, None, None]
        for i, (a, f) in enumerate(payloads):
            ans[i] = a; fb[i] = f
        cur.execute(
            """
            INSERT INTO DAT2 (id, answer1, feedback1, answer2, feedback2, answer3, feedback3, opinion1)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) AS new
            ON DUPLICATE KEY UPDATE
              answer1 = new.answer1,
              feedback1 = new.feedback1,
              answer2 = new.answer2,
              feedback2 = new.feedback2,
              answer3 = new.answer3,
              feedback3 = new.feedback3,
              opinion1 = COALESCE(new.opinion1, DAT2.opinion1)
            """,
            (student_id, ans[0], fb[0], ans[1], fb[1], ans[2], fb[2], opinion1),
        )
        cur.close(); conn.close()
    except MySQLError as e:
        st.error(f"[DB] 저장 실패: {e}")
        raise


def update_opinion_only(student_id: str, opinion1: str) -> None:
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE DAT2 SET opinion1=%s WHERE id=%s", (opinion1, student_id))
        cur.close(); conn.close()
    except MySQLError as e:
        st.error(f"[DB] 의견 저장 실패: {e}")
        raise

# ─────────────────────────────────────────────────────
# OpenAI 채점 (gpt-5 호환 처리: temperature 미전달, max_tokens 재시도)
# ─────────────────────────────────────────────────────

def build_messages(qidx: int, answer_kr: str) -> List[Dict[str, str]]:
    rules = json.dumps(SCORING_RULES[qidx], ensure_ascii=False)
    system = "당신은 한국 중학교 과학 보조채점자입니다. 아래 규칙을 엄격히 적용하고, 반드시 JSON만 출력하세요."

    # 각 문항별 검출 키 지정
    if qidx == 0:
        detected_schema = '{"freezing": true/false, "heat_release": true/false}'
    elif qidx == 1:
        detected_schema = '{"heat_absorb_common": true/false, "sublimation": true/false, "fusion": true/false}'
    else:
        detected_schema = '{"phase_change_energy": true/false, "ignition_point": true/false}'

    user = f"""
[문항]
{QUESTION_TEXTS[qidx]}

[학생 답안]
{answer_kr}

[채점 규칙(JSON)]
{rules}

[예시 답안/유의]
{EXAMPLES[qidx]}

[출력 형식(JSON only)]
{{
  "score": number,
  "reason": "채점 근거(간단)",
  "feedback": "친근한 한국어 3~4문장",
  "detected": {detected_schema}
}}
- 규칙을 반드시 따르세요. 임의 가중치/총점 변경 금지.
- 유효한 JSON만 반환(문장/코드펜스 금지).
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def grade_one(qidx: int, student_answer: str) -> Dict[str, Any]:
    api_key = st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 없습니다. .streamlit/secrets.toml 확인")
    client = OpenAI(api_key=api_key)
    model = get_model_name()
    messages = build_messages(qidx, student_answer)

    base_kwargs = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    kwargs = dict(base_kwargs); kwargs["max_tokens"] = 600

    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as e:
        msg = str(e).lower()
        if "max_tokens" in msg or "unsupported" in msg or "temperature" in msg:
            resp = client.chat.completions.create(**base_kwargs)
        else:
            raise

    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(content[start:end+1])
        else:
            raise RuntimeError("모델 응답 JSON 파싱 실패")

    # 규칙 재적용(안전 가드)
    det = data.get("detected", {})
    ps = SCORING_RULES[qidx]["partial_score"]
    full = False; partial = False

    if qidx == 0:
        a = bool(det.get("freezing")); b = bool(det.get("heat_release"))
        full = a and b
        partial = (a ^ b)
    elif qidx == 1:
        heat = bool(det.get("heat_absorb_common"))
        subl = bool(det.get("sublimation"))
        fus  = bool(det.get("fusion"))
        full = heat and subl and fus
        partial = (heat and (subl or fus)) or ((subl and fus) and not heat)
    else:  # qidx == 2
        pce = bool(det.get("phase_change_energy"))
        ign = bool(det.get("ignition_point"))
        full = pce and ign
        partial = (pce ^ ign)

    data["score"] = SCORING_RULES[qidx]["max_score"] if full else (ps if partial else 0)
    data.setdefault("reason", ""); data.setdefault("feedback", "")
    data["detected"] = det
    return data

# ─────────────────────────────────────────────────────
# 메인 UI
# ─────────────────────────────────────────────────────

# (발췌 수정 부분만 반영)

# ─────────────────────────────────────────────────────
# 메인 UI
# ─────────────────────────────────────────────────────

def render_question_block(qidx: int, answer_key: str, placeholder: str, height: int = 150):
    col_q, col_img = st.columns([2, 1])
    with col_q:
        st.subheader(f"문항 {qidx+1}")
        st.write(QUESTION_TEXTS[qidx])
    with col_img:
        img_path = os.path.join("image", IMAGE_FILENAMES[qidx])
        if os.path.isfile(img_path):
            try:
                with Image.open(img_path) as im:
                    st.image(im, caption="문항 참고 이미지", use_container_width=True)
            except UnidentifiedImageError:
                st.info(f"이미지 형식 인식 실패: {os.path.basename(img_path)}")
            except Exception as e:
                st.info(f"이미지 로드 실패({os.path.basename(img_path)}): {e}")
        else:
            st.info(f"이미지 파일을 찾을 수 없습니다: {img_path}")

    # 바로 뒤에 답안 작성 칸 배치
    return st.text_area(f"[문항 {qidx+1}] 나의 답안", key=answer_key, height=height, placeholder=placeholder)


def main():
    st.title("🧪 서술형 평가 — 상태 변화와 열에너지 (3문항)")
    st.caption("GPT 자동 채점·피드백 → ‘한 가지 의견’까지 제출해 주세요.")

    # 테이블 보장
    init_tables()

    with st.form("student_form", clear_on_submit=False):
        sid = st.text_input("학번(5자리, 예: 10130)", placeholder="학번을 입력하세요.")

        # 문제 블록별 답안 입력
        answer1 = render_question_block(0, "ans1", "오렌지에 물을 뿌리면 왜 어는 것을 막을 수 있을까요?", 140)
        st.divider()
        answer2 = render_question_block(1, "ans2", "드라이아이스 vs 아이스팩 — 공통점/차이점", 160)
        st.divider()
        answer3 = render_question_block(2, "ans3", "종이 냄비 ㉠, ㉡에 들어갈 말", 160)

        submitted = st.form_submit_button("채점 받기", type="primary")

    # 이후 로직(answer1,2,3 수집 → grade_one → DB 저장)은 그대로 유지


    if submitted:
        if not validate_student_id(sid):
            st.error("학번 형식이 올바르지 않습니다. (예: 10130)")
            return
        if not (answer1.strip() and answer2.strip() and answer3.strip()):
            st.error("세 문항 모두 답안을 입력해 주세요.")
            return

        answers = [answer1.strip(), answer2.strip(), answer3.strip()]
        results: List[Dict[str, Any]] = []

        try:
            with st.spinner("채점 중입니다…"):
                for i in range(3):
                    results.append(grade_one(i, answers[i]))
        except Exception as e:
            st.error(f"OpenAI 호출 실패: {e}")
            return

        # 결과 표시
        for i, res in enumerate(results):
            st.success(f"문항 {i+1} 점수: **{res.get('score', 0)} / {SCORING_RULES[i]['max_score']}**")
            if res.get("reason"):
                st.write(":memo: **채점 근거**")
                st.write(res["reason"])
            st.write(":bulb: **피드백**")
            st.write(res.get("feedback", ""))

            det = res.get("detected", {})
            with st.expander("조건 충족 여부"):
                if i == 0:
                    st.write(f"상태변화(응고/얼음) 언급: {'✅' if det.get('freezing') else '❌'}")
                    st.write(f"열 방출/응고열 언급: {'✅' if det.get('heat_release') else '❌'}")
                elif i == 1:
                    st.write(f"공통점(열 흡수/온도 하강) 언급: {'✅' if det.get('heat_absorb_common') else '❌'}")
                    st.write(f"차이점-승화(드라이아이스): {'✅' if det.get('sublimation') else '❌'}")
                    st.write(f"차이점-융해(얼음): {'✅' if det.get('fusion') else '❌'}")
                else:
                    st.write(f"㉠ 상태 변화에 열 사용(잠열) 언급: {'✅' if det.get('phase_change_energy') else '❌'}")
                    st.write(f"㉡ 발화점/연소 위험 언급: {'✅' if det.get('ignition_point') else '❌'}")

        # DB 저장
        try:
            payloads = []
            for i in range(3):
                pack = {
                    "score": results[i].get("score", 0),
                    "max": SCORING_RULES[i]["max_score"],
                    "reason": results[i].get("reason", ""),
                    "feedback": results[i].get("feedback", ""),
                    "detected": results[i].get("detected", {}),
                }
                payloads.append((answers[i], json.dumps(pack, ensure_ascii=False)))

            upsert_dat2_multi(
                student_id=sid.strip(),
                payloads=payloads,
                opinion1=None,  # 초기 제출 시 의견 없음(보존)
            )
            st.success("채점/피드백이 저장되었습니다. 아래에 ‘한 가지 의견’을 작성해 주세요.")
            st.session_state["last_id"] = sid.strip()
        except MySQLError:
            return

    if st.session_state.get("last_id"):
        st.divider()
        st.subheader("🗣️ 한 가지 의견 제출")
        st.caption("피드백을 읽고, 무엇을 알게 되었는지/여전히 어려운 점은 무엇인지 3~5문장으로 작성하세요.")

        op = st.text_area("나의 의견", key="opinion_text", height=120)
        sid_current = st.session_state["last_id"]

        if st.button("의견 제출", key="btn_op_submit"):
            if not op.strip():
                st.warning("의견을 입력해 주세요.")
            else:
                try:
                    update_opinion_only(sid_current.strip(), op.strip())
                    st.success("의견이 저장되었습니다. 수고했어요! ✨")
                    st.session_state.pop("last_id", None)
                    st.session_state.pop("opinion_text", None)
                except MySQLError:
                    pass
    # ⬆️⬆️ 여기까지 추가 ⬆️⬆️

if __name__ == "__main__":
    main()


