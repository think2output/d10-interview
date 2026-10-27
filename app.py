import json
import os
import base64
from pathlib import Path

import pandas as pd
import streamlit as st

import prompts
from coach import TOTAL_QUESTIONS, MAX_FOLLOW_UPS, answer_score, compare, make_report, panel_average, pick_questions, progress_percent
from llm import ask_json

ROOT = Path(__file__).parent

def character_card(mode, caption):
    path = ROOT / 'assets' / ('otter_interviewer.png' if mode == 'interview' else 'otter_ready.png')
    if path.exists():
        image = base64.b64encode(path.read_bytes()).decode('ascii')
        st.markdown(f'<div class="character-card"><img src="data:image/png;base64,{image}" alt="면접관 일러스트"><div class="caption">{caption}</div></div>', unsafe_allow_html=True)

def chat_turn(role, text, key):
    avatar = str(ROOT / 'assets' / 'otter_interviewer.png')
    with st.container(key=f'chat_{role}_{key}'):
        with st.chat_message(role, avatar=avatar if role == 'assistant' else None):
            st.write(text)

def interviewer_scene(pose='neutral'):
    poses = {'neutral': 'otter_front.png', 'adjust': 'otter_adjust.png', 'think': 'otter_think.png'}
    path = ROOT / 'assets' / poses.get(pose, 'otter_front.png')
    if not path.exists():
        path = ROOT / 'assets' / 'otter_suit.png'
    image = base64.b64encode(path.read_bytes()).decode('ascii')
    st.markdown(f'<div class="spotlight-scene"><div class="spotlight-beam"></div><div class="spotlight-pool"></div><img src="data:image/png;base64,{image}" alt="빨간 안경과 정장을 입은 수달 면접관"><div class="scene-label"><span></span> 면접관 수달</div></div>', unsafe_allow_html=True)

def main():
    st.set_page_config(page_title='AI 면접 코치', page_icon='🦦', initial_sidebar_state='collapsed')
    st.markdown(f'<style>{(ROOT / "style.css").read_text(encoding="utf-8")}</style>', unsafe_allow_html=True)

    # 로컬 키가 없을 때만 호스팅 서비스의 루트 Secrets를 사용한다.
    if not os.getenv('OPENAI_API_KEY', '').strip():
        try:
            for setting in ('OPENAI_API_KEY', 'OPENAI_MODEL', 'OPENAI_EVAL_MODEL'):
                value = st.secrets.get(setting, '')
                if value and not os.getenv(setting):
                    os.environ[setting] = str(value)
        except (FileNotFoundError, OSError):
            pass
    if not os.getenv('OPENAI_API_KEY', '').strip():
        st.info('d10-interview/.env 에 키를 넣어 주세요. 배포 환경에서는 서비스의 Secrets 설정을 확인해 주세요.')
        st.stop()

    if 'profile' not in st.session_state:
        st.markdown('<div class="brand"><span>🦦</span> 수달 면접 연습실 <span class="brand-right">오늘의 연습</span></div><div class="hero"><div class="eyebrow">오늘도 한 걸음</div><h1>우리, 면접 연습<br>시작해 볼까요?</h1><p>깐깐한 수달과 함께 답변을 단단하게.</p></div>', unsafe_allow_html=True)
        character_card('ready', '면접 준비 완료!')
        st.markdown('<div class="journey"><div><b>01</b><span>면접 5문제</span></div><div><b>02</b><span>위원 평가</span></div><div><b>03</b><span>다시 도전</span></div></div>', unsafe_allow_html=True)
        with st.container(key='setup_card'):
            st.markdown('<div class="card-heading"><span>나의 면접 준비</span><small>STEP 01</small></div>', unsafe_allow_html=True)
            st.caption('몇 가지만 알려주면 수달이 면접을 준비해요.')
            name_col, job_col = st.columns(2)
            with name_col:
                name = st.text_input('이름', placeholder='이름 또는 별명')
            with job_col:
                job = st.selectbox('직군', list(prompts.PERSONAS))
            domain = st.radio('지원 산업 분야', ['플랫폼', '커머스', '금융', '교육', '헬스케어', '기타'], horizontal=True)
            custom_domain = st.text_input('직접 입력', placeholder='예: 콘텐츠, 모빌리티') if domain == '기타' else ''
            st.markdown('**나의 경험**')
            st.markdown('<div class="experience-guide"><b>이렇게 적어보세요</b><br>어떤 상황이었는지 → 내가 한 일 → 결과와 배운 점<br><span>프로젝트, 수업, 동아리 경험도 좋아요.</span></div>', unsafe_allow_html=True)
            experience = st.text_area('내 경험', label_visibility='collapsed', placeholder='예: 팀 프로젝트에서 사용자 의견을 모아 개선할 기능의 우선순위를 정하고, 팀원들과 역할을 나누어 실행했습니다.', help='30자 이상 입력해 주세요. 실제 개인정보나 회사 기밀은 입력하지 마세요.')
            st.caption(f'{len(experience.strip())}자 · 30자 이상 입력해 주세요')
            if st.button('수달과 면접 시작하기', type='primary', use_container_width=True):
                if not name.strip():
                    st.warning('이름을 입력해 주세요.')
                elif domain == '기타' and not custom_domain.strip():
                    st.warning('산업 분야를 직접 입력해 주세요.')
                elif len(experience.strip()) < 30:
                    st.warning('내 경험을 30자 이상 입력해 주세요.')
                else:
                    try:
                        questions = pick_questions(pd.read_csv(Path(__file__).parent / 'data/questions.csv'), job)
                    except (ValueError, OSError) as exc:
                        st.error(str(exc))
                    else:
                        industry = custom_domain.strip() if domain == '기타' else domain
                        st.session_state.update(profile={'name': name.strip(), 'job': job, 'company': industry, 'experience': experience.strip()}, questions=questions, records=[[] for _ in questions], index=0, followups=0, understanding=0, evaluation=None, retries={}, polish=None, celebrated=False)
                        st.rerun()
        st.stop()

    s = st.session_state
    profile = s.profile
    # 기존 세션도 선택한 분야만 사용한다.
    profile['company'] = profile['company'].split(': ', 1)[-1]
    context_lines = prompts.CONTEXT.format(**profile).splitlines()
    context_lines[0] = context_lines[0].split(' (', 1)[0]
    context = '\n'.join(context_lines)
    with st.sidebar:
        st.markdown('### 면접 정보')
        st.caption('선택한 분야')
        st.write(profile['company'])
        st.caption('지원 직군')
        st.write(profile['job'])
        st.caption('면접관이 본 직무 이해도')
        st.progress(s.understanding / 100, text=f'{s.understanding} / 100')
        if st.button('처음부터 다시', use_container_width=True):
            for key in list(s.keys()):
                del s[key]
            st.rerun()

    st.markdown('<div class="brand"><span>🦦</span> 수달 면접 연습실 <span class="brand-right">나의 연습</span></div>', unsafe_allow_html=True)
    interview, evaluation, retry, polish, report = st.tabs(['🎤 면접', '📊 평가', '🔁 재도전', '❓ 마지막 질문', '📄 리포트'])
    with interview:
        step_html = ''.join(f'<span class="step {"done" if i < s.index else "current" if i == s.index else ""}"></span>' for i in range(TOTAL_QUESTIONS))
        title = f'질문 {s.index + 1} / {TOTAL_QUESTIONS}' if s.index < TOTAL_QUESTIONS else '오늘의 면접 완료!'
        status = '꼬리 질문에 답하는 중' if s.followups else ('답변을 기다리는 중' if s.index < TOTAL_QUESTIONS else '평가에서 나의 강점을 확인해요')
        if s.index == TOTAL_QUESTIONS:
            st.markdown('<div class="interview-heading"><span>오늘의 미션 완료</span><h2>끝까지 해냈어요!</h2><p>이제 수달과 함께 답변을 돌아봐요.</p></div>', unsafe_allow_html=True)
            character_card('ready', '다음은 평가예요')
            if not s.get('celebrated', False):
                st.balloons()
                s.celebrated = True
        st.markdown(f'<div class="stage"><div class="stage-heading"><span class="stage-title">오늘의 연습 · {title}</span><span class="stage-sub">{progress_percent(s.index)}%</span></div><div class="steps">{step_html}</div><div class="stage-status"><span class="status-dot"></span>{status}</div></div>', unsafe_allow_html=True)
        with st.container(key='interview_room'):
            scene_col, chat_col = st.columns([1, 1.25], gap='small')
            with scene_col:
                interviewer_scene(s.get('otter_pose', 'neutral'))
            with chat_col:
                st.markdown('<div class="room-chat-heading">INTERVIEW <span>면접 대화</span></div>', unsafe_allow_html=True)
                with st.container(height=380, border=False, key='conversation_scroll'):
                    for i, q in enumerate(s.questions):
                        if i > s.index:
                            break
                        chat_turn('assistant', q['question'], f'{i}_question')
                        for j, turn in enumerate(s.records[i]):
                            chat_turn(turn['role'], turn['content'], f'{i}_{j}')
        if s.index < TOTAL_QUESTIONS:
            answer = st.chat_input('답변을 입력하세요')
            if answer and answer.strip():
                q = s.questions[s.index]
                history = [{'question': x['question'], 'turns': s.records[i]} for i, x in enumerate(s.questions[:s.index + 1])]
                history[-1]['turns'] = history[-1]['turns'] + [{'role': 'user', 'content': answer.strip()}]
                try:
                    result = ask_json(prompts.INTERVIEWER.format(persona=prompts.PERSONAS[profile['job']], context=context, question=q['question'], point=q['point']), json.dumps(history, ensure_ascii=False), prompts.INTERVIEWER_SCHEMA, 'interviewer')
                    s.records[s.index].append({'role': 'user', 'content': answer.strip()})
                    s.otter_pose = {'neutral': 'adjust', 'adjust': 'think', 'think': 'neutral'}.get(s.get('otter_pose', 'neutral'), 'neutral')
                    s.understanding = max(0, min(100, result['understanding']))
                    if result['follow_up'] and s.followups < MAX_FOLLOW_UPS:
                        s.records[s.index].append({'role': 'assistant', 'content': result['reply']})
                        s.followups += 1
                    else:
                        if not result['follow_up']:
                            s.records[s.index].append({'role': 'assistant', 'content': result['reply']})
                        s.index += 1
                        s.followups = 0
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        else:
            st.success('면접이 끝났습니다. 평가 탭에서 평가를 받아 보세요.')

    with evaluation:
        st.markdown('<div class="section-intro"><span>INTERVIEW REVIEW</span><h2>네 시선으로 보는 나의 답변</h2><p>위원 한 명씩 평가를 열어보고, 마지막에 의견을 모아 볼게요.</p></div>', unsafe_allow_html=True)
        if s.index < TOTAL_QUESTIONS:
            st.info('면접을 끝내면 평가를 받을 수 있습니다.')
        else:
            if 'revealed_panel' not in s:
                s.revealed_panel = []
            st.progress(len(s.revealed_panel) / 4, text=f'위원 평가 확인 {len(s.revealed_panel)} / 4')
            roles = [('🧭', 'PO 팀장', '제품과 우선순위'), ('💻', '개발 리드', '실행과 협업'), ('🎨', '프로덕트 디자이너', '사용자 관점'), ('💬', '인사 담당자', '소통과 성장')]
            st.caption('첫 위원을 선택하면 네 위원의 평가를 준비해요. 이후 각 카드에서 한 명씩 확인할 수 있어요.')
            for row in range(2):
                cols = st.columns(2, gap='small')
                for col, position in zip(cols, range(row * 2, row * 2 + 2)):
                    icon, role, lens = roles[position]
                    with col:
                        with st.container(key=f'panel_card_{position}'):
                            st.markdown(f'<div class="panel-icon">{icon}</div><div class="panel-name">{role}</div><div class="panel-lens">{lens}</div>', unsafe_allow_html=True)
                            if position in s.revealed_panel and s.evaluation:
                                panelist = s.evaluation['panel'][position]
                                st.markdown(f"**{max(0, min(10, panelist['score']))} / 10**")
                                st.caption('먼저 짚어볼 점')
                                st.write(panelist['against'])
                                st.caption('좋았던 점')
                                st.write(panelist['good'])
                            elif st.button('평가받기', key=f'reveal_{position}', use_container_width=True):
                                try:
                                    if not s.evaluation:
                                        transcript = [{'no': i + 1, 'question': q['question'], 'turns': s.records[i]} for i, q in enumerate(s.questions)]
                                        with st.spinner('위원들이 면접 기록을 살펴보고 있어요...'):
                                            result = ask_json(prompts.EVALUATOR.format(context=context), json.dumps(transcript, ensure_ascii=False), prompts.EVAL_SCHEMA, 'evaluation')
                                        if len(result['panel']) != 4 or sorted(a['no'] for a in result['answers']) != list(range(1, TOTAL_QUESTIONS + 1)):
                                            raise ValueError('평가 결과가 완전하지 않습니다. 다시 시도해 주세요.')
                                        expected = ['PO', '개발', '디자이너', '인사']
                                        ordered = []
                                        for keyword in expected:
                                            matches = [p for p in result['panel'] if keyword.lower() in p['role'].lower()]
                                            if len(matches) != 1:
                                                raise ValueError('위원 구성을 확인하지 못했습니다. 다시 시도해 주세요.')
                                            ordered.append(matches[0])
                                        result['panel'] = ordered
                                        s.evaluation = result
                                        s.retries = {}
                                    s.revealed_panel = [*s.revealed_panel, position]
                                    st.rerun()
                                except ValueError as exc:
                                    st.error(str(exc))
            if s.evaluation and len(s.revealed_panel) == 4:
                ev = s.evaluation
                st.markdown('<div class="section-intro"><span>THE BIG PICTURE</span><h2>위원들의 평가를 모아봤어요</h2></div>', unsafe_allow_html=True)
                with st.container(key='review_summary'):
                    st.metric('위원 평균', f"{panel_average(ev['panel']):.1f} / 10")
                    st.markdown('**💬 의견이 갈린 곳**')
                    st.write(ev['conflict'])
                    st.markdown('**✨ 모두가 같은 판단**')
                    st.write(ev['agree'])
                with st.expander('위원별 평가 표 보기'):
                    st.dataframe(pd.DataFrame([{'위원': p['role'], '반론': p['against'], '좋은 점': p['good'], '점수': max(0, min(10, p['score']))} for p in ev['panel']]), hide_index=True, use_container_width=True)
                st.markdown('### 답변별 피드백')
                for a in sorted(ev['answers'], key=lambda x: x['no']):
                    with st.expander(f"답변 {a['no']} · {answer_score(a)}/20"):
                        st.write(s.questions[a['no'] - 1]['question'])
                        st.dataframe(pd.DataFrame(compare(a, a)['rows'])[['기준', '전']].rename(columns={'전': '점수'}), hide_index=True)
                        st.write('약한 점:', a['weak'])
                        if answer_score(a) < 14:
                            st.write('고친 답:', a['rewrite'])
                            st.write('사람이 확인할 것:', ', '.join(a['check']) or '없음')
                with st.container(key='review_next'):
                    st.markdown('**🎯 다음 연습 미션**')
                    for task in ev['next']:
                        st.write('•', task)

    with retry:
        st.markdown('<div class="section-intro"><span>SECOND CHANCE</span><h2>한 번 더, 나답게</h2><p>조금 아쉬웠던 답변을 다시 연습하고 변화를 확인해요.</p></div>', unsafe_allow_html=True)
        if not s.evaluation:
            with st.container(key='retry_empty'):
                character_card('ready', '다음 연습을 기다리고 있어요')
                st.info('먼저 평가 탭에서 위원의 평가를 받아 주세요.')
        else:
            ordered = sorted(s.evaluation['answers'], key=answer_score)
            with st.container(key='retry_mission'):
                st.markdown('**🎯 다시 도전할 질문**')
                st.caption('점수가 낮은 질문부터 보여드려요.')
                no = st.selectbox('질문 선택', [a['no'] for a in ordered], format_func=lambda n: f"{n}. {s.questions[n-1]['question']}")
                before = next(a for a in ordered if a['no'] == no)
                st.metric('지난 점수', f'{answer_score(before)} / 20')
                st.markdown('**수달이 발견한 연습 포인트**')
                st.write(before['weak'])
                with st.expander('이전 답변 다시 보기'):
                    for turn in s.records[no-1]:
                        if turn['role'] == 'user':
                            st.write(turn['content'])
                new_answer = st.text_area('나의 새로운 답변', key=f'retry_answer_{no}', placeholder='지난 답변을 떠올리며 구체적으로 다시 적어 보세요.')
                if st.button('새 답변 채점하기', type='primary', use_container_width=True):
                    if not new_answer.strip():
                        st.warning('답변을 입력해 주세요.')
                    else:
                        try:
                            with st.spinner('새로운 답변을 살펴보고 있어요...'):
                                result = ask_json(prompts.RETRY.format(context=context), json.dumps({'question': s.questions[no-1]['question'], 'answer': new_answer.strip()}, ensure_ascii=False), prompts.RETRY_SCHEMA, 'retry')
                            s.retries[no] = {'answer': new_answer.strip(), 'result': result}
                        except ValueError as exc:
                            st.error(str(exc))
            if no in s.retries:
                after = s.retries[no]['result']
                comparison = compare(before, after)
                with st.container(key='retry_result'):
                    st.markdown('**🌱 달라진 나의 답변**')
                    st.metric('새 점수', f'{answer_score(after)} / 20', delta=comparison['difference'])
                    st.dataframe(pd.DataFrame(comparison['rows']), hide_index=True, use_container_width=True)
                    st.write('다음 연습 포인트:', after['weak'])

    with polish:
        st.markdown('<div class="section-intro"><span>YOUR TURN</span><h2>이번엔 내가 질문할 차례</h2><p>궁금한 것을 더 선명한 질문으로 만들어 볼게요.</p></div>', unsafe_allow_html=True)
        with st.container(key='polish_form'):
            st.markdown('**💭 어떤 점이 궁금한가요?**')
            question = st.text_area('면접관에게 할 질문', placeholder='예: 이 직무의 신입 구성원은 어떤 일을 하게 되나요?')
            if st.button('질문 다듬기', type='primary', use_container_width=True):
                if not question.strip():
                    st.warning('질문을 입력해 주세요.')
                else:
                    try:
                        with st.spinner('수달이 질문을 다듬고 있어요...'):
                            s.polish = ask_json(prompts.POLISH.format(context=context), question.strip(), prompts.POLISH_SCHEMA, 'polish')
                        s.polish_input = question.strip()
                    except ValueError as exc:
                        st.error(str(exc))
        if s.polish:
            st.markdown('### 이렇게 물어보면 어떨까요?')
            if s.get('polish_input') and s.polish_input != question.strip():
                st.caption('아래 결과는 이전에 입력한 질문을 바탕으로 만들었어요.')
            for i, q in enumerate(s.polish['questions']):
                with st.container(key=f'polish_result_{i}'):
                    st.caption(['회사 관점', '직무 관점', '성장 관점'][i] if i < 3 else '다듬은 질문')
                    st.write(q)
            with st.container(key='polish_why'):
                st.markdown('**💡 더해볼 관점**')
                st.write(s.polish['why'])

    with report:
        st.markdown('<div class="section-intro"><span>YOUR JOURNEY</span><h2>오늘의 연습을 간직해요</h2><p>대화와 평가, 재도전 기록을 한 파일로 모았어요.</p></div>', unsafe_allow_html=True)
        with st.container(key='report_card'):
            st.markdown('**📄 나의 면접 리포트**')
            st.caption('지금까지 완료한 내용만 기록돼요.')
            st.write(f'면접 질문 {min(s.index, TOTAL_QUESTIONS)} / {TOTAL_QUESTIONS}개 완료')
            st.write('위원 평가: ' + ('완료' if s.evaluation else '아직 받지 않음'))
            st.write(f'재도전: {len(s.retries)}개 질문')
            st.download_button('리포트 다운로드', make_report(profile, s.questions, s.records, s.evaluation, s.retries), file_name='면접리포트.md', mime='text/markdown', use_container_width=True)

if __name__ == '__main__':
    main()
