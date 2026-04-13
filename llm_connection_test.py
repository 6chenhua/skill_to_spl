import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.rcouyi.com/v1/",
    api_key='sk-cdLN9MGoaP3uGIPUE89364843aB24e29896f9102359672C1',
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Why is the sky blue?"}],
)