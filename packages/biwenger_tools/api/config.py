import os

from dotenv import load_dotenv

load_dotenv()

# Deployed version metadata (set by CI, see deploy.yml). Used by /version.
GIT_COMMIT = os.getenv("GIT_COMMIT", "local")
DEPLOY_TIME = os.getenv("DEPLOY_TIME", "")
