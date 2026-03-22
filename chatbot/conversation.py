from django.core.cache import cache

SESSION_PREFIX = "wa_session_"
SESSION_TIMEOUT = 60 * 60  # 1 hour


def _key(phone):
    return f"{SESSION_PREFIX}{phone}"


def get_session(phone):
    return cache.get(_key(phone))


def set_session(phone, data):
    cache.set(_key(phone), data, SESSION_TIMEOUT)


def clear_session(phone):
    cache.delete(_key(phone))
