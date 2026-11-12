"""نگاشت پنج حالت چهره برای سازگاری با اپ اندروید قبلی."""
MODES = ('normal', 'happy', 'sad', 'angry', 'surprised')

def canonical(value):
    if value == 'upset': return 'sad'
    return value if isinstance(value, str) and value in MODES else None

def robot_mode(value):
    mode = canonical(value)
    # نام قدیمی چهرهٔ عصبانی در پیام ارسالی به اپ حفظ می‌شود.
    return 'upset' if mode == 'angry' else mode
