import os
import dfd

real_settings = os.environ.get('REAL_DJANGO_SETTINGS')

if real_settings:
    exec("from %s  import *" % real_settings)

else:
    raise ImportError



static_in = dfd.get_path('static_in')
build_static_in = dfd.get_path('build_static_in')
static_out = dfd.get_path('static_out')
secret_key_path = dfd.get_path_if_exists('secret_key')


DEBUG = bool(dfd.get_path_if_exists('debug_if_exists'))

if secret_key_path:
    with open(secret_key_path) as secret_key_file:
        SECRET_KEY=secret_key_file.read()

EXTENDED_STATICFILES_DIRS = []

for location in [l for l in [static_in, build_static_in] if os.path.exists(l)]:
    for filename in os.listdir(location):
        path = os.path.join(location, filename)
        if os.path.isdir(path):
            EXTENDED_STATICFILES_DIRS.append(path)

if EXTENDED_STATICFILES_DIRS:
    if 'STATICFILES_DIRS' in locals():
        STATICFILES_DIRS.extend(EXTENDED_STATICFILES_DIRS)
    else:
        STATICFILES_DIRS = EXTENDED_STATICFILES_DIRS

STATIC_ROOT = static_out
