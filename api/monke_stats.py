# api/monke_stats.py
from api.update_monke_count import handler as _handler
# Re-export the same handler (GET returns stats)
handler = _handler
