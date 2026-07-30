"""Check env vars without exposing values."""
import os

envvars = [
    'OPENAI_API_KEY', 'MISTRAL_API_KEY', 'ANTHROPIC_API_KEY',
    'GOOGLE_API_KEY', 'PERPLEXITY_API_KEY', 'DATABASE_URL',
    'LM_STUDIO_API_URL', 'EUROPEANA_API_KEY',
    'SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_KEY',
    'HOST', 'PORT',
    'IA_S3_ACCESS_KEY', 'IA_S3_SECRET_KEY',
]
for v in envvars:
    val = os.environ.get(v)
    if val is None:
        print(f"{v}=NOT_SET")
    elif val.strip() == '':
        print(f"{v}=NOT_SET")
    else:
        print(f"{v}=SET")
