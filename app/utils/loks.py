from threading import Lock
from collections import defaultdict


_locks = defaultdict(Lock)


def chat_lock(chat_id: int) -> Lock:
    return _locks[int(chat_id)]
