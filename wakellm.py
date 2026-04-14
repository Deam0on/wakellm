# Compatibility shim — preserves `python wakellm.py start` for existing users
# and cron jobs. All logic lives in the wakellm/ package.
from wakellm.__main__ import main

if __name__ == "__main__":
    main()
