import imaplib
import ssl
from imapclient import IMAPClient  # Более удобная библиотека

# Настройки Outlook IMAP
IMAP_SERVER = "khb-smtp.hg.loc"
IMAP_PORT = 143
EMAIL = "your-email@outlook.com"
PASSWORD = "your-app-password"  # Пароль приложения (если 2FA)

def check_imap():
    try:
        # Вариант 1: Через imaplib (встроенная библиотека)
        print("Попытка подключения через imaplib...")
        imap = imaplib.IMAP4_SSL(
            host=IMAP_SERVER,
            port=IMAP_PORT,
            ssl_context=ssl.create_default_context()
        )
        imap.login(EMAIL, PASSWORD)
        imap.select("inbox")
        print("✅ Успешное подключение (imaplib)!")
        imap.logout()

        # Вариант 2: Через IMAPClient (рекомендуется)
        print("\nПопытка подключения через IMAPClient...")
        with IMAPClient(IMAP_SERVER, port=IMAP_PORT, ssl=True) as client:
            client.login(EMAIL, PASSWORD)
            client.select_folder("INBOX")
            print("✅ Успешное подключение (IMAPClient)!")
        return True

    except Exception as e:
        print(f"❌ Ошибка IMAP: {e}")
        return False

if check_imap():
    print("\nIMAP-подключение работает!")
else:
    print("\nНе удалось подключиться к IMAP.")