import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
print(f"API Key exists: {bool(api_key)}")
if api_key:
    print(f"API Key prefix: {api_key[:8]}...")

client = genai.Client(api_key=api_key)

print("\nListing models available to this key:")
try:
    # Запрашиваем у API список доступных моделей
    models = list(client.models.list())
    for m in models:
        print(f" - {m.name} (supports: {m.supported_actions})")
except Exception as e:
    print(f"Error listing models: {e}")

# Проверяем генерацию текста на разных моделях
for model_name in ['gemini-2.0-flash-lite', 'gemini-2.5-flash-lite', 'gemini-flash-lite-latest']:
    print(f"\nTesting generate content with '{model_name}':")
    try:
        response = client.models.generate_content(
            model=model_name,
            contents='Привет, ответь одним словом "Тест" на русском.',
        )
        print(f" -> Success! Response: {response.text.strip()}")
    except Exception as e:
        print(f" -> Failed: {e}")
