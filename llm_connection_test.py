import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.rcouyi.com/v1/",
    api_key='sk-mPCEjW5z6Uvzto21261e10Fa86D84292B01694B33e44Fc9c',
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    max_tokens=16000,
    messages=[{"role": "user", "content": "Why is the sky blue?"}],
)
print(response.choices[0].message.content)