# Session 1.2 Part 0.3 -- confirm your Gemini key works. Delete after it prints a greeting.
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
response = client.models.generate_content(model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash"), contents="Say hello in one word.")
print(response.text)
