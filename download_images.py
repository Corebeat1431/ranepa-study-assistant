import os
import urllib.request

# Создаем папку для ресурсов
IMAGES_DIR = os.path.join("assets", "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

# Список изображений для загрузки (Unsplash Open Source / Public Domain)
IMAGES_TO_DOWNLOAD = {
    "sevastopol.jpg": "https://images.unsplash.com/photo-1544816155-12df9643f363?w=800&q=80",  # Море, побережье, корабли
    "science.jpg": "https://images.unsplash.com/photo-1532094349884-543bc11b234d?w=800&q=80",     # Наука, микроскоп, лаборатория
    "tourism.jpg": "https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=800&q=80",     # Путешествия, туризм
    "technology.jpg": "https://images.unsplash.com/photo-1593508512255-86ab42a8e620?w=800&q=80",  # Технологии, VR-очки, инновации
    "education.jpg": "https://images.unsplash.com/photo-1523240795612-9a054b0db644?w=800&q=80",   # Студенты, обучение, молодежь
    "team.jpg": "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=800&q=80",        # Команда, рабочие места, социальный эффект
    "business.jpg": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=800&q=80"     # Планирование, бизнес, дорожная карта
}

def download_images():
    print("=== ЗАГРУЗКА ИЗОБРАЖЕНИЙ ИЗ ОТКРЫТЫХ ИСТОЧНИКОВ ===")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for filename, url in IMAGES_TO_DOWNLOAD.items():
        target_path = os.path.join(IMAGES_DIR, filename)
        
        if os.path.exists(target_path):
            print(f"[ПРОПУЩЕНО] Файл {filename} уже существует.")
            continue
            
        print(f"Загрузка {filename}...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as response:
                with open(target_path, 'wb') as out_file:
                    out_file.write(response.read())
            print(f"[УСПЕШНО] Сохранено в {target_path}")
        except Exception as e:
            print(f"[ОШИБКА] Не удалось скачать {filename}: {e}")

if __name__ == "__main__":
    download_images()
