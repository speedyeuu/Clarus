from supabase import create_client, Client
from config import get_settings

# POZOR: @lru_cache záměrně NEPOUŽÍVÁME.
# lru_cache by cachoval instanci navždy — po 24+ hodinách může HTTP session expirovat
# a pipeline pak selže se session timeout chybou aniž by to bylo logováno.
# Supabase klient je lehký objekt, vytvoření nové instance na každý call je bezpečné.

def get_supabase() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)

