import random

TOTAL_QUESTIONS = 5
MAX_FOLLOW_UPS = 1
CRITERIA = {'specific': '구체성', 'relevance': '직무 연관', 'structure': '구조', 'evidence': '근거 · 검증'}

def progress_percent(completed):
    return max(0, min(TOTAL_QUESTIONS, completed)) * 100 // TOTAL_QUESTIONS

def pick_questions(df, job):
    df = df.rename(columns={'직군': 'job', '유형': 'type', '질문': 'question', '보는 점': 'point'}).copy()
    # 기존 질문 은행은 자기소개를 공통 유형으로 분류한다.
    intro = df[df['question'].str.contains('자기소개', na=False)]
    common = df[(df['job'] == '공통') & (df['type'] == '공통') & ~df.index.isin(intro.index)]
    chosen = []
    for pool in [intro, common] + [df[(df['job'] == job) & (df['type'] == kind)] for kind in ('직무', '경험', '상황')]:
        if pool.empty:
            raise ValueError('질문 은행에 필요한 직군 또는 유형의 질문이 없습니다.')
        chosen.append(pool.iloc[random.randrange(len(pool))].to_dict())
    return chosen

def _clip(value, upper):
    return max(0, min(upper, value))

def panel_average(panel):
    return sum(_clip(p['score'], 10) for p in panel) / len(panel) if panel else 0

def answer_score(answer):
    return sum(_clip(answer[k], 5) for k in CRITERIA)

def compare(before, after):
    rows = [{'기준': label, '전': _clip(before[k], 5), '후': _clip(after[k], 5)} for k, label in CRITERIA.items()]
    return {'difference': answer_score(after) - answer_score(before), 'rows': rows}

def make_report(profile, questions, records, evaluation, retries=None):
    lines = ['# 면접 리포트', '', f"- 이름: {profile['name']}", f"- 직군: {profile['job']}", f"- 산업 분야: {profile['company']}", '', '## 면접 기록']
    for i, q in enumerate(questions):
        lines.extend(['', f"### {i + 1}. {q['question']}"])
        for turn in records[i]:
            lines.append(f"- {turn['role']}: {turn['content']}")
    if evaluation:
        lines.extend(['', '## 평가', f"- 위원 평균: {panel_average(evaluation['panel']):.1f}/10", f"- 갈린 곳: {evaluation['conflict']}", f"- 같은 판단: {evaluation['agree']}"])
        for item in evaluation['panel']:
            lines.append(f"- {item['role']}: {_clip(item['score'], 10)}/10 · 반론: {item['against']} · 좋은 점: {item['good']}")
        for a in evaluation['answers']:
            lines.extend(['', f"### 답변 {a['no']} — {answer_score(a)}/20", f"- 약한 점: {a['weak']}"])
            if answer_score(a) < 14:
                lines.extend([f"- 고친 답: {a['rewrite']}", f"- 사람이 확인할 것: {', '.join(a['check']) or '없음'}"])
        lines.extend(['', '## 다음 연습'] + [f'- {x}' for x in evaluation['next']])
        for no, retry in (retries or {}).items():
            before = next((x for x in evaluation['answers'] if x['no'] == no), None)
            if before:
                lines.extend(['', f"## 재도전 {no}", f"- 점수: {answer_score(before)} → {answer_score(retry['result'])} ({compare(before, retry['result'])['difference']:+d})", f"- 답변: {retry['answer']}"])
    return '\n'.join(lines) + '\n'
