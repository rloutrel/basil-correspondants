"""WSGI config for the Basil correspondants component."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "basil_correspondants.settings")

application = get_wsgi_application()
