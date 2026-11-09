"""Print the URL of each page: sitemap.py BASE_URL PAGE..."""

import sys

base_url = sys.argv[1]
for page in sys.argv[2:]:
    print(base_url + page)
