# City Walk Planner web — the same static files GitHub Pages serves, plus a reverse proxy for /api.
#
# Proxying /api to the api container keeps the browser on one origin, so no CORS or API address
# is needed: config.js is written with an empty apiBase, which the app treats as "same origin".
FROM nginx:1.27-alpine

COPY src/city_walk_planner/web /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
RUN printf 'window.CWP_CONFIG = Object.freeze({"apiBase": ""});\n' > /usr/share/nginx/html/config.js

EXPOSE 80
