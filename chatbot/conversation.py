# In-memory conversation state (will be replaced with MySQL later)
# Key: phone number, Value: dict with step and collected data

_sessions = {}


def get_session(phone):
    return _sessions.get(phone)


def set_session(phone, data):
    _sessions[phone] = data


def clear_session(phone):
    _sessions.pop(phone, None)
