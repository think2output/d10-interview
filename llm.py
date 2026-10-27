import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, AuthenticationError, RateLimitError, APIConnectionError, APIStatusError

load_dotenv(Path(__file__).with_name('.env'), override=True)

def ask_json(instructions, user_input, schema, name):
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        raise ValueError('d10-interview/.env 에 키를 넣어 주세요')
    model = os.getenv('OPENAI_MODEL', 'gpt-6-luna').strip() or 'gpt-6-luna'
    if name == 'evaluation':
        model = os.getenv('OPENAI_EVAL_MODEL', '').strip() or model
    try:
        response = OpenAI(api_key=key).responses.create(model=model, instructions=instructions, input=user_input,
            text={'format': {'type': 'json_schema', 'name': name, 'schema': schema, 'strict': True}})
        return json.loads(response.output_text)
    except AuthenticationError:
        raise ValueError('API 키를 확인해 주세요.') from None
    except RateLimitError:
        raise ValueError('사용 한도 또는 크레딧을 확인해 주세요.') from None
    except APIConnectionError:
        raise ValueError('서버에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.') from None
    except (APIStatusError, ValueError, TypeError):
        raise ValueError('AI 응답을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.') from None
