import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.kilo.ai/api/gateway",
    api_key='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbnYiOiJwcm9kdWN0aW9uIiwia2lsb1VzZXJJZCI6IjkzZTk1YjhkLWM0YjYtNGY3NS1iNmZlLTg2NzAwMjc4MmM1ZSIsImFwaVRva2VuUGVwcGVyIjpudWxsLCJ2ZXJzaW9uIjozLCJpYXQiOjE3NzI5NzMwMTMsImV4cCI6MTkzMDY1MzAxM30.KGVzlAPF_VLEzh-K4Ga35XrfFkrJghc2UnK6s300rv4',
)

response = client.chat.completions.create(
    model="minimax/minimax-m2.5",
    messages=[{"role": "user", "content": "Why is the sky blue?"}],
)